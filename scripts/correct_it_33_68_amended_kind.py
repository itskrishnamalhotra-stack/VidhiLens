"""Correct two IT Act kinds after checking MeitY's amended-provision table.

Section 33 is a monetary penalty in the amended table. Section 68 combines a
Controller power with an anomalous retained 'offence' phrase and a monetary
penalty; hold it out of complaint-offence supervision pending legal resolution.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


DECISIONS = {
    "ITA_33": ("civil_penalty", 16, "544bb6d63b5274b6288cdbbc1d1e36a8cac82a1a3060bb53f4904121be3b4c0c",
               "MeitY Jan Vishwas amended-provision table (Annexure V) prints liability to monetary penalty without the former guilty-of-an-offence phrase."),
    "ITA_68": ("other", 26, "e1bdd1ae7c88e107740b80e4cc2527a2465effc05fbc4f2391a605e2e3f47848",
               "MeitY Annexure V retains guilty-of-an-offence wording but substitutes monetary penalty; mixed classification held outside complaint-offence pool."),
}
MEITY_URL = "https://www.meity.gov.in/static/uploads/2024/03/MeitY-JVA-1.pdf"


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    ledger = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for pid, (kind, page, expected_hash, reason) in DECISIONS.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if (row is None or row["provision_kind"] != "offence"
                    or row["legal_status"] != "in_force" or row["recommendable"]
                    or row["source_pdf_page"] != page
                    or hashlib.sha256(row["verified_text"].encode()).hexdigest() != expected_hash):
                raise ValueError(f"Unexpected state for {pid}")
            conn.execute("UPDATE provision SET provision_kind=?, review_note=? WHERE provision_id=?",
                         (kind, (row["review_note"] or "") + " Correction: " + reason, pid))
            ledger.append({"provision_id": pid, "former_kind": "offence", "new_kind": kind,
                           "source_pdf_page": page, "reason": reason,
                           "verified_text_sha256": expected_hash,
                           "recommendable": False})
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key error")
        conn.commit()
    out = ROOT / "data_drafts" / f"it_33_68_kind_correction_{today.replace('-', '')}.json"
    out.write_text(json.dumps({"corrected_on": today, "meity_source": MEITY_URL,
                               "rows": ledger}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"corrected": len(ledger), "ledger": str(out)}, indent=2))


if __name__ == "__main__":
    main()
