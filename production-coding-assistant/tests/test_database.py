"""Tests for assistant_backend.storage.database — using a temporary DB."""
from __future__ import annotations

import pytest
from unittest.mock import patch
from pathlib import Path


def _patch_db(tmp_path: Path):
    """Return a context manager that redirects the DB to a temp directory."""
    import assistant_backend.storage.database as db_module
    fake_app_dir = tmp_path / ".assistant"
    fake_app_dir.mkdir()
    return patch.multiple(
        db_module,
        APP_DIR=fake_app_dir,
        DB_PATH=fake_app_dir / "state.db",
    )


class TestSessions:
    def test_create_and_list_session(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            session = db.create_session("Test Session")
            assert session["title"] == "Test Session"
            assert "id" in session

            sessions = db.list_sessions()
            assert any(s["id"] == session["id"] for s in sessions)

    def test_delete_session(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            session = db.create_session("To Delete")
            deleted = db.delete_session(session["id"])
            assert deleted is True
            sessions = db.list_sessions()
            assert all(s["id"] != session["id"] for s in sessions)

    def test_delete_nonexistent_session_returns_false(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            assert db.delete_session("does-not-exist") is False

    def test_default_title_used_when_none(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            session = db.create_session(None)
            assert session["title"] == "New Session"


class TestMessages:
    def test_append_and_get_messages(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            session = db.create_session("Msg Test")
            db.append_message(session["id"], "user", "Hello")
            db.append_message(session["id"], "assistant", "Hi there")
            messages = db.get_messages(session["id"])
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[1]["role"] == "assistant"

    def test_messages_ordered_by_time(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            session = db.create_session("Order Test")
            for i in range(5):
                db.append_message(session["id"], "user", f"message {i}")
            messages = db.get_messages(session["id"])
            contents = [m["content"] for m in messages]
            assert contents == [f"message {i}" for i in range(5)]


class TestPendingDiffs:
    def test_store_and_get_diff(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            diff = db.store_pending_diff(
                "main.py", "old content", "new content", {"ok": True}
            )
            assert "id" in diff
            retrieved = db.get_pending_diff(diff["id"])
            assert retrieved is not None
            assert retrieved["modifiedContent"] == "new content"

    def test_get_nonexistent_diff_returns_none(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            assert db.get_pending_diff("fake-id") is None

    def test_delete_diff(self, tmp_path):
        with _patch_db(tmp_path):
            from assistant_backend.storage import database as db
            db.init_db()
            diff = db.store_pending_diff("f.py", "", "x=1", {"ok": True})
            db.delete_pending_diff(diff["id"])
            assert db.get_pending_diff(diff["id"]) is None
