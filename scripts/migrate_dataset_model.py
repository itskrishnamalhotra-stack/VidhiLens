"""Add explicit scenario review and abstention fields to the existing Phase 1 KB.

Safe to rerun. It never rewrites statute text, labels, or scenarios.
"""

from __future__ import annotations

import sqlite3

from build_full_kb import DB_PATH


TRIGGER = """
CREATE TRIGGER IF NOT EXISTS scenario_accept_requires_review
BEFORE UPDATE OF quality_status, expected_outcome, review_tier, reviewer, reviewed_on, privacy_reviewed, split ON scenario
WHEN NEW.quality_status = 'accepted' AND (
    NEW.expected_outcome = 'pending_review' OR NEW.review_tier = 'pending_review' OR
    NEW.reviewer IS NULL OR length(trim(NEW.reviewer)) = 0 OR NEW.reviewed_on IS NULL OR
    NEW.privacy_reviewed != 1 OR (NEW.review_tier = 'silver' AND NEW.split != 'train')
)
BEGIN
    SELECT RAISE(ABORT, 'accepted scenario requires outcome, privacy and review evidence');
END;
CREATE TRIGGER IF NOT EXISTS scenario_insert_requires_review
BEFORE INSERT ON scenario
WHEN NEW.quality_status = 'accepted' AND (
    NEW.expected_outcome = 'pending_review' OR NEW.review_tier = 'pending_review' OR
    NEW.reviewer IS NULL OR length(trim(NEW.reviewer)) = 0 OR NEW.reviewed_on IS NULL OR
    NEW.privacy_reviewed != 1 OR (NEW.review_tier = 'silver' AND NEW.split != 'train')
)
BEGIN
    SELECT RAISE(ABORT, 'accepted scenario requires outcome, privacy and review evidence');
END;
"""


def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        cols = {row[1] for row in conn.execute("PRAGMA table_info(scenario)")}
        changes = {
            "expected_outcome": "TEXT NOT NULL DEFAULT 'pending_review' CHECK (expected_outcome IN ('pending_review', 'provision_match', 'insufficient_information', 'out_of_scope'))",
            "review_tier": "TEXT NOT NULL DEFAULT 'pending_review' CHECK (review_tier IN ('pending_review', 'self_reviewed', 'independently_reviewed', 'silver'))",
            "reviewer": "TEXT",
            "reviewed_on": "TEXT",
        }
        for name, definition in changes.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE scenario ADD COLUMN {name} {definition}")
        conn.executescript(TRIGGER)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.execute(f"PRAGMA user_version={max(version, 2)}")
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
        print("Dataset model migration complete: review/outcome fields and acceptance gate")


if __name__ == "__main__":
    main()
