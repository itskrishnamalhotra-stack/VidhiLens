"""Source-check eight further IT Act offence provisions against pinned PDF pages.

This checks text and central-source status for an academic reference database.
None is made recommendable until complaint labels and workflow tests exist.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


PAGES = {'ITA_66F': 25, 'ITA_67B': 25, 'ITA_70': 27, 'ITA_71': 28,
         'ITA_73': 29, 'ITA_74': 29, 'ITA_84B': 32, 'ITA_84C': 32}
EXACT_REPLACEMENTS = {
    'ITA_70': [('70. Protected system.\u20132[(1)', '70. Protected system.\u2013(1)'),
               ('safety.]', 'safety.'), ('3[(4)', '(4)'), ('system.]', 'system.')],
    'ITA_71': [('2[electronic\nsignature]', 'electronic\nsignature')],
    'ITA_73': [('2[electronic signature]', 'electronic signature')],
    'ITA_74': [('2[electronic signature]', 'electronic signature')],
    'ITA_84C': [('with both.]', 'with both.')],
}


def clean(pid: str, raw: str) -> tuple[str, list[dict]]:
    edits = []
    lines = raw.splitlines()
    if pid == 'ITA_67B':
        if lines.count('26') != 1:
            raise ValueError('Expected one page 26 number within ITA_67B')
        lines.remove('26')
        edits.append({'removed_layout_line': '26'})
    text = '\n'.join(lines).strip()
    for old, new in EXACT_REPLACEMENTS.get(pid, []):
        count = text.count(old)
        expected = 3 if pid == 'ITA_73' else 1
        if count != expected:
            raise ValueError(f'{pid}: expected {expected} instances of {old!r}, saw {count}')
        text = text.replace(old, new)
        edits.append({'from': old, 'to': new, 'count': count})
    if not text.startswith(pid.removeprefix('ITA_') + '.') or not text.endswith('.'):
        raise ValueError(f'Unexpected section boundary: {pid}')
    if re.search(r'(?m)^\d{1,3}$|^\d+\. (?:Subs\.|Ins\.)', text):
        raise ValueError(f'Page number or footnote remains: {pid}')
    return text, edits


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    report = []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        for pid, page in PAGES.items():
            row = conn.execute('SELECT * FROM provision WHERE provision_id=?', (pid,)).fetchone()
            if not row or row['source_id'] != 'ITA_INDIA_CODE_CURRENT_2026_09_16' or row['source_pdf_page'] != page:
                raise SystemExit(f'Unexpected source/page: {pid}')
            if row['recommendable'] or row['legal_status'] not in ('pending_review', 'in_force'):
                raise SystemExit(f'Unexpected status: {pid}')
            text, edits = clean(pid, row['extracted_text'])
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if row['verified_text'] and row['verified_text'] != text:
                raise SystemExit(f'Existing verified text differs: {pid}')
            note = ('Official central consolidation visually checked on pages '
                    f'{page}' + ('-26' if pid == 'ITA_67B' else '') +
                    '; not approved for complaint suggestions pending case labels and evaluation.' +
                    (' Section 70 additionally requires a protected-system notification before application.' if pid == 'ITA_70' else ''))
            conn.execute('''UPDATE provision SET verified_text=?, provision_kind='offence',
                legal_status='in_force', text_reviewed_on=?, status_reviewed_on=?,
                reviewed_by='Codex AI PDF text and visual audit', recommendable=0,
                review_note=? WHERE provision_id=?''', (text, today, today, note, pid))
            report.append({'id': pid, 'source_id': row['source_id'], 'source_pdf_page': page,
                           'reviewed_text_sha256': digest, 'removed_layout_artifacts': edits,
                           'provision_kind': 'offence', 'recommendable': False,
                           'note': note})
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    output = {'reviewed_on': today, 'reviewer': 'Codex AI PDF text and visual audit',
              'source_pdf': 'sources/it_act_2000_indiacode_current.pdf',
              'status_limit': 'Pinned official central consolidation; later changes still require recheck',
              'entries': report}
    dest = ROOT / 'it_expansion_source_audit_batch01.json'
    dest.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Source-checked {len(report)} IT Act provisions, all held from recommendations: {dest}')


if __name__ == '__main__':
    main()
