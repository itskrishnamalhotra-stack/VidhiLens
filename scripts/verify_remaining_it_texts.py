"""Verify the nine remaining IT Act transcriptions from rendered source pages.

Only page footers, amendment footnotes and neighbouring chapter headings are
removed. The source's amendment-marked statutory wording is preserved.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


EXPECTED = {
    "ITA_2": ("abf7121fac14afa45c0a3cfa3ed61f165a5d3f33bafa6f75ef683ab56a7c9b26", [5, 6, 7, 8]),
    "ITA_31": ("76794f7eff167e732aebb0b5aa67f2527062fca5f5d9976439974ecd13765d85", [15]),
    "ITA_34": ("eebf51fc04482b03bba52a912de413c4896991fd86e220457d83f27871d17710", [16]),
    "ITA_36": ("a9e2739332525c6e2aa1936057d8c4a817a87021cd2fdcb19fe23871dd019f96", [16, 17]),
    "ITA_46": ("102b6db73c0ab372e0abf88d6f33396be21b6a14bcacd7aa00cf9fcb665a87ce", [20, 21]),
    "ITA_72A": ("2f2a756a7bf1ab108a96a16e35f480eb4aa00f343e1010b9cdd899deca0f827e", [28, 29]),
    "ITA_78": ("8b863fa252d10adedea80380bffcdf7415b2bb5c8ddbba7843ce299da87f7545", [30]),
    "ITA_87": ("c38492178a9381639c4c03482145fcf1b3d52d90818735cc15f2808aa449a562", [32, 33, 34]),
    "ITA_88": ("8299b7fc8b11a2b8684212290ef0fd2d3c10324d44db99a6d6528a1e0d202026", [34, 35]),
}

# One-based line numbers in the pinned extracted text. They correspond to page
# footnotes, page numbers, editorial omission stars, or adjacent headings seen
# in the rendered official pages. Legal clauses on either side are retained.
DROP = {
    "ITA_2": set(range(9, 13)) | set(range(52, 57)) | set(range(59, 65))
             | set(range(111, 115)) | {134, 135},
    "ITA_31": set(range(4, 10)),
    "ITA_34": {13, 14},
    "ITA_36": set(range(6, 12)),
    "ITA_46": set(range(13, 23)),
    "ITA_72A": set(range(4, 10)),
    "ITA_78": {4, 5},
    "ITA_87": set(range(4, 8)) | set(range(53, 64)),
    "ITA_88": set(range(11, 17)),
}


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    ledger = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        remaining = {row[0] for row in conn.execute(
            "SELECT provision_id FROM provision WHERE legal_status='in_force' AND verified_text IS NULL"
        )}
        if remaining != set(EXPECTED):
            raise ValueError(f"Unexpected remaining set: {sorted(remaining ^ set(EXPECTED))}")
        for pid, (expected_hash, pages) in EXPECTED.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            raw = row["extracted_text"]
            if hashlib.sha256(raw.encode()).hexdigest() != expected_hash:
                raise ValueError(f"Extraction changed for {pid}")
            lines = raw.splitlines()
            if max(DROP[pid], default=0) > len(lines):
                raise ValueError(f"Drop index out of bounds for {pid}")
            text = "\n".join(line for i, line in enumerate(lines, 1) if i not in DROP[pid]).strip()
            if pid == "ITA_72A":
                if not text.startswith("4[72A.") or not text.endswith("].]"):
                    raise ValueError("ITA_72A amendment wrapper changed")
                text = text[2:-1]
            if not text.startswith(pid.split("_", 1)[1] + "."):
                raise ValueError(f"Heading mismatch for {pid}")
            if not text.endswith((".", ".]")):
                raise ValueError(f"Ending looks incomplete for {pid}")
            if re.search(r"(?m)^\s*(?:CHAPTER\b|\d+\. (?:Subs\.|Ins\.|Clause(?:s)? ))", text):
                raise ValueError(f"Editorial page artifact remains in {pid}")
            note = (row["review_note"] or "") + (
                f" Visually checked complete text against pinned India Code PDF pp.{','.join(map(str,pages))}; "
                "removed page footer/footnote and adjacent heading artifacts only. "
                "Source amendment markers and replacement glyphs retained. No complaint recommendation approved."
            )
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                reviewed_by=?,review_note=? WHERE provision_id=? AND verified_text IS NULL
                AND recommendable=0""",
                (text, today, "Codex AI rendered-PDF section check", note, pid))
            ledger.append({"provision_id": pid, "source_id": row["source_id"],
                           "pdf_pages": pages, "raw_sha256": expected_hash,
                           "verified_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "removed_line_numbers": sorted(DROP[pid]), "recommendable": False})
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key error")
        conn.commit()
    out = ROOT / "data_drafts" / f"remaining_it_text_review_{today.replace('-', '')}.json"
    out.write_text(json.dumps({"reviewed_on": today, "rows": ledger}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": len(ledger), "ledger": str(out)}, indent=2))


if __name__ == "__main__":
    main()
