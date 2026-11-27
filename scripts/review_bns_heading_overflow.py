"""Resolve BNS section tails where the next topic heading overflowed extraction."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def read(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    validate_source_files()
    third = {"BNS_" + str(x["section"]): x["text"] for x in read(
        ROOT / "external_candidates/additional_20260917/nyaya_statute_bns.jsonl")}
    accepted = []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT * FROM provision WHERE act_id='BNS_2023'
            AND legal_status='in_force' AND verified_text IS NULL""").fetchall()
        for row in rows:
            pid, raw = row["provision_id"], row["extracted_text"]
            if pid in {"BNS_1", "BNS_2", "BNS_255"}:
                continue
            removed_pages = [line for line in raw.splitlines() if re.fullmatch(r"\d{1,3}", line.strip())]
            text = "\n".join(line for line in raw.splitlines()
                             if not re.fullmatch(r"\d{1,3}", line.strip())).strip()
            heading = ""
            if pid == "BNS_350":
                lines = text.splitlines()
                assert lines[-2:] == ["CHAPTER XIX", "OF CRIMINAL INTIMIDATION, INSULT, ANNOYANCE, DEFAMATION, ETC."]
                heading = "\n".join(lines[-2:])
                text = "\n".join(lines[:-2]).strip()
            else:
                end = text.rfind(".")
                if end < 0:
                    continue
                heading = text[end + 1:].strip()
                text = text[:end + 1]
            if not text.startswith(pid.split("_", 1)[1] + ".") or "—" not in text:
                continue
            body = norm(text.split("—", 1)[1])
            comparison = norm(third.get(pid, ""))
            if pid == "BNS_106":
                if body != comparison:
                    continue
                assert conn.execute("""SELECT legal_status FROM provision_subpart_status
                    WHERE provision_id=? AND subpart='(2)'""", (pid,)).fetchone()[0] == "uncommenced"
            elif pid == "BNS_350":
                if body != comparison:
                    continue
            else:
                if not (heading.startswith("Of ") and comparison == body + " " + norm(heading)):
                    continue
            note = ((row["review_note"] or "") + " " +
                    "Removed next-section topic heading/page-number overflow; full normalized body "
                    "matches independent statute transcription. Recommendation remains disabled.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                reviewed_by=?,review_note=?,recommendable=0 WHERE provision_id=?""",
                (text, today, "Codex AI BNS heading-overflow review", note, pid))
            accepted.append({"provision_id": pid, "pdf_page": row["source_pdf_page"],
                             "source_id": row["source_id"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "removed_page_lines": removed_pages, "removed_heading": heading,
                             "mixed_commencement": pid == "BNS_106"})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/bns_heading_overflow_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": accepted},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"approved_clean_text": len(accepted), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
