"""Import AI-reviewed pilot coverage examples from the authored CSV ledger."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, sha256

LEDGER = ROOT / "data_drafts/pilot_coverage_gap_review_20260918.csv"


def main():
    with LEDGER.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 14 and len({r["scenario_id"] for r in rows}) == 14
    assert sum(r["split"] == "dev" for r in rows) == 11
    assert sum(r["split"] == "train" for r in rows) == 3
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        allowed = {p: (text, url, page) for p, text, url, page in conn.execute("""
            SELECT p.provision_id,p.verified_text,s.url,p.source_pdf_page
            FROM recommendable_provision p JOIN source_snapshot s USING(source_id)""")}
        for r in rows:
            pid, sid = r["provision_id"], r["scenario_id"]
            assert pid in allowed and r["rationale"] and len(r["complaint_text"]) >= 70
            assert not conn.execute("SELECT 1 FROM scenario WHERE scenario_id=?", (sid,)).fetchone()
            law, url, page = allowed[pid]
            note = {"author": "Codex AI", "ledger_sha256": sha256(LEDGER),
                    "complaint_sha256": hashlib.sha256(r["complaint_text"].encode()).hexdigest(),
                    "official_text_sha256": hashlib.sha256(law.encode()).hexdigest(),
                    "official_url": url, "official_pdf_page": page,
                    "fictional_scenario": True}
            conn.execute("""INSERT INTO scenario
                (scenario_id,complaint_text,language,provenance_type,privacy_reviewed,
                 quality_status,expected_outcome,review_tier,reviewer,reviewed_on,
                 split,scenario_group,created_on,review_note)
                VALUES (?,?,'en','synthetic',1,'accepted','provision_match',
                    'ai_reviewed','Codex AI official-section review',?,?,?,?,?)""",
                (sid, r["complaint_text"], today, r["split"], sid, today,
                 json.dumps(note, ensure_ascii=False, sort_keys=True)))
            conn.execute("""INSERT INTO scenario_provision_label
                (scenario_id,provision_id,label,rationale,reviewer,reviewed_on)
                VALUES (?,?,'possible',?,'Codex AI official-section review',?)""",
                (sid, pid, r["rationale"], today))
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    print(json.dumps({"imported": len(rows), "dev": 11, "train": 3,
                      "ledger_sha256": sha256(LEDGER)}, indent=2))


if __name__ == "__main__":
    main()
