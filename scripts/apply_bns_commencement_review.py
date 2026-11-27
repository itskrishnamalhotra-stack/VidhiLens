"""Record the Act-wide BNS commencement notice without approving unverified text.

S.O. 850(E) starts all BNS provisions except section 106(2) on 1 July 2024.
This bulk decision addresses commencement only. It does not classify offences,
verify extracted section text, or make any section recommendable.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import fitz

from build_full_kb import DB_PATH, ROOT, MANIFEST, sha256


SOURCE_ID = "BNS_COMMENCEMENT_SO_850E_2024"
REVIEWER = "Codex AI Act-wide commencement notice review"
NOTE = (
    "Act-wide commencement: MHA S.O. 850(E), 23 February 2024, appoints "
    "1 July 2024 for BNS provisions except section 106(2). "
    "This is a commencement/status decision only; section text and kind remain "
    "unverified and the provision is not enabled for complaint suggestions. "
    "Later central or state amendments need separate review."
)


def main() -> None:
    source = next(s for s in MANIFEST["sources"] if s["source_id"] == SOURCE_ID)
    path = ROOT / source["path"]
    if sha256(path) != source["sha256"]:
        raise SystemExit("Pinned commencement notice hash mismatch")
    with fitz.open(path) as pdf:
        page_text = " ".join(pdf[1].get_text().split())
    expected = (
        "1st day of July, 2024 as the date on which the provisions of the said "
        "Sanhita, except the provision of sub-section (2) of section 106, "
        "shall come into force."
    )
    if expected not in page_text:
        raise SystemExit("Pinned notice does not contain the expected exception")

    reviewed_on = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("SELECT count(*) FROM provision WHERE act_id='BNS_2023'").fetchone()[0] != 358:
            raise SystemExit("BNS section index is incomplete")
        exception = conn.execute(
            "SELECT legal_status FROM provision_subpart_status WHERE provision_id='BNS_106' AND subpart='(2)' AND source_id=?",
            (SOURCE_ID,),
        ).fetchone()
        if exception != ("uncommenced",):
            raise SystemExit("BNS 106(2) exception missing")
        rows = conn.execute("""SELECT provision_id, review_note FROM provision
            WHERE act_id='BNS_2023' AND provision_id!='BNS_106'
            AND legal_status='pending_review' ORDER BY provision_id""").fetchall()
        if len(rows) not in (0, 325):
            raise SystemExit(f"Unexpected partial BNS status batch: {len(rows)}")
        for provision_id, old_note in rows:
            conn.execute("""UPDATE provision SET legal_status='in_force',
                status_reviewed_on=?, reviewed_by=?, review_note=?
                WHERE provision_id=? AND legal_status='pending_review'""",
                (reviewed_on, REVIEWER, (old_note or "") + " " + NOTE, provision_id),
            )
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Foreign key error")
        conn.commit()
        assert conn.execute("""SELECT count(*) FROM provision WHERE act_id='BNS_2023'
            AND legal_status='pending_review'""").fetchone()[0] == 1
        assert conn.execute("""SELECT count(*) FROM provision WHERE act_id='BNS_2023'
            AND provision_id!='BNS_106' AND legal_status='in_force'""").fetchone()[0] == 357
    report = {
        "reviewed_on": reviewed_on,
        "reviewer": REVIEWER,
        "source_id": SOURCE_ID,
        "source_sha256": source["sha256"],
        "visually_checked_pdf_page": 2,
        "commencement_date": "2024-07-01",
        "commenced_bns_sections": 357,
        "newly_classified": len(rows),
        "mixed_status_section": "BNS_106",
        "uncommenced_subpart": "BNS_106(2)",
        "scope_limit": "Commencement only, not section-text, provision-kind, subsequent-amendment, or recommendation review.",
    }
    out = ROOT / "bns_commencement_bulk_review.json"
    if out.exists():
        prior = json.loads(out.read_text(encoding="utf-8"))
        if (prior["source_sha256"] != source["sha256"] or
                prior["commenced_bns_sections"] != 357 or
                prior["uncommenced_subpart"] != "BNS_106(2)"):
            raise SystemExit("Existing bulk review report conflicts with source or exception")
        report = prior
    else:
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
