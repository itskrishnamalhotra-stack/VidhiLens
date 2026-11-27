"""Remove BNS PDF page/header artifacts only where full body still matches exactly."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main():
    validate_source_files()
    third = {"BNS_" + str(x["section"]): x["text"] for x in read(
        ROOT / "external_candidates/additional_20260917/nyaya_statute_bns.jsonl")}
    packets = {x["provision_id"]: x for path in (ROOT / "review_automation/law_review_packets").glob("*.jsonl")
               for x in read(path)}
    held = json.loads((ROOT / "data_drafts/exact_law_text_review_20260918.json").read_text(encoding="utf-8"))["held"]
    accepted = []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for h in held:
            pid = h["provision_id"]
            if not pid.startswith("BNS_") or pid == "BNS_106":
                continue
            p = packets[pid]
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row["extracted_text"] == p["extracted_text"] and row["verified_text"] is None
            raw = row["extracted_text"]
            page_lines = [int(line.strip()) for line in raw.splitlines()
                          if re.fullmatch(r"\d{1,3}", line.strip())]
            if any(not p["official_pdf_page"] - 1 <= n <= p["official_pdf_page"] + 8 for n in page_lines):
                continue
            without_pages = "\n".join(line for line in raw.splitlines()
                                      if not re.fullmatch(r"\d{1,3}", line.strip())).strip()
            end = without_pages.rfind(".")
            if end < 0:
                continue
            text, tail = without_pages[:end + 1], without_pages[end + 1:].strip()
            if len(tail) > 100 or (tail and not re.match(r"^(?:Of |CHAPTER |[A-Z][A-Za-z ]+$)", tail)):
                continue
            if not text.startswith(pid.split("_", 1)[1] + ".") or "—" not in text:
                continue
            body = text.split("—", 1)[1]
            if ratio(norm(body), norm(third.get(pid, ""))) != 100:
                continue
            if p["second_parser_recall"] < .95:
                continue
            note = ((row["review_note"] or "") + " " +
                    "Removed only printed PDF page-number lines and trailing chapter/topic heading; "
                    "normalized full section body exactly matches independent statute transcription. "
                    "Official PDF second-parser recall >=0.95. Kind and recommendation need separate review.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                reviewed_by=?,review_note=?,recommendable=0 WHERE provision_id=?""",
                (text, today, "Codex AI BNS PDF layout check", note, pid))
            accepted.append({"provision_id": pid, "pdf_page": p["official_pdf_page"],
                             "source_pdf_sha256": p["official_pdf_sha256"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "removed_page_lines": page_lines, "removed_trailing_heading": tail,
                             "second_parser_recall": p["second_parser_recall"]})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_layout_text_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": accepted},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"approved_clean_text": len(accepted), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
