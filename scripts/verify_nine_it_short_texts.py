"""Source-check nine bounded IT Act sections against rendered India Code pages.

The reviewed text deliberately preserves PDF amendment markers and the same
replacement-glyph convention used by the existing IT Act source transcriptions.
It is a source-check flag, not a recommendation or a cleaned UI rendering.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


# The entire section, including amendments, was visually compared against the
# pinned source pages. Hashes lock each exact extraction reviewed here.
CHECKED = {
    "ITA_33": (16, "544bb6d63b5274b6288cdbbc1d1e36a8cac82a1a3060bb53f4904121be3b4c0c"),
    "ITA_44": (20, "68222365177c4f7bcafd46f85a79812f775b2b7e0b6eb2e516c8f362a1b91b2d"),
    "ITA_45": (20, "d415ab4d7111df97fb2912c18494b6bbf19dfa901124a8f27968e395d426b02a"),
    "ITA_48": (21, "648e8daceb51d2d355addd19202b60c595d248af570750f8caf1376a7c36cead"),
    "ITA_60": (23, "0f1700e153f70346c76c125cc15318374f2f5f01910e02995bf59aa191d1f370"),
    "ITA_61": (23, "522f521ffd528aa031ae6a399fe7cef3c0026ebee3bb18d93c99f60f2f8b5f42"),
    "ITA_67C": (26, "e900b3c28707650ceb9fd2d9adb08f9f999a27a06f9076790b143c36581aac17"),
    "ITA_68": (26, "e1bdd1ae7c88e107740b80e4cc2527a2465effc05fbc4f2391a605e2e3f47848"),
    "ITA_72": (28, "32bbc5400a763be4c03eef0ae0bf937339ab0a5b831abf48b1b1f0a8e7ec0505"),
}


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    ledger = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for pid, (page, expected_hash) in CHECKED.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            if (row is None or row["verified_text"] is not None
                    or row["source_pdf_page"] != page or row["recommendable"]):
                raise ValueError(f"Unexpected state for {pid}")
            raw = row["extracted_text"]
            digest = hashlib.sha256(raw.encode()).hexdigest()
            if digest != expected_hash or not raw.startswith(pid.split("_", 1)[1] + "."):
                raise ValueError(f"Unexpected source extraction for {pid}")
            if not raw.rstrip().endswith((".", ".]")):
                raise ValueError(f"Potentially incomplete section {pid}")
            note = (row["review_note"] or "") + (
                f" Entire extracted section visually source-checked against pinned India Code PDF p.{page}. "
                "PDF amendment markers and replacement glyphs retained; no complaint recommendation approved."
            )
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                reviewed_by=?,review_note=? WHERE provision_id=? AND verified_text IS NULL
                AND recommendable=0""",
                (raw, today, "Codex AI rendered-PDF section check", note, pid))
            ledger.append({"provision_id": pid, "source_id": row["source_id"],
                           "pdf_page": page, "verified_text_sha256": digest,
                           "recommendable": False})
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key error")
        conn.commit()
    out = ROOT / "data_drafts" / f"nine_it_short_text_review_{today.replace('-', '')}.json"
    out.write_text(json.dumps({"reviewed_on": today, "rows": ledger}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": len(ledger), "ledger": str(out)}, indent=2))


if __name__ == "__main__":
    main()
