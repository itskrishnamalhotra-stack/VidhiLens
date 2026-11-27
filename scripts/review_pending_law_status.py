"""Record source-grounded commencement decisions separately from text review.

This deliberately leaves verified_text and recommendable untouched. A current
consolidation and commencement evidence establish status, but do not certify
that the PDF extraction is clean enough to quote to users.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, validate_source_files


DPDP_URL = "https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf"
DPDP_PATH = ROOT / "sources" / "dpdp_2025_commencement_gsr_843e.pdf"
DPDP_SHA256 = "6df25cd8c76ac8eb18cae81835d51d51128ffbf2ed13262843395efddf0998e5"
BNS_NOTICE_URL = "https://www.mha.gov.in/sites/default/files/BhartiyaNyayaSanhita_24022024.pdf"
MEITY_COMMENCEMENT_URL = "https://www.meity.gov.in/documents/orders-and-notices/rules-for-information-technology-act-2000-YDO5AjMtQWa?pageTitle=Rules-for-Information-Technology-Act-2000"


def main() -> None:
    validate_source_files()
    assert hashlib.sha256(DPDP_PATH.read_bytes()).hexdigest() == DPDP_SHA256
    today = date.today().isoformat()
    reviewed = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        rows = conn.execute("""SELECT p.*, s.url, s.sha256 FROM provision p
            JOIN source_snapshot s ON s.source_id=p.source_id
            WHERE p.legal_status='pending_review' ORDER BY p.provision_id""").fetchall()
        for row in rows:
            pid = row["provision_id"]
            if pid == "BNS_106":
                assert conn.execute("""SELECT legal_status FROM provision_subpart_status
                    WHERE provision_id='BNS_106' AND subpart='(2)'""").fetchone()[0] == "uncommenced"
                status = "in_force"
                note = ("Section 106(1) commenced 2024-07-01; 106(2) is expressly excepted "
                        "by MHA S.O. 850(E). Whole-section recommendation remains disabled. "
                        "Text still needs separate review. " + BNS_NOTICE_URL)
                evidence = [BNS_NOTICE_URL]
            elif row["act_id"] == "ITA_2000":
                # All pending ITA entries are printed as live provisions in the
                # pinned current India Code consolidation, with no omission label.
                # Most are procedural/support sections, not complaint offences.
                assert row["source_id"] == "ITA_INDIA_CODE_CURRENT_2026_09_16"
                assert row["extracted_text"] and "omitted" not in row["candidate_title"].casefold()
                assert pid not in {"ITA_66A", "ITA_72A"}
                status = "in_force"
                evidence = [row["url"], MEITY_COMMENCEMENT_URL]
                note = ("Printed as a current provision in the pinned India Code IT Act "
                        "consolidation; IT Act commencement confirmed by MeitY. "
                        "This status decision does not approve extracted text or recommendation.")
                if pid == "ITA_43A":
                    evidence.append(DPDP_URL)
                    note += (" DPDP Act section 44(2), which will omit ITA 43A, starts "
                             "18 months after the 2025-11-13 Gazette publication under "
                             "G.S.R. 843(E); it is not yet in force on this review date.")
            else:
                raise ValueError(f"Unanticipated pending provision: {pid}")
            conn.execute("""UPDATE provision SET legal_status=?, status_reviewed_on=?,
                reviewed_by=COALESCE(reviewed_by,'Codex AI official-source status review'),
                review_note=?, recommendable=0 WHERE provision_id=?""",
                (status, today, note, pid))
            reviewed.append({"provision_id": pid, "legal_status": status,
                             "source_id": row["source_id"], "source_pdf_page": row["source_pdf_page"],
                             "extracted_text_sha256": hashlib.sha256(row["extracted_text"].encode()).hexdigest(),
                             "evidence_urls": evidence, "note": note,
                             "verified_text_changed": False, "recommendable": False})
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign-key errors")
        conn.commit()
    out = ROOT / "data_drafts" / "pending_law_status_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "reviewed_count": len(reviewed),
                               "dpdp_notice_sha256": DPDP_SHA256, "entries": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Status reviewed: {len(reviewed)}; text and recommendations unchanged: {out}")


if __name__ == "__main__":
    main()
