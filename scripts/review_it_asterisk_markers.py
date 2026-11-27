"""Remove proven IT Act amendment deletion marks from five section extracts."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files


KIND = {"ITA_1": "other", "ITA_30": "procedure", "ITA_35": "procedure",
        "ITA_40": "procedure", "ITA_42": "procedure"}


def norm(s):
    return " ".join(re.findall(r"\w+", s.casefold()))


def main():
    validate_source_files()
    other = {}
    for line in (ROOT / "external_candidates/additional_20260917/nyaya_statute_it.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        other[f"ITA_{x['section']}"] = x["text"]
    reviewed = []
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        for pid, kind in KIND.items():
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["verified_text"] is None and row["legal_status"] == "in_force"
            raw = row["extracted_text"]
            text, bracket_markers = re.subn(r"(?<!\w)\d+\[", "[", raw)
            text, deletion_marks = re.subn(r"\b\d+\*+(?:\n\*+)*", "", text)
            if pid == "ITA_1":
                assert text.count("date1") == 1
                text = text.replace("date1", "date")
            text = text[:text.rfind(".") + 1]
            assert text.startswith(pid.split("_", 1)[1] + ".") and text.endswith(".")
            body = re.split("[–—]", text, 1)[1]
            assert ratio(norm(body), norm(other[pid])) == 100
            note = ((row["review_note"] or "") + " " +
                    "Removed printed amendment insertion/deletion marker numerals and stars; "
                    "full normalized section body exactly matches independent transcription. "
                    "No recommendation approved.").strip()
            conn.execute("""UPDATE provision SET verified_text=?,text_reviewed_on=?,
                provision_kind=?,reviewed_by=?,review_note=?,recommendable=0
                WHERE provision_id=?""",
                (text, today, kind, "Codex AI editorial marker review", note, pid))
            reviewed.append({"provision_id": pid, "kind": kind, "source_id": row["source_id"],
                             "pdf_page": row["source_pdf_page"],
                             "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                             "reviewed_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                             "bracket_markers_removed": bracket_markers,
                             "deletion_marks_removed": deletion_marks,
                             "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/it_asterisk_marker_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "accepted": reviewed},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(reviewed), "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
