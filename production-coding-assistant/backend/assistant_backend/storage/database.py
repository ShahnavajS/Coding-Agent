from __future__ import annotations

import logging
import sqlite3
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from assistant_backend.config import APP_DIR

logger = logging.getLogger(__name__)

DB_PATH = APP_DIR / "state.db"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables if they do not already exist, and migrate old schemas."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=OFF;

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS pending_diffs (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                original_content TEXT NOT NULL,
                modified_content TEXT NOT NULL,
                validation_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                snapshot_path TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON session_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_path
                ON checkpoints(path);

            PRAGMA foreign_keys=ON;
            """
        )
    logger.info("Database initialised at %s", DB_PATH)


@contextmanager
def db_cursor() -> Iterator[sqlite3.Cursor]:
    """Yield a cursor, commit on success, rollback on error."""
    init_db()
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── sessions ────────────────────────────────────────────────────────

def create_session(title: str | None = None) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = utcnow()
    session_title = (title or "New Session").strip() or "New Session"
    with db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, session_title, now, now),
        )
    logger.debug("Created session %s: %r", session_id, session_title)
    return {"id": session_id, "title": session_title, "createdAt": now, "updatedAt": now}


def list_sessions() -> list[dict[str, Any]]:
    with db_cursor() as cursor:
        rows = cursor.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": r["id"], "title": r["title"],
         "createdAt": r["created_at"], "updatedAt": r["updated_at"]}
        for r in rows
    ]


def delete_session(session_id: str) -> bool:
    """Delete a session and all its messages manually (no CASCADE dependency)."""
    with db_cursor() as cursor:
        # Always delete child rows first — works regardless of FK schema version
        cursor.execute(
            "DELETE FROM session_messages WHERE session_id = ?", (session_id,)
        )
        result = cursor.execute(
            "DELETE FROM sessions WHERE id = ?", (session_id,)
        )
    deleted = result.rowcount > 0
    if deleted:
        logger.info("Deleted session %s", session_id)
    return deleted


# ── messages ────────────────────────────────────────────────────────

def append_message(
    session_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    now = utcnow()
    payload = metadata or {}
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO session_messages
                (id, session_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, json.dumps(payload), now),
        )
        cursor.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
    logger.debug("Appended %s message to session %s", role, session_id)
    return {"id": message_id, "role": role, "content": content,
            "metadata": payload, "createdAt": now}


def get_messages(session_id: str) -> list[dict[str, Any]]:
    with db_cursor() as cursor:
        rows = cursor.execute(
            """
            SELECT id, role, content, metadata_json, created_at
            FROM session_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"],
         "metadata": json.loads(r["metadata_json"]), "createdAt": r["created_at"]}
        for r in rows
    ]


# ── diffs ────────────────────────────────────────────────────────────

def store_pending_diff(
    path: str,
    original_content: str,
    modified_content: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    diff_id = str(uuid.uuid4())
    now = utcnow()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO pending_diffs
                (id, path, original_content, modified_content, validation_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (diff_id, path, original_content, modified_content, json.dumps(validation), now),
        )
    logger.debug("Stored pending diff %s for %s", diff_id, path)
    return {"id": diff_id, "path": path, "originalContent": original_content,
            "modifiedContent": modified_content, "validation": validation, "createdAt": now}


def get_pending_diff(diff_id: str) -> dict[str, Any] | None:
    with db_cursor() as cursor:
        row = cursor.execute(
            """
            SELECT id, path, original_content, modified_content, validation_json, created_at
            FROM pending_diffs WHERE id = ?
            """,
            (diff_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "path": row["path"],
            "originalContent": row["original_content"],
            "modifiedContent": row["modified_content"],
            "validation": json.loads(row["validation_json"]),
            "createdAt": row["created_at"]}


def delete_pending_diff(diff_id: str) -> None:
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM pending_diffs WHERE id = ?", (diff_id,))
    logger.debug("Deleted pending diff %s", diff_id)


# ── checkpoints ──────────────────────────────────────────────────────

def store_checkpoint(path: str, snapshot_path: str, summary: str) -> dict[str, Any]:
    checkpoint_id = str(uuid.uuid4())
    now = utcnow()
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO checkpoints (id, path, snapshot_path, summary, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (checkpoint_id, path, snapshot_path, summary, now),
        )
    logger.info("Stored checkpoint %s for %s", checkpoint_id, path)
    return {"id": checkpoint_id, "path": path, "snapshotPath": snapshot_path,
            "summary": summary, "createdAt": now}


def get_checkpoint(checkpoint_id: str) -> dict[str, Any] | None:
    with db_cursor() as cursor:
        row = cursor.execute(
            "SELECT id, path, snapshot_path, summary, created_at FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "path": row["path"], "snapshotPath": row["snapshot_path"],
            "summary": row["summary"], "createdAt": row["created_at"]}
