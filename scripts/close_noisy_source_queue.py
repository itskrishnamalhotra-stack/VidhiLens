"""Resolve the 3,544-row complaint-source intake using row review decisions."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "review_automation" / "complaint_pool_v2"
DB = ROOT / "db" / "master_dataset.sqlite"


def main() -> None:
    reviewed_path = AUDIT / "remaining_1338_review" / "decisions.csv"
    reviewed = {int(r["source_row"]): r for r in csv.DictReader(
        reviewed_path.open(encoding="utf-8", newline=""))} if reviewed_path.exists() else {}
    priority = {int(r["source_row"]): r for r in csv.DictReader(
        (AUDIT / "priority_source_decisions.csv").open(encoding="utf-8", newline=""))}
    conn = sqlite3.connect(DB)
    old = {(s, n): d for s, n, d in conn.execute(
        "SELECT source_key,row_number,decision FROM public_candidate_review")}
    conn.close()
    rows, counts = [], Counter()
    for row in csv.DictReader((AUDIT / "row_audit.csv").open(encoding="utf-8", newline="")):
        source, number = row["source"], int(row["row_number"])
        if source == "statutory_triage" and number in reviewed:
            decision = reviewed[number]["decision"]
            basis = "AI_batch_fact_to_law_review"
        elif (source, number) in old:
            decision = old[(source, number)]
            basis = "earlier_individual_case_review"
        elif source == "statutory_triage" and number in priority:
            decision = priority[number]["decision"]
            basis = "individual_fact_to_law_review"
        elif row["disposition"] == "semantic_review_needed":
            decision = "excluded_source_mapping_quality"
            basis = "source_level_rejection_not_individual_legal_review"
        else:
            decision = "excluded_structural_or_task_mismatch"
            basis = "row_level_automated_screen_not_individual_legal_review"
        counts[(source, decision, basis)] += 1
        rows.append({"source": source, "row_number": number,
                     "input_sha256": row["input_sha256"], "decision": decision,
                     "basis": basis, "flags": row["flags"],
                     "source_label": row["publisher_labels"]})
    if len(rows) != 3544: raise ValueError(f"Unexpected source count: {len(rows)}")
    with (AUDIT / "final_training_dispositions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary = {
        "all_intake_rows_accounted_for": len(rows),
        "remaining_unassigned_training_dispositions": 0,
        "decisions": [{"source": s, "decision": d, "basis": b, "count": n}
                      for (s, d, b), n in sorted(counts.items())],
        "warning": "Only positive and clarification research cases are supervised targets. Challenge and duplicate rows remain unlabelled and must not be counted as supervised training.",
        "source_quality_examples": [
            {"row": 112, "problem": "A generic cheating report was labelled BNS 217, which concerns false information intended to misuse a public servant's power."},
            {"row": 250, "problem": "A child being told to hurt someone was labelled BNS 123, which concerns hurt by poison or similar means."},
            {"row": 768, "problem": "A person feeling sick after a drink was labelled BNS 355, which concerns drunken misconduct in public."},
            {"row": 1935, "problem": "A forced-activity account was labelled BNS 202, which concerns a public servant unlawfully engaging in trade."},
        ],
    }
    (AUDIT / "final_training_dispositions_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__": main()
