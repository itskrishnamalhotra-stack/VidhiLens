"""Verify that master SQLite exactly reproduces the current train/dev SFT."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
DEFAULT_EXPORT = ROOT / "exports" / "mixed-source-v17-complaint-gsms-research"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    args = parser.parse_args()
    export = args.export.resolve()
    manifest = json.loads((export / "manifest.json").read_text(encoding="utf-8"))
    with sqlite3.connect(DB) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Master SQLite integrity check failed")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Master SQLite foreign key check failed")
        imported = dict(conn.execute("SELECT source_file,sha256 FROM research_import_source"))
        for relative, expected in imported.items():
            if sha(ROOT / relative) != expected:
                raise ValueError(f"Imported research source changed: {relative}")
        counts = {}
        for split in ("train", "dev"):
            source = f"exports/{export.name}/{split}_sft.jsonl"
            expected_count = manifest["counts"][split]
            hashes = [hashlib.sha256(), hashlib.sha256()]
            rows = conn.execute("""SELECT source_file,source_line,data_json,metadata_json
                FROM research_sft_record WHERE split=? ORDER BY source_line""", (split,))
            count = 0
            for source_file, number, data, meta in rows:
                count += 1
                if source_file != source or number != count:
                    raise ValueError(f"Research row order/source mismatch: {split}:{count}")
                hashes[0].update((data + "\n").encode())
                hashes[1].update((meta + "\n").encode())
            for i, name in enumerate((f"{split}_sft.jsonl", f"{split}_sft_map.jsonl")):
                if hashes[i].hexdigest() != manifest["files_sha256"][name]:
                    raise ValueError(f"Master database differs from export: {name}")
            if count != expected_count:
                raise ValueError(f"Research row count mismatch: {split}")
            counts[split] = count
        sealed = conn.execute("SELECT count(*) FROM research_sealed_record").fetchone()[0]
        sealed_files = conn.execute("""SELECT source_file,imported_row_count
            FROM research_import_source WHERE source_role='sealed_test'""").fetchall()
        if sealed != sum(n for _, n in sealed_files) or any(
                conn.execute("SELECT count(*) FROM research_sealed_record WHERE source_file=?",
                             (name,)).fetchone()[0] != n for name, n in sealed_files):
            raise ValueError("Sealed research rows do not match pinned sources")
        counts["sealed_test_separate"] = sealed
    print(json.dumps({"status": "master_reproduces_research_train_and_dev",
                      "counts": counts, "pinned_input_files": len(imported)}, indent=2))


if __name__ == "__main__":
    main()
