"""Link the 1,338 row decisions to their indexed master-DB source records."""
from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "master_dataset.sqlite"
LEDGER = ROOT / "review_automation" / "complaint_pool_v2" / "remaining_1338_review" / "decisions.csv"
PRIORITY = ROOT / "review_automation" / "complaint_pool_v2" / "priority_source_decisions.csv"
STAMP = "2026-09-18"

rows = list(csv.DictReader(LEDGER.open(encoding="utf-8", newline="")))
if len(rows) != 1338 or len({int(r["source_row"]) for r in rows}) != 1338:
    raise ValueError("Unexpected row decisions")
ledger_hash = hashlib.sha256(LEDGER.read_bytes()).hexdigest()
with sqlite3.connect(DB) as conn:
    conn.execute("PRAGMA foreign_keys=ON")
    for r in rows:
        n = int(r["source_row"])
        decision = "accepted_corrected" if r["decision"].startswith("positive_") else "held"
        note = f"{r['decision']}; target={r['reviewed_target'] or 'none'}; {r['reason']}"
        existing = conn.execute("SELECT decision,review_ledger_sha256,decision_note,reviewed_on FROM public_candidate_review "
                                "WHERE source_key='statutory_triage' AND row_number=?", (n,)).fetchone()
        if existing and existing[:2] != (decision, ledger_hash):
            own = existing[3] == STAMP and existing[2].split(";", 1)[0] in {
                "positive_same_provision", "positive_relabelled", "clarification_train",
                "challenge_not_positive", "duplicate_held"}
            if not own:
                raise ValueError(f"Conflicting prior review for row {n}")
        conn.execute("INSERT OR REPLACE INTO public_candidate_review "
                     "(source_key,row_number,decision,decision_note,review_ledger_sha256,reviewed_on) "
                     "VALUES ('statutory_triage',?,?,?,?,?)",
                     (n, decision, note, ledger_hash, STAMP))
    priority_rows = list(csv.DictReader(PRIORITY.open(encoding="utf-8", newline="")))
    if len(priority_rows) != 78:
        raise ValueError("Priority review changed")
    priority_hash = hashlib.sha256(PRIORITY.read_bytes()).hexdigest()
    for r in priority_rows:
        n = int(r["source_row"])
        existing = conn.execute("SELECT decision,review_ledger_sha256 FROM public_candidate_review "
                                "WHERE source_key='statutory_triage' AND row_number=?", (n,)).fetchone()
        if existing:
            if existing != (r["decision"], priority_hash):
                raise ValueError(f"Conflicting priority review: {n}")
            continue
        conn.execute("INSERT INTO public_candidate_review "
                     "(source_key,row_number,decision,decision_note,review_ledger_sha256,reviewed_on) "
                     "VALUES ('statutory_triage',?,?,?,?,?)",
                     (n, r["decision"], r["review_reason"], priority_hash, STAMP))
    conn.commit()
    print(conn.execute("SELECT decision,COUNT(*) FROM public_candidate_review "
                       "WHERE source_key='statutory_triage' GROUP BY decision").fetchall())
