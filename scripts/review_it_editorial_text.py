"""Conservatively clean IT Act PDF editorial markers with exact text cross-check."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def main():
    validate_source_files()
    third = {"ITA_" + str(x["section"]): x["text"] for x in read(
        ROOT / "external_candidates/additional_20260917/nyaya_statute_it.jsonl")}
    packets = {x["provision_id"]: x for path in (ROOT / "review_automation/law_review_packets").glob("*.jsonl")
               for x in read(path)}
    held = json.loads((ROOT / "data_drafts/exact_law_text_review_20260918.json").read_text(encoding="utf-8"))["held"]
    out = ROOT / "data_drafts/it_editorial_text_review_20260918.json"
    accepted = json.loads(out.read_text(encoding="utf-8"))["accepted"] if out.exists() else []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for h in held:
            pid = h["provision_id"]
            if not pid.startswith("ITA_"):
                continue
            p = packets[pid]
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row["extracted_text"] == p["extracted_text"]
            if row["verified_text"] is not None:
                continue
            if p["second_parser_recall"] < .90 or row["legal_status"] != "in_force":
                continue
            removed = []
            lines = []
            for line in row["extracted_text"].splitlines():
                if re.fullmatch(r"\d{1,3}", line.strip()) or re.match(
                        r"^\d+\. (?:Subs\.|Ins\.|The word|The words|Section 66A)", line):
                    removed.append(line)
                else:
                    lines.append(line)
            text = "\n".join(lines).strip()
            text, markers = re.subn(r"(?<!\w)\d+\[", "[", text)
            end = text.rfind(".")
            if end < 0:
                continue
            tail = text[end + 1:].strip()
            chapter_tail = "CHAPTER" in tail and len(tail) < 100 and "." not in tail
            if len(tail) > 100 or (tail and tail != "]" and not chapter_tail
                                   and not re.match(r"^(?:Of |CHAPTER |[A-Z][A-Za-z ]+$)", tail)):
                continue
            text = text[:end + 1].lstrip("[")
            if not text.startswith(pid.split("_", 1)[1] + "."):
                continue
            pieces = re.split("[–—]", text, 1)
            if len(pieces) != 2 or ratio(norm(pieces[1]), norm(third.get(pid, ""))) != 100:
                continue
            note = ((row["review_note"] or "") + " " +
                    "Removed printed page/footnote lines and amendment marker numerals; "
                    "normalized full body exactly matches independent transcription. "
                    "Official PDF second-parser recall >=0.90. Kind and recommendation need separate review.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,reviewed_by=?,
                review_note=?,recommendable=0 WHERE provision_id=?""",
                (text, today, "Codex AI IT Act editorial-text check", note, pid))
            accepted.append({"provision_id": pid, "pdf_page": p["official_pdf_page"],
                             "source_pdf_sha256": p["official_pdf_sha256"],
                             "raw_sha256": hashlib.sha256(row["extracted_text"].encode()).hexdigest(),
                             "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "removed_lines": removed, "removed_marker_numerals": markers,
                             "removed_trailing_heading": tail,
                             "second_parser_recall": p["second_parser_recall"]})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out.write_text(json.dumps({"reviewed_on": today, "accepted": accepted},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"approved_clean_text": len(accepted), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
