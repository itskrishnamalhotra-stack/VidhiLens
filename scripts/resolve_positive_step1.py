"""Record a final disposition for the 524 originally held triage rows.

The 263 source-checked floor patterns are supplemental synthetic positives.
The other rows stay in the research archive and are not silently promoted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
HELD = ROOT / "review_automation" / "training_readiness_v1" / "weak_triage.csv"
EXCEPTIONS = ROOT / "data_drafts" / "floor_review_exceptions_v1.json"
OUT = ROOT / "review_automation" / "positive_step1_v1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    held = list(csv.DictReader(HELD.open(encoding="utf-8", newline="")))
    exceptions = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    floor = [r for r in held if r["source_id"].startswith("section-floor-")]
    if len(held) != 524 or len(floor) != 269 or len(exceptions) != 6:
        raise ValueError("Original review queue or exception count changed")
    if not set(exceptions).issubset({r["source_id"] for r in floor}):
        raise ValueError("Exception references a non-floor row")

    rows = []
    accepted_floor = []
    with sqlite3.connect(DB) as conn:
        for row in held:
            ids = row["possible_provision_ids"].split("|") if row["possible_provision_ids"] else []
            if row["source_id"].startswith("section-floor-"):
                if len(ids) != 1:
                    raise ValueError(f"Floor row lacks one target: {row['source_id']}")
                provision_id = ids[0]
                law = conn.execute("""SELECT source_id,source_pdf_page,verified_text,
                    legal_status,provision_kind FROM provision WHERE provision_id=?""",
                    (provision_id,)).fetchone()
                if not law or law[3:] != ("in_force", "offence") or not law[2]:
                    raise ValueError(f"Floor row targets ineligible law: {row['source_id']}")
                if row["source_id"] in exceptions:
                    decision = "withhold_statutory_gap"
                    reason = exceptions[row["source_id"]]
                else:
                    decision = "accept_supplemental_research_positive"
                    reason = ("Reported act and asserted required facts were checked against the "
                              "verified provision; concise synthetic case, research use only.")
                    accepted_floor.append(row["source_id"])
                law_source, page = law[0], law[1]
                law_hash = hashlib.sha256(law[2].encode()).hexdigest()
            else:
                provision_id = "|".join(ids)
                decision = "withhold_short_source_row"
                reason = ("Not promoted into the complaint-positive core: the short source row "
                          "has not passed an individual element/exception check. Preserve for "
                          "separate later use only after such a check.")
                law_source = page = law_hash = ""
            rows.append({"source_id": row["source_id"], "provision_id": provision_id,
                         "split": row["split"], "decision": decision, "reason": reason,
                         "law_source_id": law_source, "law_pdf_page": page,
                         "verified_text_sha256": law_hash,
                         "complaint": row["complaint"]})
    if len(accepted_floor) != 263:
        raise ValueError("Accepted floor count changed")
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "ledger.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "accepted_floor_ids.json").write_text(
        json.dumps(sorted(accepted_floor), indent=2) + "\n", encoding="utf-8")
    summary = {"original_held_rows": len(held),
               "decisions": dict(Counter(r["decision"] for r in rows)),
               "limits": ["AI source review of synthetic research examples is not independent legal certification.",
                          "Short source rows were conservatively withheld, not labelled legally false."],
               "input_sha256": {"held": sha(HELD), "exceptions": sha(EXCEPTIONS)},
               "output_sha256": {"ledger": sha(OUT / "ledger.csv"),
                                 "accepted_floor_ids": sha(OUT / "accepted_floor_ids.json")}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
