"""List every still-unreviewed BNS/IT section with pinned source evidence.

This queue organizes AI source review; it does not approve legal text or status.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter

from build_full_kb import DB_PATH, ROOT, validate_source_files


def main() -> None:
    validate_source_files()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''SELECT p.provision_id, p.act_id, p.section_number,
            p.candidate_title, p.source_pdf_page, p.extracted_text,
            p.priority_review, p.legal_status, s.source_id, s.url AS source_url, s.sha256 AS source_pdf_sha256
            FROM provision p JOIN source_snapshot s ON s.source_id=p.source_id
            WHERE p.legal_status='pending_review'
               OR (p.legal_status='in_force' AND p.verified_text IS NULL)
            ORDER BY p.act_id, CAST(p.section_number AS INTEGER), p.section_number''').fetchall()
    out = ROOT / 'data_drafts' / 'law_review_queue.jsonl'
    queue = []
    flag_counts = Counter()
    for r in rows:
        raw = r['extracted_text']
        flags = []
        if re.search(r'(?m)^\d{1,3}$', raw):
            flags.append('embedded_page_number')
        if re.search(r'(?m)^\d+\. (?:Subs\.|Ins\.|The word|The words|Section 66A)', raw):
            flags.append('amendment_footnote_lines')
        if re.search(r'(?m)^(?:Of offences|CHAPTER [IVX]+)', raw):
            flags.append('chapter_heading_lines')
        if re.search(r'(?<!\w)\d+\[', raw):
            flags.append('editorial_amendment_markers')
        likely_offence = bool(re.search(r'\b(?:shall be punished|shall be punishable|be punished with imprisonment)\b', raw, re.I))
        if likely_offence:
            flags.append('possible_criminal_penalty_wording')
        likely_civil = 'liable to penalty' in raw.casefold() and not likely_offence
        if likely_civil:
            flags.append('possible_civil_penalty_wording')
        flag_counts.update(flags)
        item = {k: r[k] for k in ('provision_id', 'act_id', 'section_number',
                'candidate_title', 'source_pdf_page', 'priority_review',
                'source_id', 'source_url', 'source_pdf_sha256')}
        item['extracted_text_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        item['extracted_text'] = raw
        item['review_status'] = ('pending_source_and_status_review' if r['legal_status']=='pending_review'
                                 else 'commencement_confirmed_text_and_kind_pending')
        item['legal_status'] = r['legal_status']
        item['mechanical_flags'] = flags
        item['review_order_hint'] = 1 if likely_offence else (2 if likely_civil else 3)
        queue.append(item)
    queue.sort(key=lambda x: (x['review_order_hint'], x['act_id'],
                              int(re.match(r'\d+', x['section_number']).group()), x['section_number']))
    with out.open('w', encoding='utf-8') as stream:
        for item in queue:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n')
    summary = {'pending_sections': len(queue),
               'pending_legal_status': sum(x['legal_status']=='pending_review' for x in queue),
               'in_force_text_unverified': sum(x['legal_status']=='in_force' for x in queue),
               'review_order_hint_counts': dict(Counter(x['review_order_hint'] for x in queue)),
               'mechanical_flag_counts': dict(flag_counts),
               'caution': 'Hints are mechanical screening only. Act-wide BNS commencement status does not verify section text, section kind, or later amendments.',
               'output': str(out)}
    (ROOT / 'law_review_queue_summary.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
