"""Record source-checked commencement status for eight Jan Vishwas IT Act sections.

This is a status-only review. It never verifies display text or enables a section
for complaint suggestions. The amended section wording still needs text review.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, MANIFEST, sha256, validate_source_files


# MeitY's 3 November 2023 memorandum, Schedule item 32 and Annexure V, identifies
# these amendments and states that they commenced on 30 November 2023.
EVIDENCE = {
    "ITA_33": ("five lakh rupees", "Schedule item 32(A); surrender-of-licence penalty"),
    "ITA_44": ("fifteen lakh", "Schedule item 32(B); revised information-return penalties"),
    "ITA_45": ("one lakh rupees", "Schedule item 32(C); revised residual penalty"),
    "ITA_46": ("under this Act", "Schedule item 32(D); adjudicating-officer amendment"),
    "ITA_67C": ("twenty-five lakh rupees", "Schedule item 32(F); revised retention penalty"),
    "ITA_68": ("twenty-five lakh", "Schedule item 32(G); revised Controller-direction penalty"),
    "ITA_72": ("five lakh rupees", "Schedule item 32(J); revised confidentiality penalty"),
    "ITA_72A": ("twenty-five lakh rupees", "Schedule item 32(K); revised contract-disclosure penalty"),
}


def main() -> None:
    validate_source_files()
    sources = {item["source_id"]: item for item in MANIFEST["sources"]}
    memo = sources["ITA_JAN_VISHWAS_MEITY_MEMO_2023"]
    current = sources["ITA_INDIA_CODE_CURRENT_2026_09_16"]
    if sha256(ROOT / memo["path"]) != memo["sha256"]:
        raise ValueError("MeitY source hash changed")
    today = date.today().isoformat()
    reviewer = "Codex AI MeitY amendment status audit"
    report = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for pid, (fragment, citation) in EVIDENCE.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if (not row or row["source_id"] != current["source_id"] or
                    row["recommendable"] or row["legal_status"] not in ("pending_review", "in_force")):
                raise ValueError(f"Unexpected section state: {pid}")
            if fragment.casefold() not in row["extracted_text"].casefold():
                raise ValueError(f"Amended phrase absent from current India Code text: {pid}")
            note = ("MeitY office memorandum of 3 November 2023, " + citation +
                    ", says the Jan Vishwas IT Act amendment commenced 30 November 2023. "
                    "Status checked only; statutory text and provision kind remain separately gated.")
            if row["legal_status"] == "pending_review":
                conn.execute("""UPDATE provision SET legal_status='in_force',
                    status_reviewed_on=?, reviewed_by=?, review_note=? WHERE provision_id=?""",
                    (today, reviewer, note, pid))
            else:
                if row["review_note"] != note:
                    raise ValueError(f"Existing status review differs: {pid}")
            report.append({"provision_id": pid, "status": "in_force",
                           "current_text_source_id": row["source_id"],
                           "current_text_pdf_page": row["source_pdf_page"],
                           "current_extraction_sha256": hashlib.sha256(row["extracted_text"].encode("utf-8")).hexdigest(),
                           "amendment_source_id": memo["source_id"],
                           "amendment_source_sha256": memo["sha256"],
                           "effective_date": "2023-11-30", "evidence": citation,
                           "text_verified_by_this_review": False,
                           "recommendable_by_this_review": False})
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key check failed")
        conn.commit()
    output = ROOT / "it_jan_vishwas_status_audit.json"
    result = {"reviewed_on": today, "reviewer": reviewer,
              "official_amendment_url": memo["url"], "entries": report,
              "note": "Status-only AI review of eight amended sections. No text or complaint-label approval."}
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status_reviewed": len(report), "text_approved": 0,
                      "recommendations_enabled": 0, "report": str(output)}, indent=2))


if __name__ == "__main__":
    main()
