"""Import the 28 source-grounded Nyaya v3 intake decisions; hold unsuitable rows."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, sha256

PACKET = ROOT / "review_automation" / "case_review_packets" / "packet_01.jsonl"
LEDGER = ROOT / "data_drafts" / "nyaya_v3_28_case_review_20260918.jsonl"
SOURCE_KEY = "nyaya_v3_train"
REVIEWER = "Codex AI official-section case review"


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def language(text):
    if any("\u0900" <= c <= "\u097f" for c in text):
        return "hi"
    roman_hindi = ("Mere ", "Mera ", "Kya ", "Maine ", "Mujhe ")
    return "hi-Latn" if any(word in text for word in roman_hindi) else "en"


def main():
    packets = {r["row_number"]: r for r in rows(PACKET)}
    decisions = rows(LEDGER)
    assert len(packets) == len(decisions) == 28
    assert set(packets) == {r["row_number"] for r in decisions}
    source_manifest = json.loads((ROOT / "additional_candidates_manifest.json").read_text(encoding="utf-8"))
    source = next(s for s in source_manifest["files"] if s["key"] == SOURCE_KEY)
    assert source["license"] == "apache-2.0"
    assert sha256(ROOT / source["local_path"]) == source["sha256"]
    now = date.today().isoformat()
    imported = held = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        allowed = {r[0]: r[1] for r in conn.execute(
            "SELECT provision_id,verified_text FROM recommendable_provision")}
        for d in decisions:
            n = d["row_number"]
            packet = packets[n]
            candidate = conn.execute("""SELECT * FROM additional_candidate_row
                WHERE source_key=? AND row_number=?""", (SOURCE_KEY, n)).fetchone()
            assert candidate and candidate["input_text"] == packet["input_text"]
            assert packet["source_file_sha256"] == source["sha256"]
            if d["decision"] == "hold":
                assert d.get("reason")
                held += 1
                continue
            assert d["decision"] == "accept"
            pid = d["provision_id"]
            assert pid in allowed and d["label"] in {"possible", "uncertain"}
            assert d["rationale"] and d["followup_question"]
            if d["label"] == "uncertain":
                assert d.get("missing_facts")
            else:
                assert not d.get("missing_facts")
            context = next((r for r in packet["official_section_context"]
                            if r["provision_id"] == pid), None)
            assert context and context["verified_text"] == allowed[pid]
            sid = f"NYV3_{n:05d}"
            assert not conn.execute("SELECT 1 FROM scenario WHERE scenario_id=?", (sid,)).fetchone()
            outcome = "provision_match" if d["label"] == "possible" else "insufficient_information"
            note = {"source_key": SOURCE_KEY, "row_number": n,
                    "input_sha256": hashlib.sha256(candidate["input_text"].encode()).hexdigest(),
                    "source_file_sha256": source["sha256"], "review_ledger_sha256": sha256(LEDGER),
                    "publisher_label_not_used_as_truth": True,
                    "official_text_sha256": hashlib.sha256(allowed[pid].encode()).hexdigest(),
                    "official_url": context["official_url"], "official_pdf_page": context["official_pdf_page"],
                    "followup_question": d["followup_question"]}
            conn.execute("""INSERT INTO scenario
                (scenario_id,complaint_text,language,provenance_type,source_url,license,
                 privacy_reviewed,quality_status,expected_outcome,review_tier,reviewer,
                 reviewed_on,split,scenario_group,created_on,review_note)
                VALUES (?,?,?,'public_licensed',?,'apache-2.0',1,'accepted',?,
                    'ai_reviewed',?,?,'train',?,?,?)""",
                (sid, candidate["input_text"], language(candidate["input_text"]),
                 source["url"], outcome, REVIEWER, now, sid, now,
                 json.dumps(note, ensure_ascii=False, sort_keys=True)))
            conn.execute("""INSERT INTO scenario_provision_label
                (scenario_id,provision_id,label,rationale,missing_facts,reviewer,reviewed_on)
                VALUES (?,?,?,?,?,?,?)""",
                (sid, pid, d["label"], d["rationale"], d.get("missing_facts"), REVIEWER, now))
            imported += 1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    print(json.dumps({"reviewed": len(decisions), "imported_train": imported,
                      "held": held, "possible": sum(d.get("label") == "possible" for d in decisions),
                      "uncertain": sum(d.get("label") == "uncertain" for d in decisions)}, indent=2))


if __name__ == "__main__":
    main()
