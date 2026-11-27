"""Repeatable integrity check for the assembled master and limited pilot export."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections import Counter
from pathlib import Path

from build_full_kb import DB_PATH, ROOT


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    pilot_exports = sorted((ROOT / "exports").glob("scoped-pilot-*/manifest.json"))
    check(bool(pilot_exports), "No scoped pilot export found")
    export_dir = pilot_exports[-1].parent
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity failed")
        check(not conn.execute("PRAGMA foreign_key_check").fetchall(), "Foreign key failure")
        counts = dict(conn.execute("SELECT source_key,count(*) FROM public_candidate_row GROUP BY source_key"))
        check(sum(counts.values()) == 6681 and len(counts) == 6, "Source pool incomplete")
        screen_counts = dict(conn.execute("SELECT source_key,count(*) FROM public_source_screen GROUP BY source_key"))
        check(screen_counts == counts, "Source screening incomplete")
        for key, number, record_json, row_hash, screened_hash in conn.execute("""
            SELECT r.source_key,r.row_number,r.record_json,r.row_sha256,s.source_row_sha256
            FROM public_candidate_row r JOIN public_source_screen s
            ON (r.source_key,r.row_number)=(s.source_key,s.row_number)
        """):
            normalized = json.dumps(json.loads(record_json), ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")).encode("utf-8")
            check(row_hash == screened_hash == digest(normalized), f"Source row mismatch: {key}:{number}")
        check(conn.execute("SELECT count(*) FROM public_source_screen WHERE training_approved=1").fetchone()[0] == 21,
              "Approved public count changed")
        artifact_count = 0
        for key, expected, compression, blob in conn.execute("""
            SELECT a.artifact_key,a.sha256,b.compression,b.content
            FROM dataset_artifact a JOIN dataset_artifact_blob b USING (artifact_key)
        """):
            check(compression == "zlib" and digest(zlib.decompress(blob)) == expected,
                  f"Embedded artifact mismatch: {key}")
            artifact_count += 1
        check(artifact_count == conn.execute("SELECT count(*) FROM dataset_artifact").fetchone()[0],
              "Artifact missing embedded content")
        accepted = dict(conn.execute("""SELECT split,count(*) FROM scenario
            WHERE quality_status='accepted' GROUP BY split"""))
        check(accepted.get("train", 0) >= 2980 and accepted.get("dev", 0) >= 24
              and accepted.get("sealed_test", 0) >= 80, "Accepted split fell below reviewed baseline")
        check(conn.execute("SELECT count(*) FROM scenario WHERE scenario_id LIKE 'NYV3_%' AND quality_status='accepted'").fetchone()[0] == 24,
              "Nyaya case-review import incomplete")
        check(conn.execute("SELECT count(*) FROM scenario WHERE scenario_id LIKE 'GAPDEV_%' AND quality_status='accepted'").fetchone()[0] == 11,
              "Pilot development gap import incomplete")
        check(conn.execute("SELECT count(*) FROM scenario WHERE scenario_id LIKE 'GAPTRAIN_%' AND quality_status='accepted'").fetchone()[0] == 3,
              "Pilot train gap import incomplete")
        silver = conn.execute("""SELECT count(*) FROM scenario WHERE quality_status='accepted'
            AND split='train' AND review_tier='silver'""").fetchone()[0]
        check(silver == 2760, "Synthetic CSV batch changed")
        leaks = conn.execute("""SELECT count(*) FROM (
            SELECT scenario_group FROM scenario WHERE quality_status='accepted'
            GROUP BY scenario_group HAVING count(DISTINCT split)>1)""").fetchone()[0]
        check(leaks == 0, "Related scenarios cross splits")
        law = dict(conn.execute("SELECT act_id,count(*) FROM provision GROUP BY act_id"))
        crosswalk_count = conn.execute("SELECT count(*) FROM ipc_bns_crosswalk_candidate").fetchone()[0]
        check(crosswalk_count == 502, "Official crosswalk candidate count changed")
        check(conn.execute("SELECT count(*) FROM ipc_bns_crosswalk_candidate WHERE training_label_approved=1").fetchone()[0] == 0,
              "Unreviewed IPC/BNS correspondence entered training")
    export_counts = {}
    exported_ids = {}
    for split in ("train", "dev"):
        data_path = export_dir / f"{split}_sft.jsonl"
        map_path = export_dir / f"{split}_sft_map.jsonl"
        for path in (data_path, map_path):
            check(digest(path.read_bytes()) == manifest["files_sha256"][path.name],
                  f"Pilot export hash mismatch: {path.name}")
        data = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()]
        mapping = [json.loads(line) for line in map_path.read_text(encoding="utf-8").splitlines()]
        check(len(data) == len(mapping), f"Pilot export map length mismatch: {split}")
        for row, meta in zip(data, mapping):
            check(meta["split"] == split and row["messages"][-1]["role"] == "assistant",
                  f"Pilot export shape mismatch: {split}")
            json.loads(row["messages"][-1]["content"])
        export_counts[split] = dict(Counter(item["kind"] for item in mapping))
        exported_ids[split] = {item["scenario_id"] for item in mapping}
    check(not (exported_ids["train"] & exported_ids["dev"]), "Train/dev scenario overlap")
    check(export_counts == manifest["records_by_split_and_kind"], "Pilot export count mismatch")
    check(not list(export_dir.glob("*sealed*")), "Sealed test file in pilot export")
    report = {"result": "pass", "master_database": str(DB_PATH),
              "sqlite_integrity": "ok", "foreign_key_errors": 0,
              "law_entries": law, "source_rows_hash_checked": sum(counts.values()),
              "official_ipc_bns_candidate_pairs": crosswalk_count,
              "ipc_bns_labels_autoapproved": 0,
              "source_rows_screened": sum(screen_counts.values()),
              "embedded_artifacts_hash_checked": artifact_count,
              "family_reviewed_silver_train_rows": silver,
              "accepted_scenarios_by_split": accepted, "split_group_leaks": leaks,
              "pilot_export": str(export_dir), "pilot_export_records": export_counts,
              "pilot_export_hashes_valid": True, "sealed_test_files_exported": 0,
              "scope_note": "Integrity passes. The 3,000 SFT row target includes 2,760 family-reviewed surface variants; full legal coverage and model-quality evidence remain incomplete."}
    output = ROOT / "master_v1_verification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
