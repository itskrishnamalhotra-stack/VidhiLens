"""Resolve IT Act 7A and 84 after visually inspecting pinned PDF pages."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


DETAIL = {"ITA_7A": {"pages": [10], "kind": "procedure"},
          "ITA_84": {"pages": [31, 32], "kind": "exception"}}


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
        for pid, meta in DETAIL.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["verified_text"] is None and row["source_pdf_page"] == meta["pages"][0]
            raw = row["extracted_text"]
            lines = [line for line in raw.splitlines()
                     if not re.fullmatch(r"\d{1,3}", line.strip())
                     and not re.match(r"^\d+\. (?:Subs\.|Ins\.)", line)]
            text = re.sub(r"(?<!\w)\d+\[", "[", "\n".join(lines)).strip().lstrip("[")
            if pid == "ITA_7A":
                assert text.endswith(".]"), "Inserted-section bracket changed"
                text = text[:-1]
            assert text.startswith(pid.split("_", 1)[1] + ".") and text.endswith(".")
            assert ratio(norm(text.split("–", 1)[-1]), norm(other[pid])) == 100
            note = ((row["review_note"] or "") + " " +
                    "Visually checked pinned official IT Act PDF page(s) and exact independent "
                    "text comparison; removed editorial insertion marker only. "
                    "Recommendation remains disabled.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                provision_kind=?,reviewed_by=?,review_note=?,recommendable=0
                WHERE provision_id=?""",
                (text, today, meta["kind"], "Codex AI PDF visual and text review", note, pid))
            reviewed.append({"provision_id": pid, "kind": meta["kind"],
                             "visually_checked_pdf_pages": meta["pages"],
                             "source_id": row["source_id"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "reviewed_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/it_visual_two_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
