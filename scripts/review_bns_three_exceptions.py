"""Resolve BNS 1, 2 and 255 with inspected official PDF pages."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


PAGES = {"BNS_1": [16], "BNS_2": [16, 17, 18, 19, 20], "BNS_255": [80, 81]}
KINDS = {"BNS_1": "other", "BNS_2": "definition", "BNS_255": "offence"}


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def main():
    validate_source_files()
    third = {}
    source = ROOT / "external_candidates/additional_20260917/nyaya_statute_bns.jsonl"
    for line in source.read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        third[f"BNS_{x['section']}"] = x["text"]
    today = date.today().isoformat()
    accepted = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for pid in PAGES:
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["verified_text"] is None and row["provision_kind"] == "pending_review"
            assert row["source_pdf_page"] == PAGES[pid][0]
            raw = row["extracted_text"]
            if pid == "BNS_1":
                assert raw.count("date1 as the Central Government") == 1
                text = raw.replace("date1 as the Central Government", "date as the Central Government")
                assert ratio(norm(text), norm(third[pid])) >= 98
                edits = ["Removed footnote marker after 'date'; source footnote is on PDF page 16."]
            elif pid == "BNS_2":
                lines = raw.splitlines()
                removed = [line for line in lines if re.fullmatch(r"\d{1,3}", line.strip()) or
                           line.startswith("1. 1st day of July, 2024") or
                           line.startswith("February, 2024, see Gazette")]
                assert len(removed) == 6
                text = "\n".join(line for line in lines if line not in removed)
                assert ratio(norm(text), norm(third[pid])) >= 99.9
                edits = ["Removed page numbers 17-20 and the two-line footnote to section 1 from page 16."]
            else:
                assert raw.splitlines().count("81") == 1
                text = "\n".join(line for line in raw.splitlines() if line != "81")
                assert text.startswith("255.—") and ratio(norm(text.split("—", 2)[-1]), norm(third[pid])) == 100
                edits = ["Removed printed page number 81 embedded at the page break."]
            assert text.endswith(".")
            note = ((row["review_note"] or "") + " " + " ".join(edits) +
                    " Visually checked pinned official PDF pages; no recommendation approved.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                provision_kind=?,reviewed_by=?,review_note=?,recommendable=0 WHERE provision_id=?""",
                (text, today, KINDS[pid], "Codex AI PDF visual and parser review", note, pid))
            accepted.append({"provision_id": pid, "kind": KINDS[pid],
                             "visually_checked_pdf_pages": PAGES[pid], "source_id": row["source_id"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "reviewed_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "edits": edits, "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_three_exception_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": accepted},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(accepted), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
