"""Import authored workflow conversations with source-checked provision IDs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

from build_full_kb import DB_PATH, ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('review_file', type=Path)
    args = parser.parse_args()
    path = args.review_file.resolve()
    if not path.is_relative_to((ROOT / 'data_drafts').resolve()):
        raise SystemExit('Review ledger must be under phase1/data_drafts')
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({(r['scenario_id'], r['turn_index']) for r in rows}) != len(rows):
        raise SystemExit('Duplicate scenario/turn in ledger')
    today = date.today().isoformat()
    inserted = skipped = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        allowed = {r[0] for r in conn.execute('SELECT provision_id FROM recommendable_provision')}
        for r in rows:
            sid, turn = r['scenario_id'], r['turn_index']
            scenario = conn.execute('SELECT expected_outcome, quality_status FROM scenario WHERE scenario_id=?', (sid,)).fetchone()
            if not scenario or scenario[1] != 'accepted' or not r['review_reason']:
                raise SystemExit(f'Unreviewed scenario/action: {sid}/{turn}')
            action = r['assistant_action']
            if action in ('suggest_provisions', 'offer_draft', 'draft', 'edit_draft', 'confirm_draft', 'cancel_draft') and scenario[0] != 'provision_match':
                raise SystemExit(f'Draft or suggestion on non-match: {sid}/{turn}')
            if action == 'explain_uncertainty' and scenario[0] != 'insufficient_information' and not (
                    scenario[0] == 'provision_match' and r['tool_payload'].get('after_material_edit') is True):
                raise SystemExit(f'Incorrect uncertainty outcome: {sid}/{turn}')
            if action == 'refer_to_authorities' and scenario[0] != 'out_of_scope':
                raise SystemExit(f'Incorrect referral outcome: {sid}/{turn}')
            payload = r['tool_payload']
            cited = set(payload.get('candidate_provision_ids', []) + payload.get('known_provision_ids', []))
            scenario_possible = {p[0] for p in conn.execute("SELECT provision_id FROM scenario_provision_label WHERE scenario_id=? AND label='possible'", (sid,))}
            if not cited <= allowed or not cited <= scenario_possible:
                raise SystemExit(f'Unapproved provision ID: {sid}/{turn}')
            if action == 'confirm_draft' and (not payload.get('explicit_user_confirmation') or payload.get('command') != 'save_local_draft'):
                raise SystemExit(f'Confirmation lacks consent gate: {sid}/{turn}')
            if action == 'cancel_draft' and payload.get('command') != 'discard_unsaved_draft':
                raise SystemExit(f'Cancellation lacks discard command: {sid}/{turn}')
            if payload.get('official_filing') is True:
                raise SystemExit(f'Official filing claim: {sid}/{turn}')
            eid = f'{sid}_WORKFLOW_{turn:02d}'
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            existing = conn.execute('SELECT user_message, assistant_action, assistant_message, tool_payload_json FROM conversation_example WHERE scenario_id=? AND turn_index=?', (sid, turn)).fetchone()
            expected = (r['user_message'], action, r['assistant_message'], encoded)
            if existing:
                if existing != expected:
                    raise SystemExit(f'Existing turn differs: {sid}/{turn}')
                skipped += 1
                continue
            conn.execute('''INSERT INTO conversation_example
                (example_id, scenario_id, turn_index, user_message, assistant_action,
                assistant_message, tool_payload_json, quality_status, reviewer, reviewed_on)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?)''',
                (eid, sid, turn, r['user_message'], action, r['assistant_message'], encoded,
                 'Codex AI source-grounded workflow review', today))
            inserted += 1
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SystemExit('Foreign key error')
        conn.commit()
    print(json.dumps({'inserted': inserted, 'already_present': skipped}, indent=2))


if __name__ == '__main__':
    main()
