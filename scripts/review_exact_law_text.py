"""Approve only exact three-way transcriptions of clean official PDF sections.

The external statute copy is used solely as a transcription cross-check; it
cannot determine current legal status or become a source of law. This pass
does not decide offence kind or enable recommendations.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from rapidfuzz.fuzz import ratio

from build_full_kb import DB_PATH, ROOT, validate_source_files
from import_law_review_batch import cleaned


PACKETS = ROOT / "review_automation" / "law_review_packets"
EXTERNAL = ROOT / "external_candidates" / "additional_20260917"
ALLOW_FLAGS = {"possible_criminal_penalty_wording", "possible_civil_penalty_wording"}


def norm(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def section_body(text: str) -> str:
    if "—" in text:
        return text.split("—", 1)[1]
    if "–" in text:
        return text.split("–", 1)[1]
    raise ValueError("No title-body boundary")


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    validate_source_files()
    third = {}
    for name, prefix in (("nyaya_statute_bns", "BNS"), ("nyaya_statute_it", "ITA")):
        for row in read_jsonl(EXTERNAL / (name + ".jsonl")):
            third[prefix + "_" + str(row["section"])] = row["text"]
    packets = [row for path in sorted(PACKETS.glob("packet_*.jsonl")) for row in read_jsonl(path)]
    assert len(packets) == 385
    today = date.today().isoformat()
    accepted, held = [], []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for p in packets:
            pid = p["provision_id"]
            row = conn.execute("SELECT * FROM provision WHERE provision_id=?", (pid,)).fetchone()
            assert row and row["source_pdf_page"] == p["official_pdf_page"]
            source = conn.execute("SELECT url,sha256 FROM source_snapshot WHERE source_id=?",
                                  (row["source_id"],)).fetchone()
            assert source["url"] == p["official_source_url"] and source["sha256"] == p["official_pdf_sha256"]
            assert row["extracted_text"] == p["extracted_text"]
            extraction_hash = hashlib.sha256(row["extracted_text"].encode()).hexdigest()
            reasons = []
            if pid == "BNS_106":
                reasons.append("mixed commencement status for subpart (2)")
            if p["second_parser_recall"] < .98:
                reasons.append("independent PDF parser recall below 0.98")
            if set(p["mechanical_flags"]) - ALLOW_FLAGS:
                reasons.append("layout, footnote, or amendment marker needs editing")
            try:
                official_text, _ = cleaned({"provision_id": pid}, row["extracted_text"])
                body = section_body(official_text)
            except ValueError as exc:
                reasons.append("section boundary or layout: " + str(exc))
                official_text = body = ""
            comparison = third.get(pid)
            if not comparison:
                reasons.append("no independent text comparison")
                score = None
            else:
                score = ratio(norm(body), norm(comparison)) if body else 0
                if score != 100.0:
                    reasons.append("independent text does not exactly match normalized official PDF body")
            if reasons:
                held.append({"provision_id": pid, "reasons": reasons, "comparison_score": score})
                continue
            assert row["verified_text"] is None and row["legal_status"] == "in_force"
            note = ((row["review_note"] or "") + " " +
                    "Exact normalized body agreement with independent statute transcription; "
                    "official PDF extraction also has >=0.98 second-parser recall and no "
                    "layout/editorial flags. Kind and recommendation require separate review.").strip()
            conn.execute("""UPDATE provision SET verified_text=?, text_reviewed_on=?,
                reviewed_by=?, review_note=?, recommendable=0 WHERE provision_id=?""",
                (official_text, today, "Codex AI triple-text source check", note, pid))
            accepted.append({"provision_id": pid, "source_id": row["source_id"],
                             "source_pdf_page": row["source_pdf_page"],
                             "source_pdf_sha256": p["official_pdf_sha256"],
                             "official_extraction_sha256": extraction_hash,
                             "verified_text_sha256": hashlib.sha256(official_text.encode()).hexdigest(),
                             "second_parser_recall": p["second_parser_recall"],
                             "independent_normalized_body_agreement": score,
                             "provision_kind": row["provision_kind"], "recommendable": False})
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts" / "exact_law_text_review_20260918.json"
    out.write_text(json.dumps({"reviewed_on": today, "exact_pass": len(accepted),
                               "held_for_edit_or_analysis": len(held),
                               "method": "Official PDF extraction, independent PDF parser recall, and exact normalized independent text agreement; no recommendation enabling.",
                               "accepted": accepted, "held": held},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exact_pass": len(accepted), "held": len(held),
                      "report": str(out)}, indent=2))


if __name__ == "__main__":
    main()
