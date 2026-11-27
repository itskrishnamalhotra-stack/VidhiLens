"""Classify source-checked BNS sections that explicitly prescribe punishment.

The classification records the operative penalty wording and does not enable
complaint recommendations or imply that training cases cover these offences.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT


PATTERN = re.compile(r"\bshall be punish(?:ed|able)\b", re.I)


def main():
    today = date.today().isoformat()
    reviewed = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        rows = conn.execute("""SELECT * FROM provision WHERE act_id='BNS_2023'
            AND legal_status='in_force' AND provision_kind='pending_review'
            AND verified_text IS NOT NULL ORDER BY CAST(section_number AS INTEGER)""").fetchall()
        for row in rows:
            match = PATTERN.search(row["verified_text"])
            if not match:
                continue
            pid = row["provision_id"]
            excerpt = row["verified_text"][max(0, match.start() - 90):match.end() + 90]
            # Each accepted entry has an operative penalty phrase in the
            # source-checked official section, rather than a publisher tag.
            note = ((row["review_note"] or "") + " " +
                    "Offence kind reviewed from operative 'shall be punished/punishable' "
                    "wording in the source-checked BNS section; no recommendation approval.").strip()
            conn.execute("""UPDATE provision SET provision_kind='offence',review_note=?,
                recommendable=0 WHERE provision_id=?""", (note, pid))
            reviewed.append({"provision_id": pid, "official_source_id": row["source_id"],
                             "pdf_page": row["source_pdf_page"],
                             "verified_text_sha256": hashlib.sha256(row["verified_text"].encode()).hexdigest(),
                             "operative_penalty_excerpt": excerpt,
                             "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_penalty_kind_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "kind": "offence",
                               "accepted": reviewed}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"classified_offence": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
