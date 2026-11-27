"""Pin Part 2 source and train-only candidate checks inside the master SQLite file."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
EXPORT = ROOT / "exports" / "part2_candidate_checks_v3_research"
CONFUSERS = ROOT / "exports" / "part2_confusers_v1_research"
FILES = [
    (ROOT / "data_drafts" / "part2_v1_cases.jsonl", "source_ledger", 38),
    (ROOT / "data_drafts" / "part2_remaining_fact_checks.psv", "source_ledger", 278),
    (ROOT / "data_drafts" / "part2_corrections_v1.json", "correction_ledger", 3),
    (EXPORT / "train_sft.jsonl", "candidate_check_train", 594),
    (EXPORT / "train_sft_map.jsonl", "candidate_check_train_map", 594),
    (EXPORT / "review_ledger.jsonl", "review_ledger", 594),
    (EXPORT / "manifest.json", "manifest", None),
    (ROOT / "data_drafts" / "part2_confusers_v1.jsonl", "source_ledger", 11),
    (CONFUSERS / "train_sft.jsonl", "candidate_check_train", 11),
    (CONFUSERS / "train_sft_map.jsonl", "candidate_check_train_map", 11),
    (CONFUSERS / "manifest.json", "manifest", None),
]


def main() -> None:
    manifest = json.loads((EXPORT / "manifest.json").read_text(encoding="utf-8"))
    confuser_manifest = json.loads((CONFUSERS / "manifest.json").read_text(encoding="utf-8"))
    if manifest["candidate_check_train_records"] != 594 or manifest["eligible_offence_sections"] != 297:
        raise ValueError("Unexpected Part 2 manifest counts")
    for path, _, _ in FILES:
        source_manifest = confuser_manifest if path.is_relative_to(CONFUSERS) or path.name == "part2_confusers_v1.jsonl" else manifest
        expected = source_manifest.get("files_sha256", {}).get(path.name)
        source_hashes = source_manifest.get("source_sha256", {})
        expected = expected or (source_hashes.get(path.name) if isinstance(source_hashes, dict) else
                                source_hashes if path.name == "part2_confusers_v1.jsonl" else None)
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Part 2 hash mismatch: {path}")
    inserted = reused = 0
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for path, role, count in FILES:
            key = "part2:v3:" + path.relative_to(ROOT).as_posix().replace("/", ":")
            data = path.read_bytes()
            relative = path.relative_to(ROOT).as_posix()
            digest = hashlib.sha256(data).hexdigest()
            by_path = conn.execute("SELECT artifact_key,sha256 FROM dataset_artifact WHERE relative_path=?",
                                   (relative,)).fetchone()
            if by_path:
                if by_path[1] != digest:
                    raise ValueError(f"Previously registered source changed: {relative}")
                reused += 1
                continue
            prior = conn.execute("SELECT relative_path,sha256 FROM dataset_artifact WHERE artifact_key=?",
                                 (key,)).fetchone()
            if prior and prior != (relative, digest):
                raise ValueError(f"Pinned artifact changed: {key}")
            conn.execute("""INSERT INTO dataset_artifact
                (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license)
                VALUES (?,?,?,?,?,?,?,NULL,NULL)""",
                (key, role, relative, digest, len(data), count, "AI_authored_research_candidate"))
            conn.execute("""INSERT INTO dataset_artifact_blob
                (artifact_key,compression,content) VALUES (?,'zlib',?)""",
                (key, zlib.compress(data, level=9)))
            loaded = conn.execute("SELECT content FROM dataset_artifact_blob WHERE artifact_key=?", (key,)).fetchone()[0]
            if zlib.decompress(loaded) != data:
                raise ValueError(f"Artifact blob mismatch: {key}")
            inserted += 1
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("part2_candidate_checks", "exports/part2_candidate_checks_v3_research/manifest.json"))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps({"registered_artifacts": inserted, "previously_registered": reused,
                      "train_candidate_checks": 605, "covered_sections": 297,
                      "master_db": str(DB)}, indent=2))


if __name__ == "__main__":
    main()
