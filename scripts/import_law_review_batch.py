"""Import individually reviewed law-text batches with exact extraction evidence.

The importer never enables recommendations. A separate coverage decision must do
that after complaint data and evaluation exist for the provision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT, validate_source_files


REVIEWER = 'Codex AI PDF text and visual audit'


def cleaned(row: dict, raw: str) -> tuple[str, list[dict]]:
    lines = raw.splitlines()
    edits = []
    for line in row.get('remove_lines', []):
        if lines.count(line) != 1:
            raise ValueError(f"{row['provision_id']}: expected exactly one layout line {line!r}")
        lines.remove(line)
        edits.append({'removed_layout_line': line})
    text = '\n'.join(lines).strip()
    for item in row.get('replace', []):
        old, new, expected = item['old'], item['new'], item['count']
        if text.count(old) != expected:
            raise ValueError(f"{row['provision_id']}: expected {expected} instances of {old!r}")
        text = text.replace(old, new)
        edits.append({'from': old, 'to': new, 'count': expected})
    number = row['provision_id'].split('_', 1)[1]
    if not text.startswith(number + '.') or not text.endswith('.'):
        raise ValueError(f"{row['provision_id']}: boundary mismatch")
    if re.search(r'(?m)^\d{1,3}$|^\d+\. (?:Subs\.|Ins\.)', text):
        raise ValueError(f"{row['provision_id']}: page number or footnote remains")
    if re.search(r'(?m)^(Of offences|CHAPTER [IVX]+)$', text):
        raise ValueError(f"{row['provision_id']}: chapter heading remains")
    return text, edits


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('ledger', type=Path)
    args = parser.parse_args()
    validate_source_files()
    path = args.ledger.resolve()
    if not path.is_relative_to((ROOT / 'data_drafts').resolve()):
        raise SystemExit('Ledger must be under phase1/data_drafts')
    decisions = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({r['provision_id'] for r in decisions}) != len(decisions):
        raise SystemExit('Duplicate provision in ledger')
    today = date.today().isoformat()
    audit = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        for decision in decisions:
            pid = decision['provision_id']
            row = conn.execute('SELECT * FROM provision WHERE provision_id=?', (pid,)).fetchone()
            if not row or row['source_id'] != decision['source_id'] or row['source_pdf_page'] != decision['source_pdf_page']:
                raise SystemExit(f'Source/page mismatch: {pid}')
            if hashlib.sha256(row['extracted_text'].encode('utf-8')).hexdigest() != decision['extracted_text_sha256']:
                raise SystemExit(f'Extracted text hash mismatch: {pid}')
            if not decision.get('review_note') or row['source_pdf_page'] not in decision.get('visually_checked_pdf_pages', []):
                raise SystemExit(f'Missing review evidence: {pid}')
            if row['recommendable'] or row['legal_status'] not in ('pending_review', decision['legal_status']):
                raise SystemExit(f'Existing status unexpected: {pid}')
            if decision['legal_status'] != 'in_force' or decision['provision_kind'] not in ('offence', 'definition', 'exception', 'procedure', 'power', 'other'):
                raise SystemExit(f'Unsupported batch classification: {pid}')
            text, edits = cleaned(decision, row['extracted_text'])
            if row['verified_text'] and row['verified_text'] != text:
                raise SystemExit(f'Existing verified text differs: {pid}')
            conn.execute('''UPDATE provision SET verified_text=?, provision_kind=?, legal_status=?,
                text_reviewed_on=?, status_reviewed_on=?, reviewed_by=?, recommendable=0,
                review_note=? WHERE provision_id=?''',
                (text, decision['provision_kind'], decision['legal_status'], today, today,
                 REVIEWER, decision['review_note'], pid))
            for relation in decision.get('relations', []):
                target = relation['to_provision_id']
                expected_number = target.split('_', 1)[1]
                if target == pid or not re.search(rf'\bsection\s+{re.escape(expected_number)}\b', text, re.I):
                    raise SystemExit(f'Relation lacks explicit text reference: {pid}->{target}')
                prior = conn.execute('''SELECT note FROM provision_relation
                    WHERE from_provision_id=? AND to_provision_id=? AND relation_type=?''',
                    (pid, target, relation['relation_type'])).fetchone()
                if prior and prior[0] != relation['note']:
                    raise SystemExit(f'Relation note differs: {pid}->{target}')
                conn.execute('''INSERT OR IGNORE INTO provision_relation
                    (from_provision_id, to_provision_id, relation_type, note, reviewed_on)
                    VALUES (?, ?, ?, ?, ?)''',
                    (pid, target, relation['relation_type'], relation['note'], today))
            audit.append({'id': pid, 'source_id': row['source_id'],
                          'source_pdf_page': row['source_pdf_page'],
                          'extracted_text_sha256': decision['extracted_text_sha256'],
                          'reviewed_text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                          'removed_layout_artifacts': edits,
                          'provision_kind': decision['provision_kind'],
                          'legal_status': decision['legal_status'],
                          'relations': decision.get('relations', []),
                          'recommendable': False, 'note': decision['review_note']})
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    report = {'reviewed_on': today, 'reviewer': REVIEWER,
              'ledger': str(path.relative_to(ROOT)), 'entries': audit,
              'note': 'Source-checked for the pinned central PDF; later law changes and state amendments require separate review.'}
    out = ROOT / (path.stem + '_audit.json')
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Source-checked {len(audit)} provisions, none enabled for suggestions: {out}')


if __name__ == '__main__':
    main()
