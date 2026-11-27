"""Replace one development story overlapping a training incident family."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH


def main() -> None:
    old, new = 'RICH_027', 'RICH_048'
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT complaint_text, split, quality_status, review_note FROM scenario WHERE scenario_id=?', (old,)).fetchone()
        if not row or row[1] != 'dev' or row[2] not in ('accepted', 'rejected'):
            raise SystemExit('Unexpected prior development case')
        if hashlib.sha256(row[0].encode('utf-8')).hexdigest() != 'f0d09934807c9ae32d571ae19f7262ee876ef4bf79103cbf2d2e77f6c41b0877':
            raise SystemExit('Prior case text changed')
        note = json.loads(row[3])
        if row[2] == 'rejected':
            if note.get('superseded_by') != new:
                raise SystemExit('Different rejection reason')
            print('Already superseded')
            return
        note.update({'superseded_by': new, 'superseded_on': date.today().isoformat(),
                     'supersession_reason': 'Shared source-code-deletion incident family with RICH_003 training case.'})
        conn.execute('UPDATE scenario SET quality_status=?, review_note=? WHERE scenario_id=?',
                     ('rejected', json.dumps(note, ensure_ascii=False, sort_keys=True), old))
        conn.commit()
    print('Superseded overlapping dev case')


if __name__ == '__main__':
    main()
