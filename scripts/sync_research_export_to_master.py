"""Store the frozen research SFT and extra held-out cases in the master DB.

This is a lossless inventory import, not legal approval. The source JSONL files
remain the reviewable provenance; this table makes one SQLite file sufficient
to inspect and reproduce the current research training split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
DEFAULT_EXPORT = ROOT / "exports" / "mixed-source-v17-complaint-gsms-research"
DEFAULT_SEALED = [
    ROOT / "data_drafts" / "gap_examples_v2" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch08_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch09_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch10_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch11_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch12_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch13_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch14_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch15_checked" / "sealed_test.jsonl",
    ROOT / "data_drafts" / "coverage_batch16_checked" / "sealed_test.jsonl",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_lines(path: Path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith("\n") or not line.strip():
                raise ValueError(f"Malformed JSONL line: {path}:{number}")
            yield number, line[:-1].removesuffix("\r")


def target_id(data: dict, meta: dict) -> str | None:
    if meta.get("target_provision_id"):
        return meta["target_provision_id"]
    if (meta.get("kind") or meta.get("task_family")) != "triage":
        return None
    answer = json.loads(data["messages"][-1]["content"])
    options = answer.get("possible_provision_ids", [])
    if len(options) == 1:
        return options[0]
    uncertain = answer.get("uncertain_sections", [])
    if not options and len(uncertain) == 1:
        return uncertain[0].get("provision_id")
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--sealed", type=Path, action="append")
    args = parser.parse_args()
    export = args.export.resolve()
    sealed_files = [p.resolve() for p in (args.sealed or DEFAULT_SEALED)]
    if len(set(sealed_files)) != len(sealed_files):
        raise ValueError("Duplicate sealed file")
    manifest_path = export / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename, expected in manifest["files_sha256"].items():
        if sha(export / filename) != expected:
            raise ValueError(f"Research export hash mismatch: {filename}")
    inputs = [(manifest_path, "manifest"),
              *((export / name, name) for name in manifest["files_sha256"])]
    for path in sealed_files:
        batch_manifest_path = path.with_name("manifest.json")
        if batch_manifest_path.exists():
            hashes = json.loads(batch_manifest_path.read_text(encoding="utf-8"))["files_sha256"]
            expected = hashes.get("sealed_test", hashes.get(path.name))
            if expected is None:
                raise ValueError(f"Sealed hash is not declared in {batch_manifest_path}")
            if sha(path) != expected:
                raise ValueError(f"Sealed hash mismatch: {path}")
            inputs.append((batch_manifest_path, "sealed_manifest"))
        inputs.append((path, "sealed_test"))

    records = []
    seen_keys = set()
    for split in ("train", "dev"):
        data_path = export / f"{split}_sft.jsonl"
        map_path = export / f"{split}_sft_map.jsonl"
        for (number, data_line), (map_number, map_line) in zip(
                read_lines(data_path), read_lines(map_path), strict=True):
            if number != map_number:
                raise ValueError(f"Misaligned data and map: {split}")
            data, meta = json.loads(data_line), json.loads(map_line)
            if meta.get("split", split) != split or not isinstance(data.get("messages"), list):
                raise ValueError(f"Bad research row: {split}:{number}")
            key = f"{split}:{number:07d}"
            records.append((key, split, source_name(data_path), number, data_line,
                            map_line, meta.get("kind") or meta.get("task_family"),
                            target_id(data, meta)))
            seen_keys.add(key)
        if number != manifest["counts"][split]:
            raise ValueError(f"Count mismatch: {split}")
    for path in sealed_files:
        for number, data_line in read_lines(path):
            row = json.loads(data_line)
            if row.get("metadata", {}).get("split") != "sealed_test" or not row.get("messages"):
                raise ValueError(f"Bad sealed row: {path}:{number}")
            key = "sealed:" + source_name(path.parent) + ":" + str(row["id"])
            if key in seen_keys:
                raise ValueError(f"Duplicate sealed key: {key}")
            seen_keys.add(key)
            meta = row["metadata"]
            records.append((key, "sealed_test", source_name(path), number,
                            json.dumps({"messages": row["messages"]}, ensure_ascii=False,
                                       separators=(",", ":")),
                            json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
                            meta.get("kind") or meta.get("task_family"),
                            target_id(row, meta)))

    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_sft_record (
            record_key TEXT PRIMARY KEY,
            split TEXT NOT NULL CHECK(split IN ('train','dev','sealed_test')),
            source_file TEXT NOT NULL,
            source_line INTEGER NOT NULL CHECK(source_line > 0),
            data_json TEXT NOT NULL CHECK(json_valid(data_json)),
            metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
            task_kind TEXT,
            target_provision_id TEXT REFERENCES provision(provision_id),
            UNIQUE(source_file,source_line)
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_import_source (
            source_file TEXT PRIMARY KEY,
            source_role TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            imported_row_count INTEGER NOT NULL
        )""")
        conn.execute("DROP VIEW IF EXISTS research_train_record")
        conn.execute("DROP VIEW IF EXISTS research_dev_record")
        conn.execute("DROP VIEW IF EXISTS research_sealed_record")
        conn.execute("CREATE VIEW research_train_record AS SELECT * FROM research_sft_record WHERE split='train'")
        conn.execute("CREATE VIEW research_dev_record AS SELECT * FROM research_sft_record WHERE split='dev'")
        conn.execute("CREATE VIEW research_sealed_record AS SELECT * FROM research_sft_record WHERE split='sealed_test'")
        conn.execute("DELETE FROM research_sft_record")
        conn.execute("DELETE FROM research_import_source")
        conn.executemany("""INSERT INTO research_sft_record
            (record_key,split,source_file,source_line,data_json,metadata_json,task_kind,target_provision_id)
            VALUES (?,?,?,?,?,?,?,?)""", records)
        for path, role in inputs:
            relative = source_name(path)
            n = conn.execute("SELECT count(*) FROM research_sft_record WHERE source_file=?",
                             (relative,)).fetchone()[0]
            conn.execute("INSERT INTO research_import_source VALUES (?,?,?,?)",
                         (relative, role, sha(path), n))
        counts = dict(conn.execute("SELECT split,count(*) FROM research_sft_record GROUP BY split"))
        expected = {"train": manifest["counts"]["train"],
                    "dev": manifest["counts"]["dev"],
                    "sealed_test": sum(1 for path in sealed_files for _ in read_lines(path))}
        if counts != expected or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError(f"Research import counts or foreign keys failed: {counts} != {expected}")
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_research_export", source_name(manifest_path)))
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("research_status", "candidate; AI authored and mixed source; not final legal validation"))
        conn.commit()
    print(json.dumps({"master_database": str(DB), "research_records": counts,
                      "source_files_pinned": len(inputs),
                      "status": "research_candidate_not_model_release"}, indent=2))


if __name__ == "__main__":
    main()
