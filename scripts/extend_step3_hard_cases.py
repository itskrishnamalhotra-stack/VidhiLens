"""Freeze extra missing-fact and out-of-scope evaluation cases in versioned exports."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
BASE_EVAL = ROOT / "exports" / "evaluation-step3-v4"
BASE_MIXED = ROOT / "exports" / "mixed-source-v25-step3-evaluation"
HARD = ROOT / "data_drafts" / "step3_hard_eval_cases_v1.psv"
OUT = ROOT / "exports" / "evaluation-step3-v5"
MIXED = ROOT / "exports" / "mixed-source-v26-step3-evaluation"
SYSTEM = ("Read the reported incident. Return JSON only with outcome, possible_provision_ids, "
          "and uncertain_sections. A section is only a possibility, never a finding of guilt. "
          "Never invent missing facts.")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def save(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")


def main() -> None:
    if OUT.exists() or MIXED.exists():
        raise ValueError("Versioned export already exists")
    for folder in (BASE_EVAL, BASE_MIXED):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files_sha256"].items():
            if sha(folder / name) != digest:
                raise ValueError(f"Frozen input changed: {folder.name}/{name}")
    with sqlite3.connect(DB) as conn:
        laws = {pid: (page, hashlib.sha256(text.encode()).hexdigest()) for pid, page, text in conn.execute(
            "SELECT provision_id,source_pdf_page,verified_text FROM provision "
            "WHERE legal_status='in_force' AND provision_kind='offence' AND verified_text IS NOT NULL")}
    rows = {"dev": [], "sealed_test": []}
    for number, line in enumerate(HARD.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        split, outcome, pid, missing, complaint = line.split("|", 4)
        if split not in rows or outcome not in ("insufficient_information", "out_of_scope"):
            raise ValueError(f"Bad type at line {number}")
        if len(complaint.split()) < 18 or len(complaint.split()) > 110:
            raise ValueError(f"Bad complaint length at line {number}")
        if outcome == "insufficient_information":
            if pid not in laws or not missing:
                raise ValueError(f"Unsupported uncertain section at line {number}")
            answer = {"outcome": outcome, "possible_provision_ids": [],
                      "uncertain_sections": [{"provision_id": pid, "missing_facts": missing}]}
        else:
            if pid or missing:
                raise ValueError(f"Out-of-scope row carries provision at line {number}")
            answer = {"outcome": outcome, "possible_provision_ids": [], "uncertain_sections": []}
        key = f"step3-hard-{split}-{number:02d}"
        meta = {"kind": "triage", "split": split, "target_provision_id": pid or None,
                "source": "manual_step3_hard_case", "source_id": key, "incident_family": key,
                "review_status": "AI_reviewed_research_evaluation_candidate",
                "review_note": "AI-authored hard case; no legal gold certification."}
        if pid:
            meta["source_pdf_page"], meta["verified_text_sha256"] = laws[pid]
        rows[split].append({"id": key, "messages": [
            {"role": "system", "content": SYSTEM}, {"role": "user", "content": complaint},
            {"role": "assistant", "content": json.dumps(answer, separators=(",", ":"))}],
            "metadata": meta})
    if {split: len(items) for split, items in rows.items()} != {"dev": 10, "sealed_test": 10}:
        raise ValueError("Hard-case counts changed")
    old_dev = load(BASE_EVAL / "dev_sft.jsonl")
    old_sealed = load(BASE_EVAL / "sealed_test.jsonl")
    all_dev, all_sealed = old_dev + rows["dev"], old_sealed + rows["sealed_test"]
    all_ids = [r["id"] for r in all_dev + all_sealed if "id" in r]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("Duplicate evaluation ID")
    counts = Counter(json.loads(r["messages"][-1]["content"]).get("outcome", "workflow") for r in all_sealed)
    OUT.mkdir(parents=True)
    save(OUT / "dev_sft.jsonl", all_dev)
    save(OUT / "sealed_test.jsonl", all_sealed)
    eval_manifest = {"status": "AI_reviewed_research_evaluation_candidate_not_legal_gold",
                     "counts": {"dev": len(all_dev), "sealed_test": len(all_sealed)},
                     "sealed_outcomes": dict(counts), "development_positive_sections": 297,
                     "parent_manifest": BASE_EVAL.relative_to(ROOT).as_posix() + "/manifest.json",
                     "hard_cases_sha256": sha(HARD),
                     "limits": ["AI-authored cases are research evaluation candidates, not certified legal gold.",
                                "Some positive cases restate statutory elements and may overestimate real complaint performance.",
                                "The sealed file must never be used for training or tuning."]}
    eval_manifest["files_sha256"] = {name: sha(OUT / name) for name in ("dev_sft.jsonl", "sealed_test.jsonl")}
    (OUT / "manifest.json").write_text(json.dumps(eval_manifest, indent=2) + "\n", encoding="utf-8")
    MIXED.mkdir(parents=True)
    for name in ("train_sft.jsonl", "train_sft_map.jsonl"):
        (MIXED / name).write_bytes((BASE_MIXED / name).read_bytes())
    save(MIXED / "dev_sft.jsonl", all_dev)
    save(MIXED / "dev_sft_map.jsonl", load(BASE_MIXED / "dev_sft_map.jsonl") +
         [r["metadata"] for r in rows["dev"]])
    mixed_manifest = {"status": "trainer_format_with_expanded_dev_requires_model_evaluation",
                      "counts": {"train": len(load(MIXED / "train_sft.jsonl")), "dev": len(all_dev)},
                      "parent_manifest": BASE_MIXED.relative_to(ROOT).as_posix() + "/manifest.json",
                      "evaluation_manifest": OUT.relative_to(ROOT).as_posix() + "/manifest.json",
                      "files_sha256": {name: sha(MIXED / name) for name in
                                       ("train_sft.jsonl", "train_sft_map.jsonl", "dev_sft.jsonl", "dev_sft_map.jsonl")},
                      "limits": ["The sealed test is separate from training and development tuning."]}
    (MIXED / "manifest.json").write_text(json.dumps(mixed_manifest, indent=2) + "\n", encoding="utf-8")
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for folder in (OUT, MIXED):
            for path in folder.iterdir():
                rel = path.relative_to(ROOT).as_posix()
                key = "step3:v5:" + rel.replace("/", ":")
                if conn.execute("SELECT 1 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone():
                    raise ValueError(f"Already pinned: {rel}")
                data = path.read_bytes()
                n = len(all_dev) if path.name.startswith("dev_") else len(all_sealed) if path.name == "sealed_test.jsonl" else mixed_manifest["counts"]["train"] if path.name.startswith("train_") else None
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
