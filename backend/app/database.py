from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_uid TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    active_narrative TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_owner_updated
                    ON sessions(owner_uid, updated_at DESC);

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    owner_uid TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    text TEXT NOT NULL,
                    structured_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_created
                    ON messages(session_id, created_at);

                CREATE TABLE IF NOT EXISTS analyses (
                    analysis_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
                    owner_uid TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    kb_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS analyses_session_created
                    ON analyses(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS drafts (
                    draft_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    owner_uid TEXT NOT NULL,
                    analysis_id TEXT NOT NULL REFERENCES analyses(analysis_id),
                    fields_json TEXT NOT NULL,
                    provision_ids_json TEXT NOT NULL,
                    rendered_text TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('preview', 'needs_reanalysis', 'saved', 'cancelled')),
                    internal_reference TEXT,
                    confirmed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS drafts_owner_updated
                    ON drafts(owner_uid, updated_at DESC);

                CREATE TABLE IF NOT EXISTS draft_events (
                    event_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL REFERENCES drafts(draft_id) ON DELETE CASCADE,
                    owner_uid TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL UNIQUE REFERENCES drafts(draft_id),
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    owner_uid TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('submitted', 'information_requested', 'under_review',
                         'ready_to_refer', 'out_of_scope', 'closed')),
                    reporter_role TEXT NOT NULL,
                    reporter_relationship TEXT NOT NULL,
                    verified_phone TEXT,
                    submission_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS cases_owner_updated
                    ON cases(owner_uid, updated_at DESC);
                CREATE INDEX IF NOT EXISTS cases_status_updated
                    ON cases(status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS case_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    actor_uid TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS case_events_case_created
                    ON case_events(case_id, created_at);

                CREATE TABLE IF NOT EXISTS case_messages (
                    message_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    actor_uid TEXT NOT NULL,
                    actor_role TEXT NOT NULL CHECK(actor_role IN ('citizen', 'reviewer')),
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS case_messages_case_created
                    ON case_messages(case_id, created_at);

                CREATE TABLE IF NOT EXISTS case_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    owner_uid TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    bytes BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def create_session(self, owner_uid: str, title: str) -> dict[str, Any]:
        session_id, now = opaque_id("ses"), utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, 'active', '', ?, ?)",
                (session_id, owner_uid, title.strip(), now, now),
            )
        return self.get_session(owner_uid, session_id)  # type: ignore[return-value]

    def list_sessions(self, owner_uid: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions WHERE owner_uid = ? AND status = 'active' ORDER BY updated_at DESC", (owner_uid,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, owner_uid: str, session_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ? AND owner_uid = ?",
                (session_id, owner_uid),
            ).fetchone()
        return self._row(row)

    def set_narrative(self, owner_uid: str, session_id: str, narrative: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET active_narrative = ?, updated_at = ? "
                "WHERE session_id = ? AND owner_uid = ?",
                (narrative, now, session_id, owner_uid),
            )
            if cursor.rowcount != 1:
                raise KeyError(session_id)

    def set_session_title(self, owner_uid: str, session_id: str, title: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? "
                "WHERE session_id = ? AND owner_uid = ?",
                (title.strip(), now, session_id, owner_uid),
            )
            if cursor.rowcount != 1:
                raise KeyError(session_id)

    def add_message(
        self, owner_uid: str, session_id: str, role: str, text: str,
        structured: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message_id, now = opaque_id("msg"), utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?)",
                (message_id, session_id, owner_uid, role, text,
                 json.dumps(structured, ensure_ascii=False) if structured is not None else None, now),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ? AND owner_uid = ?",
                (now, session_id, owner_uid),
            )
        return {
            "id": message_id, "role": role, "text": text,
            "structured": structured, "created_at": now,
        }

    def list_messages(self, owner_uid: str, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT message_id AS id, role, text, structured_json, created_at "
                "FROM messages WHERE session_id = ? AND owner_uid = ? ORDER BY created_at, rowid",
                (session_id, owner_uid),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["structured"] = json.loads(item.pop("structured_json")) if item["structured_json"] else None
            result.append(item)
        return result

    def save_analysis(
        self, owner_uid: str, session_id: str | None, narrative: str,
        result: dict[str, Any], model_version: str, kb_version: str,
    ) -> dict[str, Any]:
        analysis_id, now = opaque_id("ana"), utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (analysis_id, session_id, owner_uid, narrative,
                 json.dumps(result, ensure_ascii=False), model_version, kb_version, now),
            )
        return {
            "analysis_id": analysis_id, "session_id": session_id,
            "narrative": narrative, "result": result,
            "model_version": model_version, "kb_version": kb_version, "created_at": now,
        }

    def latest_analysis(self, owner_uid: str, session_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM analyses WHERE session_id = ? AND owner_uid = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (session_id, owner_uid),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json"))
        return item

    def create_draft(
        self, owner_uid: str, session_id: str, analysis_id: str,
        fields: dict[str, str], provision_ids: list[str], rendered_text: str,
    ) -> dict[str, Any]:
        draft_id, now = opaque_id("drf"), utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'preview', NULL, NULL, ?, ?)",
                (draft_id, session_id, owner_uid, analysis_id,
                 json.dumps(fields, ensure_ascii=False), json.dumps(provision_ids), rendered_text, now, now),
            )
            connection.execute(
                "INSERT INTO draft_events VALUES (?, ?, ?, 'created', 1, '{}', ?)",
                (opaque_id("evt"), draft_id, owner_uid, now),
            )
        return self.get_draft(owner_uid, draft_id)  # type: ignore[return-value]

    def get_draft(self, owner_uid: str, draft_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE draft_id = ? AND owner_uid = ?", (draft_id, owner_uid)
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["fields"] = json.loads(item.pop("fields_json"))
        item["provision_ids"] = json.loads(item.pop("provision_ids_json"))
        return item

    def update_draft(
        self, owner_uid: str, draft_id: str, expected_version: int,
        fields: dict[str, str], rendered_text: str, status: str, event_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        new_version, now = expected_version + 1, utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE drafts SET fields_json = ?, rendered_text = ?, version = ?, status = ?, updated_at = ? "
                "WHERE draft_id = ? AND owner_uid = ? AND version = ? AND status IN ('preview', 'needs_reanalysis', 'saved')",
                (json.dumps(fields, ensure_ascii=False), rendered_text, new_version, status, now,
                 draft_id, owner_uid, expected_version),
            )
            if cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                return None
            connection.execute(
                "INSERT INTO draft_events VALUES (?, ?, ?, 'edited', ?, ?, ?)",
                (opaque_id("evt"), draft_id, owner_uid, new_version,
                 json.dumps(event_data, ensure_ascii=False), now),
            )
            connection.execute("COMMIT")
        return self.get_draft(owner_uid, draft_id)

    def replace_draft_analysis(
        self, owner_uid: str, draft_id: str, expected_version: int, analysis_id: str,
        provision_ids: list[str], rendered_text: str,
    ) -> dict[str, Any] | None:
        new_version, now = expected_version + 1, utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE drafts SET analysis_id = ?, provision_ids_json = ?, rendered_text = ?, "
                "version = ?, status = 'preview', updated_at = ? "
                "WHERE draft_id = ? AND owner_uid = ? AND version = ? AND status = 'needs_reanalysis'",
                (analysis_id, json.dumps(provision_ids), rendered_text, new_version, now,
                 draft_id, owner_uid, expected_version),
            )
            if cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                return None
            connection.execute(
                "INSERT INTO draft_events VALUES (?, ?, ?, 'reanalyzed', ?, ?, ?)",
                (opaque_id("evt"), draft_id, owner_uid, new_version,
                 json.dumps({"analysis_id": analysis_id, "provision_ids": provision_ids}), now),
            )
            connection.execute("COMMIT")
        return self.get_draft(owner_uid, draft_id)

    def transition_draft(
        self, owner_uid: str, draft_id: str, expected_version: int,
        from_status: str, to_status: str, internal_reference: str | None = None,
    ) -> dict[str, Any] | None:
        new_version, now = expected_version + 1, utc_now()
        confirmed_at = now if to_status == "saved" else None
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE drafts SET version = ?, status = ?, internal_reference = ?, confirmed_at = ?, updated_at = ? "
                "WHERE draft_id = ? AND owner_uid = ? AND version = ? AND status = ?",
                (new_version, to_status, internal_reference, confirmed_at, now,
                 draft_id, owner_uid, expected_version, from_status),
            )
            if cursor.rowcount != 1:
                connection.execute("ROLLBACK")
                return None
            connection.execute(
                "INSERT INTO draft_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (opaque_id("evt"), draft_id, owner_uid, to_status, new_version,
                 json.dumps({"internal_reference": internal_reference}), now),
            )
            connection.execute("COMMIT")
        return self.get_draft(owner_uid, draft_id)

    def delete_saved_draft(self, owner_uid: str, draft_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM drafts WHERE draft_id = ? AND owner_uid = ? AND status = 'saved'",
                (draft_id, owner_uid),
            )
        return cursor.rowcount == 1

    def has_case_for_draft(self, draft_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM cases WHERE draft_id = ?", (draft_id,)).fetchone() is not None

    def list_drafts(self, owner_uid: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT draft_id FROM drafts WHERE owner_uid = ? AND status != 'cancelled' "
                "ORDER BY updated_at DESC", (owner_uid,),
            ).fetchall()
        return [item for row in rows if (item := self.get_draft(owner_uid, row["draft_id"]))]

    def remove_or_archive_session(self, owner_uid: str, session_id: str) -> str | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT session_id FROM sessions WHERE session_id = ? AND owner_uid = ?",
                (session_id, owner_uid),
            ).fetchone()
            if session is None:
                connection.execute("ROLLBACK")
                return None
            has_case = connection.execute(
                "SELECT 1 FROM cases WHERE session_id = ?", (session_id,)
            ).fetchone()
            if has_case:
                connection.execute(
                    "UPDATE sessions SET status = 'archived', updated_at = ? WHERE session_id = ?",
                    (utc_now(), session_id),
                )
                action = "archived"
            else:
                connection.execute("DELETE FROM drafts WHERE session_id = ?", (session_id,))
                connection.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                action = "deleted"
            connection.execute("COMMIT")
        return action

    def create_case(
        self, owner_uid: str, draft: dict[str, Any], reporter_role: str,
        reporter_relationship: str, affected_person_name: str, verified_phone: str | None,
    ) -> dict[str, Any] | None:
        now = utc_now()
        case_id = "VDL-" + datetime.now(UTC).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper()
        snapshot = {
            "fields": draft["fields"], "provision_ids": draft["provision_ids"],
            "rendered_text": draft["rendered_text"], "draft_version": draft["version"],
            "affected_person_name": affected_person_name,
        }
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT case_id FROM cases WHERE draft_id = ?", (draft["draft_id"],)
            ).fetchone()
            if existing:
                connection.execute("ROLLBACK")
                return None
            connection.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, 'submitted', ?, ?, ?, ?, ?, ?)",
                (case_id, draft["draft_id"], draft["session_id"], owner_uid,
                 reporter_role, reporter_relationship, verified_phone,
                 json.dumps(snapshot, ensure_ascii=False), now, now),
            )
            connection.execute(
                "INSERT INTO case_events VALUES (?, ?, ?, 'submitted', ?, ?)",
                (opaque_id("evt"), case_id, owner_uid,
                 json.dumps({"reporter_role": reporter_role, "declaration_accepted": True}), now),
            )
            connection.execute("COMMIT")
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["submission"] = json.loads(item.pop("submission_json"))
        return item

    def list_cases(self, owner_uid: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if owner_uid is None:
                rows = connection.execute("SELECT case_id FROM cases ORDER BY updated_at DESC").fetchall()
            else:
                rows = connection.execute(
                    "SELECT case_id FROM cases WHERE owner_uid = ? ORDER BY updated_at DESC",
                    (owner_uid,),
                ).fetchall()
        return [item for row in rows if (item := self.get_case(row["case_id"]))]

    def case_history(self, case_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            events = connection.execute(
                "SELECT event_id, actor_uid, event_type, details_json, created_at "
                "FROM case_events WHERE case_id = ? ORDER BY created_at, rowid", (case_id,)
            ).fetchall()
            messages = connection.execute(
                "SELECT message_id, actor_uid, actor_role, text, created_at "
                "FROM case_messages WHERE case_id = ? ORDER BY created_at, rowid", (case_id,)
            ).fetchall()
            evidence = connection.execute(
                "SELECT evidence_id, filename, content_type, sha256, length(bytes) AS size, created_at "
                "FROM case_evidence WHERE case_id = ? ORDER BY created_at, rowid", (case_id,)
            ).fetchall()
        return {
            "events": [{**dict(row), "details": json.loads(row["details_json"])} for row in events],
            "messages": [dict(row) for row in messages],
            "evidence": [dict(row) for row in evidence],
        }

    def add_case_message(self, case_id: str, actor_uid: str, actor_role: str, text: str) -> dict[str, Any]:
        item = {
            "message_id": opaque_id("cmsg"), "case_id": case_id,
            "actor_uid": actor_uid, "actor_role": actor_role,
            "text": text, "created_at": utc_now(),
        }
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO case_messages VALUES (?, ?, ?, ?, ?, ?)", tuple(item.values())
            )
            if actor_role == "citizen":
                current = connection.execute(
                    "SELECT status FROM cases WHERE case_id = ?", (case_id,)
                ).fetchone()
                if current and current["status"] == "information_requested":
                    connection.execute(
                        "UPDATE cases SET status = 'under_review' WHERE case_id = ?", (case_id,)
                    )
                    connection.execute(
                        "INSERT INTO case_events VALUES (?, ?, ?, 'information_received', ?, ?)",
                        (opaque_id("evt"), case_id, actor_uid,
                         json.dumps({"reason": "Your reply has been sent to the review queue."}), item["created_at"]),
                    )
            connection.execute(
                "UPDATE cases SET updated_at = ? WHERE case_id = ?",
                (item["created_at"], case_id),
            )
            connection.execute("COMMIT")
        return item

    def request_case_review(self, case_id: str, owner_uid: str, reason: str) -> dict[str, Any] | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            case = connection.execute(
                "SELECT status FROM cases WHERE case_id = ? AND owner_uid = ?", (case_id, owner_uid)
            ).fetchone()
            if not case or case["status"] != "closed":
                connection.execute("ROLLBACK")
                return None
            connection.execute(
                "UPDATE cases SET status = 'under_review', updated_at = ? WHERE case_id = ?",
                (now, case_id),
            )
            connection.execute(
                "INSERT INTO case_events VALUES (?, ?, ?, 'review_requested', ?, ?)",
                (opaque_id("evt"), case_id, owner_uid,
                 json.dumps({"reason": reason}, ensure_ascii=False), now),
            )
            connection.execute("COMMIT")
        return self.get_case(case_id)

    def decide_case(self, case_id: str, actor_uid: str, action: str, reason: str) -> dict[str, Any]:
        status_map = {
            "request_information": "information_requested", "under_review": "under_review",
            "ready_to_refer": "ready_to_refer", "out_of_scope": "out_of_scope",
            "close": "closed", "reopen": "under_review",
        }
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?",
                (status_map[action], now, case_id),
            )
            connection.execute(
                "INSERT INTO case_events VALUES (?, ?, ?, ?, ?, ?)",
                (opaque_id("evt"), case_id, actor_uid, action,
                 json.dumps({"reason": reason}, ensure_ascii=False), now),
            )
            connection.execute("COMMIT")
        return self.get_case(case_id)  # type: ignore[return-value]

    def add_evidence(
        self, case_id: str, owner_uid: str, filename: str,
        content_type: str, sha256: str, data: bytes,
    ) -> dict[str, Any]:
        item = {
            "evidence_id": opaque_id("evd"), "filename": filename,
            "content_type": content_type, "sha256": sha256,
            "size": len(data), "created_at": utc_now(),
        }
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO case_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (item["evidence_id"], case_id, owner_uid, filename,
                 content_type, sha256, data, item["created_at"]),
            )
            connection.execute(
                "INSERT INTO case_events VALUES (?, ?, ?, 'evidence_added', ?, ?)",
                (opaque_id("evt"), case_id, owner_uid,
                 json.dumps({"evidence_id": item["evidence_id"], "filename": filename}), item["created_at"]),
            )
            connection.execute("UPDATE cases SET updated_at = ? WHERE case_id = ?", (item["created_at"], case_id))
        return item

    def get_evidence(self, case_id: str, evidence_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM case_evidence WHERE case_id = ? AND evidence_id = ?",
                (case_id, evidence_id),
            ).fetchone()
        return self._row(row)
