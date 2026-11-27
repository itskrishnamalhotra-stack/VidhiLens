"""Record IT Act omissions stated explicitly in the pinned official PDF.

Only the exact enumerated sections are changed. Extracted text stays unverified
for display; these sections are blocked from complaint recommendations.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, validate_source_files


OMITTED = ('20', '49', '50', '51', '52', '52A', '52B', '52C',
           '53', '54', '56', '91', '92', '93', '94')


def main() -> None:
    validate_source_files()
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        for number in OMITTED:
            pid = f'ITA_{number}'
            row = conn.execute('''SELECT extracted_text, legal_status, recommendable,
                source_id FROM provision WHERE provision_id=?''', (pid,)).fetchone()
            if not row or row[3] != 'ITA_INDIA_CODE_CURRENT_2026_09_16':
                raise SystemExit(f'Unexpected source for {pid}')
            opening = ' '.join(row[0].splitlines()[:3])
            if not re.match(rf'^{re.escape(number)}\.\s*\[[^]]+\]\W*Omitted by\b', opening):
                raise SystemExit(f'Omission wording not found for {pid}')
            if row[2]:
                raise SystemExit(f'Unexpected recommendable section: {pid}')
            if row[1] not in ('pending_review', 'omitted'):
                raise SystemExit(f'Unexpected prior status for {pid}: {row[1]}')
            conn.execute('''UPDATE provision SET legal_status='omitted',
                provision_kind='omitted', status_reviewed_on=?,
                reviewed_by='Codex AI, official PDF omission wording',
                review_note=? WHERE provision_id=?''',
                (today, f'Pinned India Code PDF p. {conn.execute("SELECT source_pdf_page FROM provision WHERE provision_id=?", (pid,)).fetchone()[0]} explicitly says Omitted by. Source text remains unverified for display.', pid))
            conn.execute('''INSERT OR IGNORE INTO blocked_provision
                (provision_id, reason) VALUES (?, 'Pinned official IT Act PDF explicitly marks this section omitted')''',
                (pid,))
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print(f'Marked {len(OMITTED)} explicit IT Act omissions and blocked recommendations')


if __name__ == '__main__':
    main()
