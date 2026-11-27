"""Require an explicit, text-pinned approval and case coverage to enable a section.

The database-level guard prevents a status/text review alone from silently
turning on complaint suggestions. This is a structural gate, not proof of
model accuracy or a substitute for later evaluation.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from build_full_kb import DB_PATH, ROOT


PILOT = {"BNS_115", "BNS_117", "BNS_303", "BNS_304", "BNS_316", "BNS_318",
         "BNS_319", "BNS_329", "BNS_351", "BNS_75", "BNS_77", "BNS_78",
         "ITA_65", "ITA_66", "ITA_66B", "ITA_66C", "ITA_66D", "ITA_67", "ITA_67A"}


def main():
    today = date.today().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='recommendation_release_approval'").fetchone():
            raise SystemExit("Release approval migration already applied")
        allowed = {p for (p,) in conn.execute("SELECT provision_id FROM recommendable_provision")}
        if allowed != PILOT:
            raise ValueError("Current recommendation scope does not match reviewed 19-section pilot")
        conn.execute("""CREATE TABLE recommendation_release_approval (
            provision_id TEXT PRIMARY KEY REFERENCES provision(provision_id),
            approved_text TEXT NOT NULL,
            approved_on TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            scope_note TEXT NOT NULL
        )""")
        for pid in sorted(PILOT):
            text = conn.execute("SELECT verified_text FROM provision WHERE provision_id=?", (pid,)).fetchone()[0]
            assert text
            conn.execute("""INSERT INTO recommendation_release_approval
                (provision_id,approved_text,approved_on,reviewer,scope_note)
                VALUES (?,?,?,'Codex AI pilot release review',
                '19-section pilot only; full-act coverage and model reliability remain unproven')""",
                (pid, text, today))
        conn.execute("""CREATE TRIGGER require_recommendation_release_approval
            BEFORE UPDATE OF recommendable,verified_text,legal_status,provision_kind ON provision
            WHEN NEW.recommendable=1 AND (
                NOT EXISTS (SELECT 1 FROM recommendation_release_approval a
                    WHERE a.provision_id=NEW.provision_id AND a.approved_text=NEW.verified_text)
                OR (SELECT count(*) FROM scenario_provision_label l
                    JOIN scenario s USING(scenario_id)
                    WHERE l.provision_id=NEW.provision_id AND l.label='possible'
                      AND s.quality_status='accepted' AND s.privacy_reviewed=1
                      AND s.split='train') < 5
                OR (SELECT count(*) FROM scenario_provision_label l
                    JOIN scenario s USING(scenario_id)
                    WHERE l.provision_id=NEW.provision_id AND l.label='possible'
                      AND s.quality_status='accepted' AND s.privacy_reviewed=1
                      AND s.split='dev') < 1
                OR (SELECT count(*) FROM scenario_provision_label l
                    JOIN scenario s USING(scenario_id)
                    WHERE l.provision_id=NEW.provision_id AND l.label='possible'
                      AND s.quality_status='accepted' AND s.privacy_reviewed=1
                      AND s.split='sealed_test') < 2
            )
            BEGIN SELECT RAISE(ABORT,'section lacks text-pinned release approval or case coverage'); END""")
        # Exercise the exact path that the old validator found unguarded.
        try:
            conn.execute("UPDATE provision SET recommendable=1 WHERE provision_id='BNS_305'")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Unapproved BNS_305 passed release gate")
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
    out = ROOT / "data_drafts/recommendation_release_gate_20260918.json"
    out.write_text(json.dumps({"created_on": today, "pilot_approved": sorted(PILOT),
                               "gate": "exact approved text plus positive train/dev/sealed coverage",
                               "unapproved_provision_probe": "BNS_305 rejected",
                               "model_accuracy_claim": False}, indent=2) + "\n", encoding="utf-8")
    print(f"Locked recommendation release to {len(PILOT)} approved pilot sections; BNS_305 rejected")


if __name__ == "__main__":
    main()
