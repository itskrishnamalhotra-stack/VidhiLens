"""Classify the last 17 IT Act entries by their pinned source text.

This pass changes only provision_kind and its review note. It does not verify
the extracted section text or approve any complaint recommendation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


# The official India Code consolidation pages were inspected as rendered PDF
# pages. MeitY's amended-provision table controls the later correction of
# sections 33 and 68: section 33 is a penalty, while section 68 has mixed
# offence/penalty wording and stays outside the complaint-offence pool.
DECISIONS = {
    "ITA_2": ("definition", 5, "Act-wide definitions."),
    "ITA_31": ("other", 15, "Compliance duty of Certifying Authority."),
    "ITA_33": ("civil_penalty", 16, "MeitY's amended-provision table states monetary penalty; consolidation retains older offence wording."),
    "ITA_34": ("other", 16, "Disclosure duty of Certifying Authority."),
    "ITA_36": ("other", 16, "Certificate representation duty."),
    "ITA_44": ("civil_penalty", 20, "Failure-to-furnish monetary penalties."),
    "ITA_45": ("civil_penalty", 20, "Residuary monetary penalty and compensation."),
    "ITA_46": ("power", 20, "Adjudicating officer jurisdiction and powers."),
    "ITA_48": ("procedure", 21, "Appellate Tribunal establishment and jurisdiction."),
    "ITA_60": ("procedure", 23, "Limitation rule for an appeal."),
    "ITA_61": ("procedure", 23, "Civil court jurisdiction exclusion."),
    "ITA_67C": ("civil_penalty", 26, "Intermediary retention duty and monetary penalty."),
    "ITA_68": ("other", 26, "Controller power with mixed offence/monetary-penalty wording; hold complaint-offence classification."),
    "ITA_72": ("civil_penalty", 28, "Confidentiality contravention carries monetary penalty."),
    "ITA_78": ("power", 30, "Police investigative authority."),
    "ITA_87": ("power", 32, "Central Government rule-making authority."),
    "ITA_88": ("procedure", 34, "Cyber Regulations Advisory Committee constitution."),
}


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    ledger = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        pending = {row[0] for row in conn.execute(
            "SELECT provision_id FROM provision WHERE provision_kind='pending_review'"
        )}
        if pending != set(DECISIONS):
            raise ValueError(f"Unexpected pending-kind IDs: {sorted(pending ^ set(DECISIONS))}")
        for pid, (kind, page, reason) in DECISIONS.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if (row["act_id"] != "ITA_2000" or row["legal_status"] != "in_force"
                    or row["source_pdf_page"] != page or row["recommendable"]):
                raise ValueError(f"Source/status mismatch for {pid}")
            raw = row["extracted_text"]
            if not raw.startswith(pid.split("_", 1)[1] + "."):
                raise ValueError(f"Extracted text heading mismatch for {pid}")
            if kind == "offence" and "guilty of an offence" not in raw.casefold():
                raise ValueError(f"Offence wording missing for {pid}")
            note = (row["review_note"] or "") + (
                f" Kind review against pinned India Code PDF p.{page}: {reason} "
                "Extracted text remains unverified; no recommendation approved."
            )
            conn.execute("""UPDATE provision SET provision_kind=?,review_note=?
                            WHERE provision_id=? AND provision_kind='pending_review'
                            AND recommendable=0""", (kind, note, pid))
            ledger.append({
                "provision_id": pid, "kind": kind, "pdf_page": page,
                "source_id": row["source_id"], "reason": reason,
                "extracted_text_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "text_verified": False, "recommendable": False,
            })
        if conn.execute("SELECT count(*) FROM provision WHERE provision_kind='pending_review'").fetchone()[0]:
            raise ValueError("Pending kind remained")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key error")
        conn.commit()
    out = ROOT / "data_drafts" / f"remaining_it_kind_review_{today.replace('-', '')}.json"
    out.write_text(json.dumps({"reviewed_on": today, "rows": ledger}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classified": len(ledger), "ledger": str(out)}, indent=2))


if __name__ == "__main__":
    main()
