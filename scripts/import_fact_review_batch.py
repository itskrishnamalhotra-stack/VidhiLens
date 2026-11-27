"""Import individually reviewed fact states; never infer missing values from labels."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from build_full_kb import DB_PATH, ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('review_file', type=Path)
    args = parser.parse_args()
    path = args.review_file.resolve()
    if not path.is_relative_to((ROOT / 'data_drafts').resolve()):
        raise SystemExit('Review ledger must be under phase1/data_drafts')
    rows = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if len({r['scenario_id'] for r in rows}) != len(rows):
        raise SystemExit('Repeated scenario')
    inserted = skipped = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        for row in rows:
            sid = row['scenario_id']
            found = conn.execute('SELECT complaint_text, quality_status FROM scenario WHERE scenario_id=?', (sid,)).fetchone()
            if not found or found[1] != 'accepted' or not row['review_reason']:
                raise SystemExit(f'Unaccepted scenario or missing review: {sid}')
            if len({f['fact_key'] for f in row['facts']}) != len(row['facts']):
                raise SystemExit(f'Repeated fact key: {sid}')
            for fact in row['facts']:
                state = fact['state']
                if state not in ('present', 'absent', 'unknown', 'disputed'):
                    raise SystemExit(f'Invalid state: {sid}/{fact["fact_key"]}')
                val, span = fact.get('fact_value'), fact.get('evidence_span')
                if state in ('present', 'absent') and (not val or not span or span not in found[0]):
                    raise SystemExit(f'Claim lacks exact complaint evidence: {sid}/{fact["fact_key"]}')
                if state in ('unknown', 'disputed') and (val or span):
                    raise SystemExit(f'Unknown/disputed fact asserted: {sid}/{fact["fact_key"]}')
                key = (sid, fact['fact_key'])
                existing = conn.execute('SELECT fact_value, state, evidence_span FROM scenario_fact WHERE scenario_id=? AND fact_key=?', key).fetchone()
                expected = (val, state, span)
                if existing:
                    if existing != expected:
                        raise SystemExit(f'Existing fact differs: {sid}/{fact["fact_key"]}')
                    skipped += 1
                    continue
                conn.execute('INSERT INTO scenario_fact VALUES (?, ?, ?, ?, ?)', (sid, fact['fact_key'], val, state, span))
                inserted += 1
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print(json.dumps({'inserted': inserted, 'already_present': skipped, 'scenarios': len(rows)}, indent=2))


if __name__ == '__main__':
    main()
