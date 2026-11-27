"""Prepare train-only open-ended fact-gap complaints for uncovered offence sections."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data_drafts" / "part2_remaining_fact_checks.psv"
AUDIT = ROOT / "review_automation" / "training_readiness_v5" / "per_section.csv"
OUT = ROOT / "data_drafts" / "coverage_batch16.json"


def main() -> None:
    if OUT.exists():
        raise ValueError("Output already exists; refuse to overwrite the Part 2 triage batch")
    missing = {row["provision_id"] for row in csv.DictReader(AUDIT.open(encoding="utf-8"))
               if int(row["candidate_train_missing_fact"]) == 0}
    if len(missing) != 243:
        raise ValueError(f"Expected 243 uncovered fact-gap sections, found {len(missing)}")
    cases = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        pid, known, gap, _ = line.split("|")
        if pid not in missing:
            continue
        complaint = (f"{known} {gap} The report is incomplete, and I can provide more details "
                     "about what happened if I am asked a specific follow-up question.")
        cases.append({"id": f"p2-triage-{pid}-u", "split": "train", "provision_id": pid,
                      "outcome": "insufficient_information", "input": complaint,
                      "missing_facts": gap.removeprefix("I do not know ").rstrip("."),
                      "review_note": "Section-specific AI-authored missing-fact case; research candidate only."})
    if len(cases) != 243 or {case["provision_id"] for case in cases} != missing:
        raise ValueError("Not all uncovered sections are represented exactly once")
    result = {"review_status": "AI_authored_part2_missing_fact_research_candidate",
              "scope": "Train-only open-ended triage missing-fact coverage for 243 previously uncovered offence sections",
              "case_targets": {pid: {"train_insufficient_information": 1} for pid in sorted(missing)},
              "cases": cases}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"batch": str(OUT), "cases": len(cases), "sections": len(missing)}, indent=2))


if __name__ == "__main__":
    main()
