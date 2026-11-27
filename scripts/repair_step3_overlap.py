"""Replace overly similar development cases, retaining frozen prior versions."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
BASE_EVAL = ROOT / "exports" / "evaluation-step3-v5"
BASE_MIXED = ROOT / "exports" / "mixed-source-v26-step3-evaluation"
REPAIRS = ROOT / "data_drafts" / "step3_dev_overlap_repairs_v1.psv"
AUDIT = ROOT / "review_automation" / "research_leakage_step3_v5" / "nearest_train.csv"
OUT = ROOT / "exports" / "evaluation-step3-v6"
MIXED = ROOT / "exports" / "mixed-source-v27-step3-evaluation"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def save(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")


def main() -> None:
    if OUT.exists() or MIXED.exists():
        raise ValueError("Versioned output exists")
    for folder in (BASE_EVAL, BASE_MIXED):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files_sha256"].items():
            if sha(folder / name) != digest:
                raise ValueError(f"Frozen input changed: {folder.name}/{name}")
    flagged = {row["held_source_id"].removeprefix("step3-dev-replacement-") for row in
               csv.DictReader(AUDIT.open(encoding="utf-8", newline=""))
               if float(row["lexical_similarity"]) >= .75}
    repairs = {}
    for line in REPAIRS.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        pid, complaint = line.split("|", 1)
        if pid in repairs or not (18 <= len(complaint.split()) <= 110):
            raise ValueError(f"Bad repair: {pid}")
        repairs[pid] = complaint
    if len(repairs) != 43 or flagged != set(repairs):
        raise ValueError(f"Repair coverage differs: missing={flagged-set(repairs)}, extra={set(repairs)-flagged}")
    dev = load(BASE_EVAL / "dev_sft.jsonl")
    sealed = load(BASE_EVAL / "sealed_test.jsonl")
    dev_map = load(BASE_MIXED / "dev_sft_map.jsonl")
    if len(dev) != len(dev_map) or len(dev) != 326 or len(sealed) != 90:
        raise ValueError("Base count mismatch")
    changed = set()
    for row, meta in zip(dev, dev_map, strict=True):
        pid = row.get("metadata", {}).get("target_provision_id")
        if pid not in repairs or row.get("metadata", {}).get("source_id") != f"step3-dev-replacement-{pid}":
            continue
        row["messages"][1]["content"] = repairs[pid]
        row["metadata"]["review_note"] = "Distinct AI-authored incident replacing a training-similar development case; research label."
        meta["review_note"] = row["metadata"]["review_note"]
        changed.add(pid)
    if changed != set(repairs):
        raise ValueError(f"Repair targets not found: {set(repairs)-changed}")
    OUT.mkdir(parents=True)
    save(OUT / "dev_sft.jsonl", dev)
    save(OUT / "sealed_test.jsonl", sealed)
    eval_manifest = {"status": "AI_reviewed_research_evaluation_candidate_not_legal_gold",
                     "counts": {"dev": len(dev), "sealed_test": len(sealed), "repaired_dev": len(changed)},
                     "development_positive_sections": 297,
                     "parent_manifest": BASE_EVAL.relative_to(ROOT).as_posix() + "/manifest.json",
                     "repair_source_sha256": sha(REPAIRS),
                     "limits": ["AI-authored cases are research evaluation candidates, not certified legal gold.",
                                "A lexical screen cannot prove semantic independence or real-world reliability.",
                                "The sealed file must never be used for training or tuning."]}
    eval_manifest["files_sha256"] = {name: sha(OUT / name) for name in ("dev_sft.jsonl", "sealed_test.jsonl")}
    (OUT / "manifest.json").write_text(json.dumps(eval_manifest, indent=2) + "\n", encoding="utf-8")
    MIXED.mkdir(parents=True)
    for name in ("train_sft.jsonl", "train_sft_map.jsonl"):
        (MIXED / name).write_bytes((BASE_MIXED / name).read_bytes())
    save(MIXED / "dev_sft.jsonl", dev)
    save(MIXED / "dev_sft_map.jsonl", dev_map)
    mixed_manifest = {"status": "trainer_format_with_expanded_dev_requires_model_evaluation",
                      "counts": {"train": len(load(MIXED / "train_sft.jsonl")), "dev": len(dev)},
                      "parent_manifest": BASE_MIXED.relative_to(ROOT).as_posix() + "/manifest.json",
                      "evaluation_manifest": OUT.relative_to(ROOT).as_posix() + "/manifest.json",
                      "files_sha256": {name: sha(MIXED / name) for name in
                                       ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")}}
    (MIXED / "manifest.json").write_text(json.dumps(mixed_manifest, indent=2) + "\n", encoding="utf-8")
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for folder in (OUT, MIXED):
            for path in folder.iterdir():
                rel = path.relative_to(ROOT).as_posix()
                key = "step3:v6:" + rel.replace("/", ":")
                if conn.execute("SELECT 1 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone():
                    raise ValueError(f"Already pinned: {rel}")
                data = path.read_bytes()
                n = len(dev) if path.name.startswith("dev_") else len(sealed) if path.name == "sealed_test.jsonl" else mixed_manifest["counts"]["train"] if path.name.startswith("train_") else None
                conn.execute("INSERT INTO dataset_artifact (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                             (key, "evaluation" if folder == OUT else "trainer_format_sft", rel, sha(path), len(data), n, "AI_reviewed_research_candidate"))
                conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,'zlib',?)", (key, zlib.compress(data, 9)))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_evaluation_export", OUT.relative_to(ROOT).as_posix() + "/manifest.json"))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_research_export", MIXED.relative_to(ROOT).as_posix() + "/manifest.json"))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps(eval_manifest, indent=2))


if __name__ == "__main__":
    main()
