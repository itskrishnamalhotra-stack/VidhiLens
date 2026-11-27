"""Classify the BNS general/sentencing/exception/abetment chapters by section."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT


KIND = {3: "definition", **{n: "other" for n in range(4, 14)},
        **{n: "exception" for n in range(14, 34)},
        **{n: "exception" for n in range(35, 45)},
        45: "definition", 46: "definition",
        **{n: "other" for n in range(47, 55)},
        62: "offence"}


def main():
    reviewed = []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for number, kind in sorted(KIND.items()):
            pid = f"BNS_{number}"
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["legal_status"] == "in_force"
            if row["provision_kind"] != "pending_review":
                continue
            if not row["verified_text"]:
                continue
            title = row["candidate_title"]
            # The explicit range is the BNS general principles portion. A
            # title check stops this map if a future consolidation renumbers it.
            if kind == "exception" and not any(word in title.casefold() for word in
                    ("act ", "right ", "consent", "harm", "defence", "offence", "accident", "judge", "communication", "child", "person", "exclusion", "commencement", "when such")):
                raise ValueError(f"Unexpected exception title: {pid}: {title}")
            note = ((row["review_note"] or "") + " " +
                    f"Kind {kind} reviewed from BNS general-principles chapter and section text; "
                    "recommendation remains disabled.").strip()
            conn.execute("""UPDATE provision SET provision_kind=?,review_note=?,
                recommendable=0 WHERE provision_id=?""", (kind, note, pid))
            reviewed.append({"provision_id": pid, "kind": kind, "title": title,
                             "official_source_id": row["source_id"],
                             "pdf_page": row["source_pdf_page"],
                             "verified_text_sha256": hashlib.sha256(row["verified_text"].encode()).hexdigest(),
                             "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_general_kind_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"classified": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
