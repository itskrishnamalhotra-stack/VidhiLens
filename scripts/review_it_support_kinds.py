"""Classify source-checked IT Act support provisions without enabling suggestions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT


KINDS = {
    "civil_penalty": {"43A"},
    "definition": {"14", "15"},
    "exception": {"9", "79"},
    "power": {"10", "16", "17", "18", "19", "27", "28", "29", "70A", "79A", "80", "83", "84A", "86", "89"},
    "procedure": {"3", "3A", "6", "6A", "7", "8", "22", "23", "24", "25", "26", "32",
                  "37", "38", "39", "40A", "41", "47", "52D", "55", "57", "58", "59",
                  "62", "63", "64", "76", "77A", "77B"},
}


def main():
    today = date.today().isoformat()
    out = ROOT / "data_drafts/it_support_kind_review_20260918.json"
    classified = json.loads(out.read_text(encoding="utf-8"))["accepted"] if out.exists() else []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        rows = conn.execute("""SELECT * FROM provision WHERE act_id='ITA_2000'
            AND legal_status='in_force' AND provision_kind='pending_review'
            AND verified_text IS NOT NULL ORDER BY CAST(section_number AS INTEGER),section_number""").fetchall()
        for row in rows:
            number = row["section_number"]
            matches = [kind for kind, numbers in KINDS.items() if number in numbers]
            if len(matches) > 1:
                raise ValueError(f"Conflicting kind assignments: {number}")
            kind = matches[0] if matches else "other"
            # This pass covers electronic-record, certification, tribunal,
            # enforcement-power and general-support sections. Standalone IT
            # offences were classified in the earlier priority law reviews.
            assert row["verified_text"].startswith(number + ".")
            if "shall be punished" in row["verified_text"].casefold() or "shall be punishable" in row["verified_text"].casefold():
                raise ValueError(f"Possible offence in support queue: {row['provision_id']}")
            note = ((row["review_note"] or "") + " " +
                    f"IT Act source-checked support provision classified as {kind}; "
                    "not a standalone complaint recommendation. ").strip()
            conn.execute("""UPDATE provision SET provision_kind=?,review_note=?,
                recommendable=0 WHERE provision_id=?""", (kind, note, row["provision_id"]))
            classified.append({"provision_id": row["provision_id"], "kind": kind,
                               "title": row["candidate_title"],
                               "official_source_id": row["source_id"],
                               "pdf_page": row["source_pdf_page"],
                               "verified_text_sha256": hashlib.sha256(row["verified_text"].encode()).hexdigest(),
                               "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out.write_text(json.dumps({"reviewed_on": today, "accepted": classified},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classified": len(classified), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
