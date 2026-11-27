"""Source-check three IT Act transcription disagreements against PDF images."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


DETAIL = {"ITA_12": (11, "procedure", 99.9,
                     "Official PDF spells 'acknowledgement'; comparison copy uses 'acknowledgment'."),
          "ITA_21": (14, "procedure", 99.7,
                     "Official PDF prints 'fulfils' and 'arc'; these printed spellings are preserved."),
          "ITA_90": (35, "power", 99.8,
                     "Official PDF prints 'Stale Legislature'; printed wording is preserved.")}


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def main():
    validate_source_files()
    other = {}
    for line in (ROOT / "external_candidates/additional_20260917/nyaya_statute_it.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        other[f"ITA_{x['section']}"] = x["text"]
    today = date.today().isoformat()
    reviewed = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for pid, (page, kind, minimum, difference_note) in DETAIL.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["verified_text"] is None and row["source_pdf_page"] == page
            raw = row["extracted_text"]
            text = re.sub(r"(?<!\w)\d+\[", "[", raw)
            text = re.sub(r"\b\d+\*+(?:\s*\*)*", "", text)
            text = text[:text.rfind(".") + 1]
            assert text.startswith(pid.split("_", 1)[1] + ".") and text.endswith(".")
            body = re.split("[–—]", text, 1)[1]
            score = ratio(norm(body), norm(other[pid]))
            assert score >= minimum
            note = ((row["review_note"] or "") + " " +
                    "Visually checked official PDF page; removed editorial marker numerals/stars. " +
                    difference_note + " No complaint recommendation approved.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                provision_kind=?,reviewed_by=?,review_note=?,recommendable=0
                WHERE provision_id=?""",
                (text, today, kind, "Codex AI PDF visual comparison", note, pid))
            reviewed.append({"provision_id": pid, "kind": kind, "visually_checked_pdf_page": page,
                             "source_id": row["source_id"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "reviewed_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "independent_comparison_score": score,
                             "known_printed_difference": difference_note,
                             "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/it_visual_three_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
