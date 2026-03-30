from __future__ import annotations

import importlib
from types import SimpleNamespace

from assistant_backend.config import WebSearchSettings

web_search_tool = importlib.import_module("assistant_backend.tools.web_search")


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload


def test_web_search_normalizes_and_caches_brave_results(monkeypatch, isolated_state_db):
    settings = SimpleNamespace(
        web_search=WebSearchSettings(
            enabled=True,
            provider="brave",
            timeout_seconds=5,
            max_results=5,
            cache_ttl_seconds=300,
        )
    )
    monkeypatch.setattr(web_search_tool, "get_cached_settings", lambda: settings)
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "test-brave-key")

    calls = {"count": 0}

    def fake_request(method, url, headers=None, params=None, timeout=None):
        calls["count"] += 1
        assert method == "GET"
        assert "X-Subscription-Token" in headers
        return FakeResponse(
            200,
            {
                "web": {
                    "results": [
                        {
                            "title": "FastAPI Best Practices",
                            "url": "https://example.com/article?utm_source=test&fbclid=123",
                            "description": "A" * 260,
                            "page_age": "2026-03-20",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(web_search_tool.requests, "request", fake_request)

    first = web_search_tool.web_search(
        " latest   FastAPI best practices 2026 ",
        5,
        provider="brave",
        session_id="session-1",
    )
    second = web_search_tool.web_search(
        "latest FastAPI best practices 2026",
        5,
        provider="brave",
        session_id="session-1",
    )

    assert calls["count"] == 1
    assert first == second
    assert first[0]["source"] == "example.com"
    assert "utm_source" not in first[0]["link"]
    assert "fbclid" not in first[0]["link"]
    assert len(first[0]["snippet"]) <= 200


def test_web_search_supports_serpapi_shape(monkeypatch, isolated_state_db):
    settings = SimpleNamespace(
        web_search=WebSearchSettings(
            enabled=True,
            provider="serpapi",
            timeout_seconds=5,
            max_results=4,
            cache_ttl_seconds=300,
        )
    )
    monkeypatch.setattr(web_search_tool, "get_cached_settings", lambda: settings)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-serp-key")

    def fake_request(method, url, headers=None, params=None, timeout=None):
        assert params["engine"] == "google"
        return FakeResponse(
            200,
            {
                "organic_results": [
                    {
                        "title": "React Vite Guide",
                        "link": "https://vite.dev/guide/?utm_campaign=x",
                        "snippet": "Official guide for building React apps with Vite.",
                        "date": "2026-03-10",
                    }
                ]
            },
        )

    monkeypatch.setattr(web_search_tool.requests, "request", fake_request)
    results = web_search_tool.web_search("react vite guide", 3, provider="serpapi")

    assert results == [
        {
            "title": "React Vite Guide",
            "link": "https://vite.dev/guide/",
            "snippet": "Official guide for building React apps with Vite.",
            "source": "vite.dev",
            "published_at": "2026-03-10",
        }
    ]
