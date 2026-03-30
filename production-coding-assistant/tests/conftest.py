from __future__ import annotations

import pytest

import assistant_backend.config as config
import assistant_backend.storage.database as database


@pytest.fixture(autouse=True)
def clear_settings_cache():
    config.get_cached_settings.cache_clear()
    yield
    config.get_cached_settings.cache_clear()


@pytest.fixture
def isolated_state_db(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "APP_DIR", tmp_path)
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "state.db")
    database.init_db()
    return database
