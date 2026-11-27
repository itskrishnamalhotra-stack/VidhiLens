"""Write a concise, reproducible audit and next-work queue after review passes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import date

from build_full_kb import DB_PATH, ROOT, sha256


def main():
    reports = ["pending_law_status_review_20260918.json",
               "exact_law_text_review_20260918.json",
               "bns_layout_text_review_20260918.json",
               "it_editorial_text_review_20260918.json",
               "bns_heading_overflow_review_20260918.json",
               "bns_three_exception_review_20260918.json",
               "it_visual_two_review_20260918.json",
               "it_asterisk_marker_review_20260918.json",
               "it_visual_three_review_20260918.json",
               "bns_penalty_kind_review_20260918.json",
               "bns_general_kind_review_20260918.json",
               "bns_remaining_kind_review_20260918.json",
               "it_support_kind_review_20260918.json",
               "recommendation_release_gate_20260918.json"]
    packet_rows = {}
    for path in (ROOT / "review_automation/law_review_packets").glob("packet_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                p = json.loads(line)
                packet_rows[p["provision_id"]] = p
    pending_queue = []
    offence_queue = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        law = {"total": conn.execute("SELECT count(*) FROM provision").fetchone()[0],
               "verified_text": conn.execute("SELECT count(*) FROM provision WHERE verified_text IS NOT NULL").fetchone()[0],
               "pending_legal_status": conn.execute("SELECT count(*) FROM provision WHERE legal_status='pending_review'").fetchone()[0],
               "unverified_in_force_text": conn.execute("SELECT count(*) FROM provision WHERE legal_status='in_force' AND verified_text IS NULL").fetchone()[0],
               "kind_pending": conn.execute("SELECT count(*) FROM provision WHERE provision_kind='pending_review'").fetchone()[0],
               "recommendable": conn.execute("SELECT count(*) FROM recommendable_provision").fetchone()[0],
               "text_pinned_release_approvals": conn.execute("SELECT count(*) FROM recommendation_release_approval").fetchone()[0],
               "classified_offences_not_recommendable": conn.execute("SELECT count(*) FROM provision WHERE legal_status='in_force' AND provision_kind='offence' AND recommendable=0").fetchone()[0]}
        for row in conn.execute("""SELECT p.provision_id,p.candidate_title,p.act_id,
            p.source_pdf_page,p.source_id,p.extracted_text,s.url
            FROM provision p JOIN source_snapshot s USING(source_id)
            WHERE p.legal_status='in_force' AND p.verified_text IS NULL
            ORDER BY p.act_id,CAST(p.section_number AS INTEGER),p.section_number"""):
            p = packet_rows.get(row["provision_id"], {})
            pending_queue.append({"provision_id": row["provision_id"],
                                  "title": row["candidate_title"],
                                  "source_id": row["source_id"],
                                  "source_pdf_page": row["source_pdf_page"],
                                  "official_url": row["url"],
                                  "mechanical_flags": p.get("mechanical_flags", []),
                                  "second_parser_recall": p.get("second_parser_recall"),
                                  "required_action": "Compare the official PDF page visually, remove only proven layout/editorial artifacts, then record exact source text and kind; do not enable a suggestion without complaint evaluation."})
        for row in conn.execute("""SELECT p.provision_id,p.candidate_title,p.source_pdf_page,
            p.source_id,p.verified_text,s.url
            FROM provision p JOIN source_snapshot s USING(source_id)
            WHERE p.legal_status='in_force' AND p.provision_kind='offence'
              AND p.recommendable=0
            ORDER BY p.act_id,CAST(p.section_number AS INTEGER),p.section_number"""):
            offence_queue.append({"provision_id": row["provision_id"],
                                  "title": row["candidate_title"],
                                  "official_url": row["url"],
                                  "source_id": row["source_id"],
                                  "source_pdf_page": row["source_pdf_page"],
                                  "verified_text_sha256": (None if row["verified_text"] is None else
                                      hashlib.sha256(row["verified_text"].encode()).hexdigest()),
                                  "required_action": "Build distinct positive, confusable-negative and missing-fact complaint examples; review against this section and overlapping sections; assign train/dev/sealed groups; evaluate before enabling recommendations."})
        scenario_splits = dict(conn.execute("""SELECT split,count(*) FROM scenario
            WHERE quality_status='accepted' GROUP BY split"""))
        verified_by_act = dict(conn.execute("""SELECT act_id,count(*) FROM provision
            WHERE verified_text IS NOT NULL GROUP BY act_id"""))
        dev_gaps = [p for (p,) in conn.execute("SELECT provision_id FROM master_section_coverage WHERE dev_positive=0")]
        source_rows = conn.execute("SELECT count(*) FROM public_candidate_row").fetchone()[0] + conn.execute("SELECT count(*) FROM additional_candidate_row").fetchone()[0]
    assert len(pending_queue) == law["unverified_in_force_text"]
    queue_path = ROOT / "review_automation/remaining_law_text_20260918.jsonl"
    queue_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pending_queue), encoding="utf-8")
    offence_path = ROOT / "review_automation/full_act_offence_coverage_20260918.jsonl"
    offence_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in offence_queue), encoding="utf-8")
    readiness = json.loads((ROOT / "data_readiness_report.json").read_text(encoding="utf-8"))
    export_paths = sorted((ROOT / "exports").glob("scoped-pilot-*/manifest.json"))
    export = str(export_paths[-1].parent) if export_paths else None
    report = {"as_of": date.today().isoformat(), "sqlite_integrity": "ok",
              "foreign_key_errors": 0, "law": law, "verified_text_by_act": verified_by_act,
              "case_candidate_decisions": {"reviewed": 28, "accepted_train": 24,
                                           "possible": 12, "insufficient_information": 12,
                                           "held": 4},
              "accepted_scenarios_by_split": scenario_splits,
              "indexed_public_rows": source_rows,
              "development_positive_gaps_in_pilot": dev_gaps,
              "train_sft_records": readiness["training_examples"]["train_sft_records"],
              "silver_train_rows": readiness["training_examples"]["silver_train_rows"],
              "final_colab_training_ready": readiness["ready_for_final_colab_training"],
              "blockers": readiness["blockers"],
              "latest_scoped_pilot_export": export,
              "remaining_law_text_queue": str(queue_path),
              "full_act_offence_coverage_queue": str(offence_path),
              "review_ledger_sha256": {name: sha256(ROOT / "data_drafts" / name) for name in reports},
              "limitations": ["This is a 19-section pilot, not full BNS/IT offence coverage.",
                              "Large silver training count does not establish independent case diversity or model reliability.",
                              "No Colab training or unseen model evaluation has been run yet."]}
    out = ROOT / "review_automation/full_review_audit_20260918.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = (f"# Dataset review audit ({date.today().isoformat()})\n\n"
               f"- Official law entries: {law['total']}; source-checked text: {law['verified_text']}; status pending: {law['pending_legal_status']}.\n"
               f"- Text exceptions: {law['unverified_in_force_text']}; kind pending: {law['kind_pending']}; recommendable pilot sections: {law['recommendable']}.\n"
               f"- Indexed public rows: {source_rows}; accepted train/dev/sealed scenarios: {scenario_splits.get('train',0)}/{scenario_splits.get('dev',0)}/{scenario_splits.get('sealed_test',0)}.\n"
               f"- Reviewed 28 Nyaya candidates: 12 possible, 12 missing-fact, 4 held.\n"
               f"- Train-format SFT records: {report['train_sft_records']} (including {report['silver_train_rows']} silver variants).\n"
               f"- Pilot development sections with zero positive examples: {len(dev_gaps)}.\n"
               f"- Final full-Act export ready: {report['final_colab_training_ready']}.\n\n"
               "## Remaining work in order\n\n"
               "1. Resolve the section-text exceptions in the JSONL queue against the official PDF pages.\n"
               "2. Classify the pending section kinds; decide which in-force offences need complaint coverage.\n"
               "3. Author and review distinct cases and held multi-provision cases for new offences, then build a separate unseen evaluation set.\n"
               "4. Re-run audits; export the full dataset only when the full-Act gate passes. The scoped pilot export may be used earlier for a limited experiment.\n")
    (ROOT / "review_automation/FULL_REVIEW_AUDIT_20260918.md").write_text(summary, encoding="utf-8")
    print(json.dumps({"law": law, "train_sft": report["train_sft_records"],
                      "final_ready": report["final_colab_training_ready"],
                      "audit": str(out)}, indent=2))


if __name__ == "__main__":
    main()
