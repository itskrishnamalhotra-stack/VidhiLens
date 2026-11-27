"""Check the Phase 1 index and recommendation gate."""

from __future__ import annotations

import sqlite3
import json
import hashlib
from pathlib import Path

from build_full_kb import ROOT, DB_PATH, MANIFEST, sha256
from review_priority import cleaned_text
from review_it_expansion_batch01 import clean as clean_it_expansion
from review_it_expansion_batch02 import clean as clean_it_expansion_02
from import_law_review_batch import cleaned as clean_generic_batch


def main() -> None:
    for source in MANIFEST["sources"]:
        assert sha256(ROOT / source["path"]) == source["sha256"]

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        scenario_cols = {row[1] for row in conn.execute("PRAGMA table_info(scenario)")}
        assert {"expected_outcome", "review_tier", "reviewer", "reviewed_on"} <= scenario_cols
        scenario_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='scenario'").fetchone()[0]
        assert "'ai_reviewed'" in scenario_sql
        assert conn.execute("SELECT count(*) FROM provision WHERE act_id='BNS_2023'").fetchone()[0] == 358
        assert conn.execute("SELECT count(*) FROM provision WHERE act_id='ITA_2000'").fetchone()[0] == 125
        assert conn.execute("SELECT count(*) FROM provision WHERE priority_review=1").fetchone()[0] == 20
        assert conn.execute("SELECT count(*) FROM recommendable_provision").fetchone()[0] == 19
        assert conn.execute("SELECT count(*) FROM recommendation_release_approval").fetchone()[0] == 19
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='require_recommendation_release_approval'").fetchone()
        artifact_count = conn.execute("SELECT count(*) FROM dataset_artifact").fetchone()[0]
        assert artifact_count >= 37
        assert conn.execute("SELECT count(*) FROM dataset_artifact_blob").fetchone()[0] == artifact_count
        assert conn.execute("SELECT value FROM master_dataset_info WHERE key='owner'").fetchone()[0] == "Krishna Malhotra"
        assert conn.execute("SELECT count(*) FROM master_section_coverage").fetchone()[0] == 19
        assert conn.execute("SELECT count(*) FROM master_training_record").fetchone()[0] == conn.execute("SELECT count(*) FROM master_train_scenario").fetchone()[0]
        assert not conn.execute("""SELECT r.scenario_id FROM master_training_record r
            JOIN scenario s USING (scenario_id) WHERE s.split!='train' OR s.quality_status!='accepted'""").fetchall()
        assert conn.execute("SELECT count(*) FROM dataset_artifact WHERE role='public_candidate' AND status LIKE 'quarantined%'").fetchone()[0] == 6
        expected_public_rows = {
            'bns_structured': 358, 'bns_qa': 2148, 'nyaya_train': 1293,
            'nyaya_val': 163, 'nyaya_eval': 500, 'statutory_triage': 2219,
        }
        assert dict(conn.execute('SELECT source_key,count(*) FROM public_candidate_row GROUP BY source_key')) == expected_public_rows
        assert conn.execute("SELECT count(*) FROM public_candidate_row WHERE source_key='statutory_triage' AND review_status='publisher_labels_rejected'").fetchone()[0] == 2219
        assert conn.execute("SELECT count(*) FROM public_candidate_row WHERE source_key='nyaya_eval' AND review_status='external_eval_holdout'").fetchone()[0] == 500
        assert conn.execute("SELECT count(*) FROM public_source_screen").fetchone()[0] == 6681
        assert conn.execute("""SELECT count(*) FROM public_candidate_row p
            LEFT JOIN public_source_screen s USING (source_key,row_number)
            WHERE s.source_key IS NULL""").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM public_source_screen WHERE training_approved=1").fetchone()[0] == 21
        assert conn.execute("SELECT count(*) FROM ipc_bns_crosswalk_candidate").fetchone()[0] == 502
        assert conn.execute("SELECT count(*) FROM ipc_bns_crosswalk_candidate WHERE training_label_approved=1").fetchone()[0] == 0
        assert conn.execute("SELECT bns_provision_id FROM ipc_bns_crosswalk_candidate WHERE ipc_section='420'").fetchone()[0] == "BNS_318"
        assert conn.execute("SELECT count(*) FROM dataset_artifact WHERE artifact_key='ledger:hinglish_review_batch04'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM dataset_artifact WHERE artifact_key='ledger:hindi_review_batch05'").fetchone()[0] == 1
        audit = json.loads((ROOT / "priority_source_audit.json").read_text(encoding="utf-8"))
        assert len(audit["entries"]) == 20
        assert len(audit["support_entries"]) == 3
        baseline_verified = 82
        added_reviews = sum(len(json.loads((ROOT / "data_drafts" / name).read_text(encoding="utf-8"))["accepted"])
                            for name in ("exact_law_text_review_20260918.json",
                                         "bns_layout_text_review_20260918.json",
                                         "it_editorial_text_review_20260918.json",
                                         "bns_heading_overflow_review_20260918.json",
                                         "bns_three_exception_review_20260918.json",
                                         "it_visual_two_review_20260918.json",
                                         "it_asterisk_marker_review_20260918.json",
                                         "it_visual_three_review_20260918.json"))
        assert conn.execute("SELECT count(*) FROM provision WHERE verified_text IS NOT NULL").fetchone()[0] >= baseline_verified + added_reviews
        assert conn.execute("SELECT count(*) FROM provision WHERE legal_status='pending_review'").fetchone()[0] == 0
        assert conn.execute("SELECT legal_status FROM provision WHERE provision_id='ITA_43A'").fetchone()[0] == 'in_force'
        for item in audit["entries"] + audit["support_entries"]:
            row = conn.execute("SELECT verified_text, recommendable, source_id, source_pdf_page, extracted_text FROM provision WHERE provision_id=?", (item["id"],)).fetchone()
            assert row and row[0] and bool(row[1]) == item["recommendable"]
            assert row[2] == item["source_id"] and row[3] == item["source_pdf_page"]
            assert hashlib.sha256(row[0].encode("utf-8")).hexdigest() == item["reviewed_text_sha256"]
            assert cleaned_text(item["id"], row[4])[0] == row[0]
        expansion_path = ROOT / "it_expansion_source_audit_batch01.json"
        if expansion_path.exists():
            expansion = json.loads(expansion_path.read_text(encoding="utf-8"))
            assert len(expansion["entries"]) == 8
            for item in expansion["entries"]:
                row = conn.execute("""SELECT verified_text, recommendable, source_id,
                    source_pdf_page, extracted_text FROM provision WHERE provision_id=?""", (item["id"],)).fetchone()
                assert row and row[0] and not row[1]
                assert row[2] == item["source_id"] and row[3] == item["source_pdf_page"]
                assert hashlib.sha256(row[0].encode("utf-8")).hexdigest() == item["reviewed_text_sha256"]
                assert clean_it_expansion(item["id"], row[4])[0] == row[0]
        expansion_path_02 = ROOT / "it_expansion_source_audit_batch02.json"
        if expansion_path_02.exists():
            expansion = json.loads(expansion_path_02.read_text(encoding="utf-8"))
            assert len(expansion["entries"]) == 4
            for item in expansion["entries"]:
                row = conn.execute("""SELECT verified_text, recommendable, source_id,
                    source_pdf_page, extracted_text FROM provision WHERE provision_id=?""", (item["id"],)).fetchone()
                assert row and row[0] and not row[1]
                assert row[2] == item["source_id"] and row[3] == item["source_pdf_page"]
                assert hashlib.sha256(row[0].encode("utf-8")).hexdigest() == item["reviewed_text_sha256"]
                assert clean_it_expansion_02(item["id"], row[4])[0] == row[0]
        for stem, expected_count in (("bns_offence_review_batch01", 11),
                                     ("bns_offence_review_batch02", 7),
                                     ("bns_short_review_batch03", 14),
                                     ("bns_public_safety_review_batch04", 15)):
            generic_audit_path = ROOT / f"{stem}_audit.json"
            generic_ledger_path = ROOT / "data_drafts" / f"{stem}.jsonl"
            if not generic_audit_path.exists():
                continue
            generic_audit = json.loads(generic_audit_path.read_text(encoding="utf-8"))
            decisions = {d["provision_id"]: d for d in map(json.loads, generic_ledger_path.read_text(encoding="utf-8").splitlines())}
            assert len(generic_audit["entries"]) == len(decisions) == expected_count
            for item in generic_audit["entries"]:
                row = conn.execute("""SELECT verified_text, recommendable, source_id,
                    source_pdf_page, extracted_text, provision_kind, legal_status
                    FROM provision WHERE provision_id=?""", (item["id"],)).fetchone()
                assert row and row[0] and not row[1]
                assert row[2] == item["source_id"] and row[3] == item["source_pdf_page"]
                assert row[5] == item["provision_kind"] and row[6] == item["legal_status"]
                assert hashlib.sha256(row[0].encode("utf-8")).hexdigest() == item["reviewed_text_sha256"]
                assert clean_generic_batch(decisions[item["id"]], row[4])[0] == row[0]
        assert conn.execute("SELECT legal_status FROM provision WHERE provision_id='ITA_66A'").fetchone()[0] == "omitted"
        assert conn.execute("SELECT legal_status FROM provision_subpart_status WHERE provision_id='BNS_106' AND subpart='(2)'").fetchone()[0] == "uncommenced"
        assert conn.execute("SELECT count(*) FROM blocked_provision WHERE provision_id='ITA_66A'").fetchone()[0] == 1
        assert conn.execute("SELECT provision_kind FROM provision WHERE provision_id='ITA_72A'").fetchone()[0] == "civil_penalty"
        assert conn.execute("SELECT count(*) FROM blocked_provision WHERE provision_id='ITA_72A'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM blocked_provision WHERE provision_id='ITA_66E'").fetchone()[0] == 1
        assert conn.execute("SELECT source_id FROM provision WHERE provision_id='ITA_66D'").fetchone()[0] == "ITA_INDIA_CODE_CURRENT_2026_09_16"
        assert conn.execute("SELECT count(*) FROM provision_relation").fetchone()[0] >= 3

        # The database itself rejects an unreviewed or blocked recommendation.
        for provision_id in ("BNS_305", "ITA_66A", "ITA_72A", "ITA_66E"):
            try:
                conn.execute("UPDATE provision SET recommendable=1 WHERE provision_id=?", (provision_id,))
            except sqlite3.IntegrityError:
                conn.rollback()
            else:
                conn.rollback()
                raise AssertionError(f"Gate allowed {provision_id}")

        # Even a forged status/text review cannot bypass the explicit 66A block.
        try:
            conn.execute("""UPDATE provision SET legal_status='in_force', verified_text='x',
                text_reviewed_on='2026-09-16', status_reviewed_on='2026-09-16',
                reviewed_by='test', recommendable=1 WHERE provision_id='ITA_66A'""")
        except sqlite3.IntegrityError:
            conn.rollback()
        else:
            conn.rollback()
            raise AssertionError("66A block failed")

        # AI-reviewed sealed references are allowed and honestly distinguished
        # from train-only unverified silver examples. Both probes roll back.
        insert_scenario = """INSERT INTO scenario
            (scenario_id, complaint_text, language, provenance_type, privacy_reviewed,
             quality_status, expected_outcome, review_tier, reviewer, reviewed_on,
             split, scenario_group, created_on)
            VALUES (?, 'A fictional incident with no applicable in-scope provision.',
                    'en', 'synthetic', 1, 'accepted', 'out_of_scope', ?,
                    'Codex AI source-grounded review', '2026-09-16',
                    'sealed_test', ?, '2026-09-16')"""
        conn.execute(insert_scenario, ("__validator_ai__", "ai_reviewed", "__validator_ai__"))
        conn.rollback()
        try:
            conn.execute(insert_scenario, ("__validator_silver__", "silver", "__validator_silver__"))
        except sqlite3.IntegrityError:
            conn.rollback()
        else:
            conn.rollback()
            raise AssertionError("Silver example entered sealed test")
    finally:
        conn.close()
    print("KB validation passed: sources, counts, links, blocked statuses, recommendation gates")


if __name__ == "__main__":
    main()
