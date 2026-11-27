"""Add an honestly named AI-reviewed tier without changing statute or scenario data.

SQLite cannot widen a CHECK constraint in place. Rebuild only the scenario table,
preserving its rows and all referencing child tables. Safe to rerun.
"""

from __future__ import annotations

import sqlite3

from build_full_kb import DB_PATH
from migrate_dataset_model import TRIGGER


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='scenario'"
        ).fetchone()[0]
        if "'ai_reviewed'" not in table_sql:
            old_list = "'pending_review', 'self_reviewed', 'independently_reviewed', 'silver'"
            new_list = "'pending_review', 'ai_reviewed', 'self_reviewed', 'independently_reviewed', 'silver'"
            if old_list not in table_sql or "CREATE TABLE scenario (" not in table_sql:
                raise RuntimeError("Unexpected scenario schema; refusing automatic migration")
            new_sql = table_sql.replace("CREATE TABLE scenario (", "CREATE TABLE scenario_migrating (", 1)
            new_sql = new_sql.replace(old_list, new_list, 1)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(scenario)")]
            names = ", ".join('"' + name + '"' for name in columns)
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(new_sql)
                conn.execute(f"INSERT INTO scenario_migrating ({names}) SELECT {names} FROM scenario")
                conn.execute("DROP TABLE scenario")
                conn.execute("ALTER TABLE scenario_migrating RENAME TO scenario")
                conn.execute("CREATE INDEX idx_scenario_split ON scenario(split, quality_status)")
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("Foreign-key check failed after scenario migration")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(TRIGGER)
        conn.execute("PRAGMA user_version=3")
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.commit()
        print("AI-reviewed tier available; existing scenario rows preserved")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
