"""Report what can safely be used for a Colab pilot or final training release."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import audit_dataset
import compile_sft_data


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
EXTERNAL_MANIFEST = ROOT / "external_candidates_manifest.json"
ADDITIONAL_MANIFEST = ROOT / "additional_candidates_manifest.json"
OUTPUT = ROOT / "data_readiness_report.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar(conn: sqlite3.Connection, query: str) -> int:
    return conn.execute(query).fetchone()[0]


def main() -> None:
    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        law = {
            "bns_entries": scalar(conn, "SELECT count(*) FROM provision WHERE act_id='BNS_2023'"),
            "it_act_entries": scalar(conn, "SELECT count(*) FROM provision WHERE act_id='ITA_2000'"),
            "verified_text": scalar(conn, "SELECT count(*) FROM provision WHERE verified_text IS NOT NULL"),
            "recommendable": scalar(conn, "SELECT count(*) FROM recommendable_provision"),
            "pending_legal_status": scalar(conn, "SELECT count(*) FROM provision WHERE legal_status='pending_review'"),
            "in_force_text_unverified": scalar(conn, "SELECT count(*) FROM provision WHERE legal_status='in_force' AND verified_text IS NULL"),
            "priority_review_total": scalar(conn, "SELECT count(*) FROM provision WHERE priority_review=1"),
            "priority_review_approved": scalar(conn, "SELECT count(*) FROM provision WHERE priority_review=1 AND provision_id IN (SELECT provision_id FROM recommendable_provision)"),
            "provision_kind_pending": scalar(conn, "SELECT count(*) FROM provision WHERE provision_kind='pending_review'"),
            "reviewed_offences_not_recommendable": scalar(conn, "SELECT count(*) FROM provision WHERE legal_status='in_force' AND provision_kind='offence' AND recommendable=0"),
        }
        scenarios = dict(conn.execute("SELECT split, count(*) FROM scenario WHERE quality_status='accepted' GROUP BY split"))
        outcomes = dict(conn.execute("SELECT expected_outcome, count(*) FROM scenario WHERE quality_status='accepted' GROUP BY expected_outcome"))
        review_tiers = dict(conn.execute("SELECT review_tier, count(*) FROM scenario WHERE quality_status='accepted' GROUP BY review_tier"))
        all_scenarios = scalar(conn, "SELECT count(*) FROM scenario")
        accepted = sum(scenarios.values())
        unreviewed_privacy = scalar(conn, "SELECT count(*) FROM scenario WHERE quality_status='accepted' AND privacy_reviewed=0")
        unreviewed_labels = scalar(conn, """SELECT count(*) FROM scenario_provision_label l
            JOIN scenario s ON s.scenario_id=l.scenario_id
            WHERE s.quality_status='accepted' AND (l.reviewer IS NULL OR l.reviewed_on IS NULL)""")
        labeled = scalar(conn, """SELECT count(DISTINCT l.scenario_id) FROM scenario_provision_label l
            JOIN scenario s ON s.scenario_id=l.scenario_id WHERE s.quality_status='accepted'
            AND l.reviewer IS NOT NULL AND l.reviewed_on IS NOT NULL""")
        possible = scalar(conn, """SELECT count(*) FROM scenario_provision_label l
            JOIN scenario s ON s.scenario_id=l.scenario_id WHERE s.quality_status='accepted'
            AND l.label='possible' AND l.reviewer IS NOT NULL AND l.reviewed_on IS NOT NULL""")
        match_without_possible = scalar(conn, """SELECT count(*) FROM scenario s
            WHERE s.quality_status='accepted' AND s.expected_outcome='provision_match'
            AND NOT EXISTS (SELECT 1 FROM scenario_provision_label l WHERE l.scenario_id=s.scenario_id
                AND l.label='possible' AND l.reviewer IS NOT NULL AND l.reviewed_on IS NOT NULL
                AND l.provision_id IN (SELECT provision_id FROM recommendable_provision))""")
        abstention_with_possible = scalar(conn, """SELECT count(DISTINCT s.scenario_id) FROM scenario s
            JOIN scenario_provision_label l ON l.scenario_id=s.scenario_id
            WHERE s.quality_status='accepted' AND s.expected_outcome IN ('insufficient_information','out_of_scope')
            AND l.label='possible'""")
        possible_blocked = scalar(conn, """SELECT count(*) FROM scenario_provision_label l
            JOIN scenario s ON s.scenario_id=l.scenario_id WHERE s.quality_status='accepted'
            AND l.label='possible' AND l.provision_id NOT IN (SELECT provision_id FROM recommendable_provision)""")
        actions = dict(conn.execute("""SELECT assistant_action, count(*) FROM conversation_example
            WHERE quality_status='accepted' GROUP BY assistant_action"""))
        train_actions = dict(conn.execute("""SELECT a.assistant_action, count(*)
            FROM conversation_example a JOIN scenario s USING (scenario_id)
            WHERE a.quality_status='accepted' AND s.quality_status='accepted'
              AND s.split='train' GROUP BY a.assistant_action"""))
        languages = dict(conn.execute("""SELECT language, count(*) FROM scenario
            WHERE quality_status='accepted' GROUP BY language"""))
        coverage = [dict(provision_id=pid, train=train, dev=dev, sealed_test=test)
                    for pid, train, dev, test in conn.execute("SELECT * FROM master_section_coverage ORDER BY provision_id")]
        fact_rows = scalar(conn, """SELECT count(*) FROM scenario_fact f
            JOIN scenario s ON s.scenario_id=f.scenario_id WHERE s.quality_status='accepted'""")
        group_leaks = conn.execute("""SELECT scenario_group FROM scenario
            GROUP BY scenario_group HAVING count(DISTINCT split)>1""").fetchall()
        foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        sft_shape = compile_sft_data.inspect(compile_sft_data.compile_records(conn))
        train_sft_count = sum(sft_shape["train"].values())
        dev_sft_count = sum(sft_shape["dev"].values())
        silver_train_rows = scalar(conn, "SELECT count(*) FROM scenario WHERE quality_status='accepted' AND split='train' AND review_tier='silver'")
        silver_train_families = scalar(conn, "SELECT count(DISTINCT scenario_group) FROM scenario WHERE quality_status='accepted' AND split='train' AND review_tier='silver'")
        original_candidate_rows = scalar(conn, "SELECT count(*) FROM public_candidate_row")
        additional_candidate_rows = scalar(conn, "SELECT count(*) FROM additional_candidate_row")
        additional_approved = scalar(conn, "SELECT count(*) FROM additional_candidate_row WHERE training_approved!=0")
        additional_by_source = dict(conn.execute("SELECT source_key,count(*) FROM additional_candidate_row GROUP BY source_key"))

    external = []
    if EXTERNAL_MANIFEST.exists():
        for row in json.loads(EXTERNAL_MANIFEST.read_text(encoding="utf-8"))["files"]:
            path = ROOT / row["local_path"]
            external.append({"key": row["key"], "bytes": row["bytes"],
                             "license": row["license"], "review_status": row["review_status"],
                             "hash_valid": path.is_file() and sha256(path) == row["sha256"]})

    additional = []
    if ADDITIONAL_MANIFEST.exists():
        for row in json.loads(ADDITIONAL_MANIFEST.read_text(encoding="utf-8"))["files"]:
            path = ROOT / row["local_path"]
            additional.append({"key": row["key"], "bytes": row["bytes"],
                               "license": row["license"],
                               "indexed_rows": additional_by_source.get(row["key"], 0),
                               "hash_valid": path.is_file() and sha256(path) == row["sha256"]})

    blockers = []
    if law["recommendable"] == 0:
        blockers.append("No legally reviewed, recommendable provisions")
    if law["pending_legal_status"]:
        blockers.append(f"Full BNS/IT Act law review incomplete: {law['pending_legal_status']} section entries have pending legal status")
    if law["in_force_text_unverified"]:
        blockers.append(f"Full law text review incomplete: {law['in_force_text_unverified']} in-force sections still have only unverified PDF extraction")
    if law["provision_kind_pending"]:
        blockers.append(f"Full-act classification incomplete: {law['provision_kind_pending']} sections still lack a reviewed offence/support kind")
    if law["reviewed_offences_not_recommendable"]:
        blockers.append(f"Full-act complaint coverage incomplete: {law['reviewed_offences_not_recommendable']} classified in-force offences still lack recommendation/evaluation approval")
    if accepted == 0:
        blockers.append("No accepted complaint scenarios")
    elif accepted < 300 or scenarios.get("sealed_test", 0) < 80 or sum(outcomes.get(x, 0) for x in ("insufficient_information", "out_of_scope")) < 60:
        blockers.append("Final reviewed dataset target not met: 300 scenarios, 80 sealed-test cases and 60 abstentions")
    if train_sft_count < 3000:
        blockers.append(f"User's 3,000 training-format example target not met: {train_sft_count} eligible train SFT records; {3000 - train_sft_count} remaining")
    if labeled == 0 or possible == 0:
        blockers.append("No reviewed complaint-to-provision labels")
    if not scenarios.get("sealed_test", 0):
        blockers.append("No sealed test scenarios")
    required_actions = {"ask_followup", "suggest_provisions", "explain_uncertainty",
                        "refer_to_authorities", "offer_draft", "draft", "edit_draft",
                        "confirm_draft", "cancel_draft"}
    missing_actions = sorted(required_actions - train_actions.keys())
    if missing_actions:
        blockers.append("Missing reviewed conversation actions: " + ", ".join(missing_actions))
    thin_sections = [r["provision_id"] for r in coverage if r["train"] < 5 or r["sealed_test"] < 2]
    if thin_sections:
        blockers.append("Thin positive coverage (fewer than 5 train or 2 sealed-test examples): " + ", ".join(thin_sections))
    thin_actions = sorted(a for a in required_actions if train_actions.get(a, 0) < 3)
    if thin_actions:
        blockers.append("Thin train-split workflow coverage (fewer than 3 reviewed actions): " + ", ".join(thin_actions))
    if languages.get("hi-Latn", 0) < 20 or languages.get("hi", 0) < 20:
        blockers.append("Hindi language coverage below minimum inspection target: 20 Romanized Hindi and 20 Devanagari examples")
    if unreviewed_privacy or unreviewed_labels:
        blockers.append("Accepted scenarios still have privacy or label review gaps")
    if match_without_possible or abstention_with_possible or possible_blocked:
        blockers.append("Accepted scenario outcomes or positive labels conflict with reviewed provision coverage")
    if group_leaks:
        blockers.append("Scenario groups cross train/dev/test splits")
    if foreign_key_errors:
        blockers.append("Database foreign-key errors")
    dataset_audit = audit_dataset.audit()
    if not dataset_audit["pilot_split_ready"]:
        blockers.append("Pilot dataset split minimum not met: 70 train, 15 dev, 15 sealed-test accepted incidents")
    if accepted and dataset_audit["issues"]:
        blockers.append("Dataset audit found label, provenance, conversation or cross-split duplication issues")
    if external and not all(item["hash_valid"] for item in external):
        blockers.append("External candidate file hash mismatch")
    if additional and not all(item["hash_valid"] for item in additional):
        blockers.append("Additional candidate file hash mismatch")
    if additional_approved:
        blockers.append("Additional candidates bypassed source-grounded training review")
    if additional and set(additional_by_source) != {item["key"] for item in additional}:
        blockers.append("Additional candidate source manifest does not match indexed rows")

    report = {
        "as_of": date.today().isoformat(),
        "law_database": law,
        "training_examples": {
            "all_scenarios": all_scenarios,
            "train_sft_records": train_sft_count,
            "silver_train_rows": silver_train_rows,
            "silver_fact_pattern_families": silver_train_families,
            "dev_sft_records": dev_sft_count,
            "train_sft_target": 3000,
            "accepted_by_split": scenarios,
            "accepted_by_outcome": outcomes,
            "accepted_by_review_tier": review_tiers,
            "scenarios_with_any_label": labeled,
            "possible_label_rows": possible,
            "structured_fact_rows": fact_rows,
            "conversation_actions": actions,
            "train_conversation_actions": train_actions,
            "languages": languages,
            "positive_coverage_by_recommendable_section": coverage,
            "unreviewed_accepted_privacy": unreviewed_privacy,
            "unreviewed_accepted_labels": unreviewed_labels,
            "match_without_reviewed_possible": match_without_possible,
            "abstention_with_possible": abstention_with_possible,
            "possible_label_not_recommendable": possible_blocked,
            "split_group_leaks": len(group_leaks),
            "dataset_audit_issues": len(dataset_audit["issues"]),
        },
        "external_candidates": external,
        "additional_candidates": additional,
        "candidate_inventory": {
            "original_indexed_rows": original_candidate_rows,
            "additional_indexed_rows": additional_candidate_rows,
            "total_indexed_rows": original_candidate_rows + additional_candidate_rows,
            "additional_training_approved": additional_approved,
        },
        "ready_for_final_colab_training": not blockers,
        "blockers": blockers,
        "note": "The 3,000 SFT row target includes 2,760 silver synthetic actor/report-frame variants from 115 families. They were family-reviewed and mechanically audited, not independently legal-reviewed row by row; row count is not model-quality evidence. The Nyaya v3 case review accepted 24 further rows and held four. Other raw external rows and publisher labels are not training truth. Full-act readiness requires more than passing a 19-section pilot count.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
