"""Pin the unified Part 2 trainer-format bundle in the master database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
OUT = ROOT / "exports" / "complaint_training_v8_research_candidate"


def main() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    if manifest["train_total"] != 4523 or manifest["dev_total"] != 60:
        raise ValueError("Unexpected training bundle size")
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for name in (*manifest["files_sha256"], "manifest.json"):
            path = OUT / name
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if name != "manifest.json" and manifest["files_sha256"][name] != digest:
                raise ValueError(f"Bundle hash mismatch: {name}")
            key = "part2:bundle_v8:" + name
            relative = path.relative_to(ROOT).as_posix()
            old = conn.execute("SELECT relative_path,sha256 FROM dataset_artifact WHERE artifact_key=?",
                               (key,)).fetchone()
            if old and old != (relative, digest):
                raise ValueError(f"Pinned bundle artifact changed: {name}")
            count = manifest["train_total"] if name.startswith("train_") else (
                manifest["dev_total"] if name.startswith("dev_") else None)
            conn.execute("""INSERT OR REPLACE INTO dataset_artifact
                (artifact_key,role,relative_path,sha256,bytes,record_count,status,url,license)
                VALUES (?,?,?,?,?,?,?,NULL,NULL)""",
                (key, "trainer_format_sft" if name.endswith(".jsonl") else "manifest",
                 relative, digest, len(data), count, "AI_authored_research_candidate"))
            conn.execute("""INSERT OR REPLACE INTO dataset_artifact_blob
                (artifact_key,compression,content) VALUES (?,'zlib',?)""",
                (key, zlib.compress(data, 9)))
            copied = conn.execute("SELECT content FROM dataset_artifact_blob WHERE artifact_key=?",
                                  (key,)).fetchone()[0]
            if zlib.decompress(copied) != data:
                raise ValueError(f"Bundle blob mismatch: {name}")
        conn.execute("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)",
                     ("current_complaint_training_bundle", "exports/complaint_training_v8_research_candidate/manifest.json"))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key failure")
        conn.commit()
    print(json.dumps({"registered_bundle_files": 5, "train": 4523, "dev": 60,
                      "master_db": str(DB)}, indent=2))


if __name__ == "__main__":
    main()
