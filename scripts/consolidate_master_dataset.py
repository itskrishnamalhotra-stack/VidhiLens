"""Pin source and review artifacts inside the one canonical Phase 1 database.

This does not promote quarantined publisher data into training examples.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, MANIFEST, sha256


LEDGER_PATTERNS = (
    "seed_review_batch*.jsonl",
    "rich_candidates*.jsonl",
    "rich_review*.jsonl",
    "bulk_review*.jsonl",
    "fact_review*.jsonl",
    "followup_review*.jsonl",
    "workflow_review*.jsonl",
    "bns_offence_review*.jsonl",
    "bns_short_review*.jsonl",
    "bns_public_safety_review*.jsonl",
    "hinglish_review*.jsonl",
    "hindi_review*.jsonl",
    "triage_review*.jsonl",
    "coverage_candidates*.jsonl",
    "coverage_review*.jsonl",
)


def add_artifact(conn: sqlite3.Connection, *, key: str, role: str,
                 path: Path, status: str, url: str | None = None,
                 license_name: str | None = None, expected_hash: str | None = None) -> None:
    if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError(f"Missing or outside Phase 1: {path}")
    digest = sha256(path)
    if expected_hash and digest != expected_hash:
        raise ValueError(f"Pinned source changed: {key}")
    relative = path.relative_to(ROOT).as_posix()
    count = None
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as stream:
            count = sum(bool(line.strip()) for line in stream)
    value = (key, role, relative, digest, path.stat().st_size, count,
             status, url, license_name)
    existing = conn.execute("SELECT role, relative_path, sha256, bytes, record_count, status, url, license FROM dataset_artifact WHERE artifact_key=?", (key,)).fetchone()
    if existing and existing != value[1:]:
        raise ValueError(f"Registered artifact changed; create a new version: {key}")
    conn.execute("INSERT OR IGNORE INTO dataset_artifact VALUES (?,?,?,?,?,?,?,?,?)", value)
    packed = conn.execute("SELECT compression, content FROM dataset_artifact_blob WHERE artifact_key=?", (key,)).fetchone()
    if packed:
        if packed[0] != "zlib" or zlib.decompress(packed[1]) != path.read_bytes():
            raise ValueError(f"Embedded artifact differs: {key}")
    else:
        conn.execute("INSERT INTO dataset_artifact_blob VALUES (?,?,?)",
                     (key, "zlib", zlib.compress(path.read_bytes(), level=6)))


def main() -> None:
    external_manifest = json.loads((ROOT / "external_candidates_manifest.json").read_text(encoding="utf-8"))
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""CREATE TABLE IF NOT EXISTS dataset_artifact (
            artifact_key TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL CHECK (bytes > 0),
            record_count INTEGER,
            status TEXT NOT NULL,
            url TEXT,
            license TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS dataset_artifact_blob (
            artifact_key TEXT PRIMARY KEY REFERENCES dataset_artifact(artifact_key),
            compression TEXT NOT NULL CHECK (compression='zlib'),
            content BLOB NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS master_dataset_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        conn.executemany("INSERT OR REPLACE INTO master_dataset_info VALUES (?,?)", (
            ("owner", "Krishna Malhotra"),
            ("contract_version", "dataset-contract-2.0-2026-09-17"),
            ("scope", "BNS 2023 and IT Act 2000 academic complaint assistant"),
            ("training_rule", "Use master_training_record only after export gate passes; never upload this whole file to a training notebook because it contains sealed test cases."),
            ("public_data_rule", "Embedded public candidates are quarantined provenance, not approved training labels."),
        ))
        conn.execute("DROP VIEW IF EXISTS master_training_record")
        conn.execute("DROP VIEW IF EXISTS master_section_coverage")
        conn.execute("DROP VIEW IF EXISTS master_train_scenario")
        conn.execute("""CREATE VIEW master_train_scenario AS
            SELECT * FROM scenario WHERE quality_status='accepted'
            AND review_tier IN ('ai_reviewed','silver') AND privacy_reviewed=1 AND split='train'""")
        conn.execute("""CREATE VIEW IF NOT EXISTS master_dev_scenario AS
            SELECT * FROM scenario WHERE quality_status='accepted'
            AND review_tier='ai_reviewed' AND privacy_reviewed=1 AND split='dev'""")
        conn.execute("""CREATE VIEW IF NOT EXISTS master_sealed_test_scenario AS
            SELECT * FROM scenario WHERE quality_status='accepted'
            AND review_tier='ai_reviewed' AND privacy_reviewed=1 AND split='sealed_test'""")
        conn.execute("""CREATE VIEW master_training_record AS
            SELECT s.scenario_id, s.scenario_group, s.language, s.complaint_text,
                   s.expected_outcome,
                   (SELECT json_group_array(json_object(
                       'provision_id', l.provision_id, 'label', l.label,
                       'rationale', l.rationale, 'missing_facts', l.missing_facts,
                       'verified_law_text', p.verified_text,
                       'source_id', p.source_id, 'source_pdf_page', p.source_pdf_page))
                    FROM scenario_provision_label l JOIN provision p USING (provision_id)
                    WHERE l.scenario_id=s.scenario_id) AS labels_json,
                   (SELECT json_group_array(json_object(
                       'fact_key', f.fact_key, 'state', f.state,
                       'fact_value', f.fact_value, 'evidence_span', f.evidence_span))
                    FROM scenario_fact f WHERE f.scenario_id=s.scenario_id) AS facts_json,
                   (SELECT json_group_array(json_object(
                       'turn_index', a.turn_index, 'user_message', a.user_message,
                       'assistant_action', a.assistant_action,
                       'assistant_message', a.assistant_message,
                       'tool_payload_json', a.tool_payload_json))
                    FROM conversation_example a WHERE a.scenario_id=s.scenario_id
                    AND a.quality_status='accepted') AS conversation_json
            FROM master_train_scenario s""")
        conn.execute("""CREATE VIEW master_section_coverage AS
            SELECT r.provision_id,
                   SUM(CASE WHEN s.split='train' THEN 1 ELSE 0 END) AS train_positive,
                   SUM(CASE WHEN s.split='dev' THEN 1 ELSE 0 END) AS dev_positive,
                   SUM(CASE WHEN s.split='sealed_test' THEN 1 ELSE 0 END) AS sealed_test_positive
            FROM recommendable_provision r
            LEFT JOIN scenario_provision_label l ON l.provision_id=r.provision_id
                AND l.label='possible'
            LEFT JOIN scenario s ON s.scenario_id=l.scenario_id
                AND s.quality_status='accepted' AND s.review_tier IN ('ai_reviewed','silver')
                AND s.privacy_reviewed=1
            GROUP BY r.provision_id""")
        for source in MANIFEST["sources"]:
            add_artifact(conn, key="official:" + source["source_id"], role="official_law_source",
                         path=ROOT / source["path"], status="pinned_source_snapshot",
                         url=source.get("url"), expected_hash=source["sha256"])
        for source in external_manifest["files"]:
            add_artifact(conn, key="public:" + source["key"], role="public_candidate",
                         path=ROOT / source["local_path"], status=source["review_status"],
                         url=source["url"], license_name=source["license"],
                         expected_hash=source["sha256"])
        add_artifact(conn, key="review:bns_commencement_bulk", role="law_status_review",
                     path=ROOT / "bns_commencement_bulk_review.json",
                     status="source_checked_commencement_only")
        add_artifact(conn, key="review:bns_short_batch03_audit", role="law_text_review",
                     path=ROOT / "bns_short_review_batch03_audit.json",
                     status="source_checked_text_and_kind")
        add_artifact(conn, key="review:bns_public_safety_batch04_audit", role="law_text_review",
                     path=ROOT / "bns_public_safety_review_batch04_audit.json",
                     status="source_checked_text_and_kind_not_recommendable")
        add_artifact(conn, key="review:it_jan_vishwas_status_v1", role="law_status_review",
                     path=ROOT / "it_jan_vishwas_status_audit.json",
                     status="source_checked_status_only_text_pending")
        add_artifact(conn, key="contract:dataset_v2", role="dataset_contract",
                     path=ROOT / "dataset_contract.json", status="current_contract")
        ncrb_manifest = json.loads((ROOT / "ncrb_crosswalk_manifest.json").read_text(encoding="utf-8"))
        add_artifact(conn, key="official:ncrb_ipc_bns_crosswalk_20260917",
                     role="official_correspondence_source",
                     path=ROOT / ncrb_manifest["local_path"],
                     status="candidate_cross_reference_not_training_approval",
                     url=ncrb_manifest["url"], expected_hash=ncrb_manifest["sha256"])
        add_artifact(conn, key="crosswalk:ncrb_manifest_v1", role="source_manifest",
                     path=ROOT / "ncrb_crosswalk_manifest.json",
                     status="current_crosswalk_source_manifest")
        add_artifact(conn, key="crosswalk:ncrb_parse_report_v1", role="automation_audit",
                     path=ROOT / "ncrb_crosswalk_report.json",
                     status="candidate_correspondence_only")
        add_artifact(conn, key="screen:public_full_v1", role="automation_audit",
                     path=ROOT / "data_drafts" / "automation_full_report.json",
                     status="source_screen_only_not_training_approval")
        csv_path = ROOT / "data_drafts" / "synthetic_training_expansion_v1.csv"
        if csv_path.is_file():
            add_artifact(conn, key="ledger:synthetic_training_expansion_v1",
                         role="synthetic_train_csv", path=csv_path,
                         status="family_reviewed_silver_train_only")
        add_artifact(conn, key="screen:law_preflight_v1", role="automation_audit",
                     path=ROOT / "data_drafts" / "law_preflight_packets" / "report.json",
                     status="parser_check_only_not_legal_approval")
        for packet in sorted((ROOT / "data_drafts" / "law_preflight_packets").glob("packet_*.jsonl")):
            add_artifact(conn, key="screen:" + packet.stem, role="law_review_packet",
                         path=packet, status="awaiting_ai_legal_review")
        ledgers = {path for pattern in LEDGER_PATTERNS for path in (ROOT / "data_drafts").glob(pattern)}
        for path in sorted(ledgers):
            add_artifact(conn, key="ledger:" + path.stem, role="review_or_candidate_ledger",
                         path=path, status="provenance_only")
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.commit()
        count = conn.execute("SELECT count(*) FROM dataset_artifact").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM dataset_artifact_blob").fetchone()[0] == count
        assert conn.execute("SELECT count(*) FROM master_training_record").fetchone()[0] == conn.execute("SELECT count(*) FROM master_train_scenario").fetchone()[0]
        assert conn.execute("SELECT count(*) FROM master_training_record WHERE json_valid(labels_json)=0 OR json_valid(facts_json)=0 OR json_valid(conversation_json)=0").fetchone()[0] == 0
        print(json.dumps({"master_database": str(DB_PATH), "pinned_artifacts": count,
                          "embedded_artifacts": count,
                          "train": conn.execute("SELECT count(*) FROM master_train_scenario").fetchone()[0],
                          "dev": conn.execute("SELECT count(*) FROM master_dev_scenario").fetchone()[0],
                          "sealed_test": conn.execute("SELECT count(*) FROM master_sealed_test_scenario").fetchone()[0]}, indent=2))


if __name__ == "__main__":
    main()
