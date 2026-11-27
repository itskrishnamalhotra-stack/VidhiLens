"""Carry the reviewed complaint v9 into the mixed research export and master DB."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OLD_COMPLAINT = ROOT / "exports" / "complaint_training_v8_research_candidate"
COMPLAINT = ROOT / "exports" / "complaint_training_v9_step1_research_candidate"
OLD_MIXED = ROOT / "exports" / "mixed-source-v19-nyaya-bnss-bsa-experiment"
MIXED = ROOT / "exports" / "mixed-source-v20-step1-nyaya-experiment"
AUDIT = ROOT / "review_automation" / "positive_step1_final_v1"
SOURCE = ROOT / "data_drafts" / "step1_positive_revisions_v1.psv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path: Path) -> list[str]:
    rows = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not rows or any(not row.endswith("\n") for row in rows):
        raise ValueError(f"Malformed JSONL: {path}")
    return rows


def verify_manifest(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        if sha(folder / name) != expected:
            raise ValueError(f"Manifest hash mismatch: {folder.name}/{name}")
    return manifest


def main() -> None:
    if MIXED.exists():
        raise ValueError("Mixed v20 already exists; refuse to overwrite")
    old_complaint = verify_manifest(OLD_COMPLAINT)
    complaint = verify_manifest(COMPLAINT)
    old_mixed = verify_manifest(OLD_MIXED)
    if complaint["train_total"] != 4538 or complaint["dev_total"] != 60 or old_mixed["counts"]["train"] != 8092:
        raise ValueError("Unexpected input counts")
    merged = {}
    for split in ("train", "dev"):
        for suffix in ("sft", "sft_map"):
            name = f"{split}_{suffix}.jsonl"
            old_base_lines = lines(OLD_COMPLAINT / name)
            old_mixed_lines = lines(OLD_MIXED / name)
            if old_mixed_lines[:len(old_base_lines)] != old_base_lines:
                raise ValueError(f"Mixed v19 does not start with complaint v8: {name}")
            merged[name] = lines(COMPLAINT / name) + old_mixed_lines[len(old_base_lines):]
    if len(merged["train_sft.jsonl"]) != 8107 or len(merged["dev_sft.jsonl"]) != 60:
        raise ValueError("Unexpected merged size")
    MIXED.mkdir(parents=True)
    for name, rows in merged.items():
        (MIXED / name).write_text("".join(rows), encoding="utf-8", newline="\n")
    manifest = {"status": "trainer_format_auxiliary_experiment_requires_model_evaluation",
                "counts": {**old_mixed["counts"], "train": 8107, "dev": 60,
                           "complaint_train": 4538, "auxiliary_train": 3569},
                "complaint_bundle": COMPLAINT.relative_to(ROOT).as_posix() + "/manifest.json",
                "parent_mixed_bundle": OLD_MIXED.relative_to(ROOT).as_posix() + "/manifest.json",
                "input_sha256": {"complaint_v9_manifest": sha(COMPLAINT / "manifest.json"),
                                "mixed_v19_manifest": sha(OLD_MIXED / "manifest.json")},
                "files_sha256": {name: sha(MIXED / name) for name in merged},
                "limits": ["Experimental auxiliary Q&A mixture; compare it with complaint-only v9 using independent cases.",
                           "No sealed cases are in the trainer export.",
                           "Source-grounded AI research examples are not legal certification."]}
    (MIXED / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    artifacts = [(COMPLAINT / name, "trainer_format_sft", complaint["train_total"] if name.startswith("train_") else complaint["dev_total"])
                 for name in complaint["files_sha256"]]
    artifacts.extend((path, "step1_audit", None) for path in
                     (COMPLAINT / "manifest.json", AUDIT / "positive_ledger.csv",
                      AUDIT / "per_section.csv", AUDIT / "summary.json", SOURCE))
    artifacts.extend((MIXED / name, "research_experiment", manifest["counts"]["train"] if name.startswith("train_") else manifest["counts"]["dev"])
                     for name in manifest["files_sha256"])
    artifacts.append((MIXED / "manifest.json", "manifest", None))
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for path, role, count in artifacts:
            data = path.read_bytes()
            rel = path.relative_to(ROOT).as_posix()
            key = "step1:v1:" + rel.replace("/", ":")
            prior = conn.execute("SELECT artifact_key,sha256 FROM dataset_artifact WHERE relative_path=?", (rel,)).fetchone()
            if prior:
                if prior[1] != sha(path):
                    raise ValueError(f"Pinned artifact changed: {rel}")
                continue
            conn.execute("INSERT INTO dataset_artifact (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license) VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                         (key, role, rel, sha(path), len(data), count, "AI_reviewed_research_candidate"))
            conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,'zlib',?)", (key, zlib.compress(data, 9)))
            if zlib.decompress(conn.execute("SELECT content FROM dataset_artifact_blob WHERE artifact_key=?", (key,)).fetchone()[0]) != data:
                raise ValueError(f"Blob mismatch: {rel}")
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_complaint_training_bundle", COMPLAINT.relative_to(ROOT).as_posix() + "/manifest.json"))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("positive_step1_audit", AUDIT.relative_to(ROOT).as_posix() + "/summary.json"))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps({"complaint_train": complaint["train_total"], "mixed_train": manifest["counts"]["train"],
                      "master_complaint_pointer": COMPLAINT.relative_to(ROOT).as_posix() + "/manifest.json",
                      "mixed_export": MIXED.relative_to(ROOT).as_posix() + "/manifest.json"}, indent=2))


if __name__ == "__main__":
    main()
