"""Import separately reviewed, fictional complaint cases with fixed splits.

This importer rejects duplicate text, conflicting groups, unsupported positive
IDs, and altered review ledgers. It does not export or train a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, sha256


REVIEWER = 'Codex AI source-grounded complaint review'


def lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate_file', type=Path)
    parser.add_argument('review_file', type=Path)
    args = parser.parse_args()
    for path in (args.candidate_file.resolve(), args.review_file.resolve()):
        if not path.is_relative_to((ROOT / 'data_drafts').resolve()):
            raise SystemExit('Input must be under phase1/data_drafts')
    candidates = lines(args.candidate_file)
    reviews = lines(args.review_file)
    if len({r['scenario_id'] for r in candidates}) != len(candidates):
        raise SystemExit('Duplicate candidate ID')
    if len({r['scenario_id'] for r in reviews}) != len(reviews):
        raise SystemExit('Duplicate review ID')
    c_by_id = {r['scenario_id']: r for r in candidates}
    if {r['scenario_id'] for r in reviews} != set(c_by_id):
        raise SystemExit('Candidate/review IDs differ')
    today = date.today().isoformat()
    inserted = skipped = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        allowed = {r[0] for r in conn.execute('SELECT provision_id FROM recommendable_provision')}
        verified = {pid: value for pid, value in conn.execute('SELECT provision_id, verified_text FROM provision')}
        occupied_groups = {group: split for group, split in conn.execute('SELECT scenario_group, split FROM scenario')}
        occupied_texts = {' '.join(text.lower().split()): sid for sid, text in conn.execute('SELECT scenario_id, complaint_text FROM scenario')}
        for review in reviews:
            sid = review['scenario_id']
            candidate = c_by_id[sid]
            if review['decision'] != 'accept':
                raise SystemExit(f'Unsupported decision: {sid}')
            split, group = candidate['split'], candidate['scenario_group']
            text = candidate['complaint_text']
            language = candidate.get('language', 'en')
            if (split not in ('train', 'dev', 'sealed_test') or not group or
                    language not in ('en', 'hi', 'hi-Latn') or len(text.split()) < 25):
                raise SystemExit(f'Invalid split, group or text: {sid}')
            if group in occupied_groups and occupied_groups[group] != split:
                raise SystemExit(f'Group crosses splits: {sid}')
            norm = ' '.join(text.lower().split())
            if norm in occupied_texts and occupied_texts[norm] != sid:
                raise SystemExit(f'Exact complaint duplicate: {sid}')
            occupied_groups[group] = split
            occupied_texts[norm] = sid
            outcome = review['expected_outcome']
            labels = review['labels']
            positives = [x['provision_id'] for x in labels if x['label'] == 'possible']
            if (outcome == 'provision_match') != bool(positives):
                raise SystemExit(f'Outcome/positive mismatch: {sid}')
            if len({x['provision_id'] for x in labels}) != len(labels):
                raise SystemExit(f'Duplicate label: {sid}')
            if not review.get('challenge_note') or not review.get('followup_question'):
                raise SystemExit(f'Missing individual review: {sid}')
            for label in labels:
                pid = label['provision_id']
                if pid not in verified or not verified[pid]:
                    raise SystemExit(f'Label lacks verified source text: {sid}/{pid}')
                if label['label'] == 'possible' and pid not in allowed:
                    raise SystemExit(f'Positive label not eligible: {sid}/{pid}')
                if label['label'] not in ('possible', 'uncertain', 'unsupported') or not label['rationale']:
                    raise SystemExit(f'Invalid label/reason: {sid}/{pid}')
                if label['label'] == 'uncertain' and not label.get('missing_facts'):
                    raise SystemExit(f'Missing fact absent: {sid}/{pid}')
            prior = conn.execute('SELECT complaint_text, expected_outcome, split, review_tier, language FROM scenario WHERE scenario_id=?', (sid,)).fetchone()
            if prior:
                if prior != (text, outcome, split, 'ai_reviewed', language):
                    raise SystemExit(f'Existing scenario differs: {sid}')
                skipped += 1
                continue
            note = {'candidate_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                    'review_ledger_sha256': sha256(args.review_file.resolve()),
                    'challenge_note': review['challenge_note'],
                    'followup_question': review['followup_question'],
                    'source_text_sha256_by_label': {
                        x['provision_id']: hashlib.sha256(verified[x['provision_id']].encode('utf-8')).hexdigest()
                        for x in labels}}
            conn.execute('''INSERT INTO scenario
                (scenario_id, complaint_text, language, provenance_type, privacy_reviewed,
                 quality_status, expected_outcome, review_tier, reviewer, reviewed_on,
                 split, scenario_group, created_on, review_note)
                 VALUES (?, ?, ?, 'synthetic', 1, 'accepted', ?, 'ai_reviewed', ?, ?, ?, ?, ?, ?)''',
                (sid, text, language, outcome, REVIEWER, today, split, group, today,
                 json.dumps(note, ensure_ascii=False, sort_keys=True)))
            for label in labels:
                conn.execute('''INSERT INTO scenario_provision_label
                    (scenario_id, provision_id, label, rationale, missing_facts, reviewer, reviewed_on)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (sid, label['provision_id'], label['label'], label['rationale'],
                     label.get('missing_facts'), REVIEWER, today))
            inserted += 1
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print(json.dumps({'inserted': inserted, 'already_present': skipped}, indent=2))


if __name__ == '__main__':
    main()
