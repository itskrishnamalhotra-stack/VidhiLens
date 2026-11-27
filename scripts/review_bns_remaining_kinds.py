"""Apply explicit BNS kind decisions for the remaining source-checked sections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT


DECISIONS = {
    "definition": {63, 100, 101, 128, 129, 130, 169, 170, 171, 172,
                   227, 228, 270, 330, 335, 345},
    "offence": {72, 91, 123, 160, 161, 162, 163, 165, 166, 192, 200,
                204, 205, 225, 238, 246, 249, 250, 251, 252, 257, 268,
                298, 321, 349, 350},
    "other": {102, 167, 190, 358},
}


def main():
    ids = [n for group in DECISIONS.values() for n in group]
    assert len(ids) == len(set(ids))
    today = date.today().isoformat()
    reviewed = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT * FROM provision WHERE act_id='BNS_2023'
            AND provision_kind='pending_review' AND verified_text IS NOT NULL""").fetchall()
        current = {int(r["section_number"]): r for r in rows}
        if set(current) != set(ids):
            raise ValueError({"unmapped": sorted(set(current) - set(ids)),
                              "stale": sorted(set(ids) - set(current))})
        for kind, numbers in DECISIONS.items():
            for number in sorted(numbers):
                row = current[number]
                note = ((row["review_note"] or "") + " " +
                        f"Explicit BNS section-kind review: {kind}; no complaint recommendation approved.").strip()
                conn.execute("""UPDATE provision SET provision_kind=?,review_note=?,recommendable=0
                    WHERE provision_id=?""", (kind, note, row["provision_id"]))
                reviewed.append({"provision_id": row["provision_id"], "title": row["candidate_title"],
                                 "kind": kind, "source_id": row["source_id"],
                                 "source_pdf_page": row["source_pdf_page"],
                                 "verified_text_sha256": hashlib.sha256(row["verified_text"].encode()).hexdigest(),
                                 "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_remaining_kind_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classified": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
