"""Source-check four IT Act provisions with order/agency dependent offences.

They remain outside direct complaint recommendations. Source wording typos are
preserved, and each removed PDF footnote marker is recorded exactly.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT, validate_source_files


PAGES = {'ITA_69': 26, 'ITA_69A': 27, 'ITA_69B': 27, 'ITA_70B': 28}
FOOTNOTE_LINES_69 = [
    '1. Subs. by Act 18 of 2023, s. 2 and Schedule for certain words (w.e.f. 30-11-2023).',
    '2. Subs. by Act 10 of 2009, s. 33, for sub-section (2) (w.e.f. 27-10-2009).',
    '3. Subs. by s. 34, ibid., for section 69 (w.e.f. 27-10-2009).',
    '27',
]
REPLACEMENTS = {
    'ITA_69': [('3[69.', '69.')],
    'ITA_69B': [('1[one year or shall be liable to fine', 'one year or shall be liable to fine'),
                ('rupees, or with both].', 'rupees, or with both.'),
                ('any other information.]', 'any other information.')],
    'ITA_70B': [('1[one crore]', 'one crore'),
                ('sub-section (1).]', 'sub-section (1).')],
}


def clean(pid: str, raw: str) -> tuple[str, list[dict]]:
    lines = raw.splitlines()
    edits = []
    if pid == 'ITA_69':
        for line in FOOTNOTE_LINES_69:
            if lines.count(line) != 1:
                raise ValueError(f'{pid}: exact PDF footnote line absent: {line}')
            lines.remove(line)
            edits.append({'removed_layout_line': line})
    text = '\n'.join(lines).strip()
    for old, new in REPLACEMENTS.get(pid, []):
        if text.count(old) != 1:
            raise ValueError(f'{pid}: exact editorial marker absent: {old}')
        text = text.replace(old, new)
        edits.append({'from': old, 'to': new})
    if not text.startswith(pid.removeprefix('ITA_') + '.') or not text.endswith('.'):
        raise ValueError(f'Unexpected section boundary: {pid}')
    if re.search(r'(?m)^\d{1,3}$|^\d+\. (?:Subs\.|Ins\.)', text):
        raise ValueError(f'Residual PDF layout artifact: {pid}')
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
            if row['verified_text'] and row['verified_text'] != text:
                raise SystemExit(f'Existing text differs: {pid}')
            note = (f'Official central consolidation visually checked on PDF page {page}; offence applies only '
                    'to failure of a specified government/agency direction or duty. Not approved for general '
                    'complaint suggestions pending order, authority and workflow checks.')
            if pid == 'ITA_69B':
                note += " Preserve printed 'which any extend' wording; no editorial correction."
            if pid == 'ITA_70B':
                note += ' Subsection (8) restricts court cognizance to an authorised officer complaint.'
            conn.execute('''UPDATE provision SET verified_text=?, provision_kind='offence',
                legal_status='in_force', text_reviewed_on=?, status_reviewed_on=?,
                reviewed_by='Codex AI PDF text and visual audit', recommendable=0,
                review_note=? WHERE provision_id=?''', (text, today, today, note, pid))
            report.append({'id': pid, 'source_id': row['source_id'], 'source_pdf_page': page,
                           'reviewed_text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                           'removed_layout_artifacts': edits, 'provision_kind': 'offence',
                           'recommendable': False, 'note': note})
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    output = {'reviewed_on': today, 'reviewer': 'Codex AI PDF text and visual audit',
              'source_pdf': 'sources/it_act_2000_indiacode_current.pdf',
              'status_limit': 'Pinned official central consolidation; later changes still require recheck',
              'entries': report}
    dest = ROOT / 'it_expansion_source_audit_batch02.json'
    dest.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Source-checked {len(report)} order/agency dependent provisions; recommendations still held: {dest}')


if __name__ == '__main__':
    main()
