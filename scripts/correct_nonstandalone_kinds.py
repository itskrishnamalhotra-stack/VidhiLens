"""Correct two provisions that a verb-based screen marked as standalone offences."""
from pathlib import Path
import sqlite3

DB = Path(__file__).resolve().parents[1] / "db" / "master_dataset.sqlite"
CORRECTIONS = {
    "BNS_71": ("other", "Repeat-conviction sentencing provision; not an independent incident offence."),
    "BNS_165": ("civil_penalty", "Negligence-based monetary penalty for a merchant-vessel master; not an independent criminal offence label."),
}

with sqlite3.connect(DB) as conn:
    for pid, (kind, reason) in CORRECTIONS.items():
        row = conn.execute("SELECT provision_kind, verified_text, review_note FROM provision WHERE provision_id=?", (pid,)).fetchone()
        if row is None or not row[1] or row[0] not in ("offence", kind):
            raise ValueError(f"Unexpected source state for {pid}")
        note = row[2] or ""
        marker = " Section-kind correction 2026-09-18: " + reason
        if marker not in note:
            note += marker
        conn.execute("UPDATE provision SET provision_kind=?, review_note=? WHERE provision_id=?", (kind, note, pid))
    conn.commit()
    print(conn.execute("SELECT provision_kind, COUNT(*) FROM provision WHERE legal_status='in_force' GROUP BY provision_kind").fetchall())
