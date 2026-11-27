"""Import individually authored AI-reviewed follow-up examples for accepted scenarios."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('review_file', type=Path)
    args = parser.parse_args()
    path = args.review_file.resolve()
    if not path.is_relative_to((ROOT / 'data_drafts').resolve()):
        raise SystemExit('Review ledger must be under phase1/data_drafts')
    rows = read_jsonl(path)
    if len({r['scenario_id'] for r in rows}) != len(rows):
        raise SystemExit('Duplicate scenario in ledger')
    seed_reviews = {}
    for file in sorted((ROOT / 'data_drafts').glob('seed_review_batch*.jsonl')):
        seed_reviews.update({r['queue_id']: r for r in read_jsonl(file) if r['decision'] == 'accept'})
    today = date.today().isoformat()
    inserted = skipped = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        for r in rows:
            sid = r['scenario_id']
            scenario = conn.execute('SELECT complaint_text, expected_outcome, quality_status FROM scenario WHERE scenario_id=?', (sid,)).fetchone()
            if not scenario or scenario[1:] != ('insufficient_information', 'accepted'):
                raise SystemExit(f'Follow-up scenario is not accepted insufficient-information: {sid}')
            if sid not in seed_reviews or r['assistant_message'] != seed_reviews[sid]['followup_question']:
                raise SystemExit(f'Follow-up differs from source-grounded review: {sid}')
            if len(r['options']) < 3 or 'Other' not in r['options'] or 'Not sure' not in r['options']:
                raise SystemExit(f'Follow-up lacks uncertainty/Other options: {sid}')
            if not r['review_reason'] or len(set(r['options'])) != len(r['options']):
                raise SystemExit(f'Follow-up lacks review reason or has repeated options: {sid}')
            payload = json.dumps({'response_mode': 'choice_or_free_text', 'options': r['options'],
                                  'allow_free_text': True, 'selected_option_is_reported_fact_not_verified': True,
                                  'review_reason': r['review_reason']}, ensure_ascii=False, sort_keys=True)
            eid = f'{sid}_FOLLOWUP_01'
            existing = conn.execute('SELECT assistant_message, tool_payload_json FROM conversation_example WHERE example_id=?', (eid,)).fetchone()
            if existing:
                if existing != (r['assistant_message'], payload):
                    raise SystemExit(f'Existing example differs: {eid}')
                skipped += 1
                continue
            conn.execute('''INSERT INTO conversation_example
                (example_id, scenario_id, turn_index, user_message, assistant_action,
                 assistant_message, tool_payload_json, quality_status, reviewer, reviewed_on)
                VALUES (?, ?, 1, ?, 'ask_followup', ?, ?, 'accepted', ?, ?)''',
                (eid, sid, scenario[0], r['assistant_message'], payload,
                 'Codex AI source-grounded dialogue review', today))
            inserted += 1
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print(json.dumps({'inserted': inserted, 'already_present': skipped, 'action': 'ask_followup'}, indent=2))


if __name__ == '__main__':
    main()
