"""Mark three near-template sealed cases rejected before model experiments.

This is an explicit, idempotent review correction. Historical cases and their
labels remain in the database for traceability but are excluded from exports.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH


REPLACEMENTS = {'RICH_033': 'RICH_045', 'RICH_035': 'RICH_046', 'RICH_041': 'RICH_047'}
EXPECTED_SHA256 = {
    'RICH_033': '117ad1f02222b48dab9df15e48825180abb8453cc09d6b3c29b2e181ebcec210',
    'RICH_035': '78ede2beb3d91408c83b0a0fd09d2b1c57ae5e795366434248b2495586378ec5',
    'RICH_041': '0417ab1807501ae85204e163e8b176eafbc540b703bd2d83b8bc17ee6cd73251',
}


def main() -> None:
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        for old, new in REPLACEMENTS.items():
            row = conn.execute('SELECT complaint_text, split, quality_status, review_note FROM scenario WHERE scenario_id=?', (old,)).fetchone()
            if not row or row[1] != 'sealed_test' or row[2] not in ('accepted', 'rejected'):
                raise SystemExit(f'Unexpected prior row: {old}')
            digest = hashlib.sha256(row[0].encode('utf-8')).hexdigest()
            if digest != EXPECTED_SHA256[old]:
                raise SystemExit(f'Old text changed: {old} {digest}')
            note = json.loads(row[3])
            if row[2] == 'rejected':
                if note.get('superseded_by') != new:
                    raise SystemExit(f'Different rejection reason: {old}')
                continue
            note.update({'superseded_by': new, 'superseded_on': today,
                         'supersession_reason': 'Potential template overlap with a training incident; replaced before any model experiment or test opening.'})
            conn.execute('UPDATE scenario SET quality_status=?, review_note=? WHERE scenario_id=?',
                         ('rejected', json.dumps(note, ensure_ascii=False, sort_keys=True), old))
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print('Superseded 3 sealed pilot cases before model experiments')


if __name__ == '__main__':
    main()
