from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from assistant_backend.config import get_cached_settings
from assistant_backend.storage.database import (
    get_cached_web_search,
    log_tool_invocation,
    store_cached_web_search,
)

logger = logging.getLogger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
_BING_SEARCH_URL = "https://api.bing.microsoft.com/v7.0/search"
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}


def _normalize_query(query: str) -> str:
    normalized = " ".join(query.strip().split())
    if not normalized:
        raise ValueError("web_search query cannot be empty")
    return normalized


def _clamp_num_results(value: int, maximum: int) -> int:
    return max(1, min(int(value), maximum))


def _hash_query(provider: str, query: str, num_results: int) -> str:
    payload = f"{provider}|{query}|{num_results}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _truncate_snippet(text: str, max_chars: int = 200) -> str:
    snippet = " ".join((text or "").split())
    if len(snippet) <= max_chars:
        return snippet
    return snippet[: max_chars - 1].rstrip() + "…"


def _sanitize_link(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    clean = parsed._replace(query=urlencode(query_items, doseq=True), fragment="")
    return urlunparse(clean)


def _source_from_link(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _iso_or_empty(value: Any) -> str:
    if not value:
        return ""
    text = str(value).strip()
    return text


def _normalize_result(
    title: str,
    link: str,
    snippet: str,
    *,
    source: str = "",
    published_at: str = "",
) -> dict[str, str]:
    clean_link = _sanitize_link(link)
    return {
        "title": " ".join((title or "").split()),
        "link": clean_link,
        "snippet": _truncate_snippet(snippet),
        "source": source or _source_from_link(clean_link),
        "published_at": _iso_or_empty(published_at),
    }


def _raise_for_status_with_context(response: requests.Response, provider: str) -> None:
    if response.status_code < 400:
        return
    text = response.text[:200]
    raise RuntimeError(f"{provider} web search HTTP error: {response.status_code} {text}")


def _request_json(
    provider: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    response: requests.Response | None = None
    for attempt in range(1, 4):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                timeout=timeout_seconds,
            )
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = 2 * attempt
                if retry_after:
                    try:
                        delay = max(1, min(int(float(retry_after)), 15))
                    except ValueError:
                        logger.debug("Invalid Retry-After header for %s: %s", provider, retry_after)
                logger.warning("%s web search rate-limited; retrying in %ss", provider, delay)
                time.sleep(delay)
                continue
            _raise_for_status_with_context(response, provider)
            return response.json()
        except requests.Timeout as exc:
            if attempt == 3:
                raise RuntimeError(f"{provider} web search timed out") from exc
            time.sleep(attempt)
        except ValueError as exc:
            raise RuntimeError(f"{provider} web search returned invalid JSON") from exc
    raise RuntimeError(f"{provider} web search failed without a response")


def _search_brave(query: str, num_results: int, timeout_seconds: int) -> list[dict[str, str]]:
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing BRAVE_SEARCH_API_KEY")
    payload = _request_json(
        "brave",
        "GET",
        _BRAVE_SEARCH_URL,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
        params={
            "q": query,
            "count": num_results,
            "country": "us",
            "search_lang": "en",
        },
        timeout_seconds=timeout_seconds,
    )
    results = payload.get("web", {}).get("results", [])
    normalized: list[dict[str, str]] = []
    for item in results[:num_results]:
        normalized.append(
            _normalize_result(
                item.get("title", ""),
                item.get("url", ""),
                item.get("description", ""),
                published_at=item.get("page_age", ""),
            )
        )
    return normalized


def _search_serpapi(query: str, num_results: int, timeout_seconds: int) -> list[dict[str, str]]:
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing SERPAPI_API_KEY")
    payload = _request_json(
        "serpapi",
        "GET",
        _SERPAPI_SEARCH_URL,
        headers={"Accept": "application/json"},
        params={
            "engine": "google",
            "q": query,
            "num": num_results,
            "api_key": api_key,
        },
        timeout_seconds=timeout_seconds,
    )
    results = payload.get("organic_results", [])
    normalized: list[dict[str, str]] = []
    for item in results[:num_results]:
        normalized.append(
            _normalize_result(
                item.get("title", ""),
                item.get("link", ""),
                item.get("snippet", ""),
                published_at=item.get("date", "") or item.get("displayed_date", ""),
            )
        )
    return normalized


def _search_bing(query: str, num_results: int, timeout_seconds: int) -> list[dict[str, str]]:
    api_key = os.getenv("BING_SEARCH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing BING_SEARCH_API_KEY")
    payload = _request_json(
        "bing",
        "GET",
        _BING_SEARCH_URL,
        headers={
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": api_key,
        },
        params={
            "q": query,
            "count": num_results,
            "textDecorations": False,
            "textFormat": "Raw",
        },
        timeout_seconds=timeout_seconds,
    )
    results = payload.get("webPages", {}).get("value", [])
    normalized: list[dict[str, str]] = []
    for item in results[:num_results]:
        normalized.append(
            _normalize_result(
                item.get("name", ""),
                item.get("url", ""),
                item.get("snippet", ""),
                published_at=item.get("dateLastCrawled", ""),
            )
        )
    return normalized


def _search_live(provider: str, query: str, num_results: int, timeout_seconds: int) -> list[dict[str, str]]:
    if provider == "brave":
        return _search_brave(query, num_results, timeout_seconds)
    if provider == "serpapi":
        return _search_serpapi(query, num_results, timeout_seconds)
    if provider == "bing":
        return _search_bing(query, num_results, timeout_seconds)
    raise ValueError(f"Unsupported web search provider: {provider}")


def web_search(
    query: str,
    num_results: int = 5,
    provider: str | None = None,
    *,
    session_id: str | None = None,
) -> list[dict[str, str]]:
    settings = get_cached_settings()
    search_settings = settings.web_search
    if not search_settings.enabled:
        raise RuntimeError("Web search is disabled in settings")

    resolved_provider = (provider or search_settings.provider).strip().lower()
    normalized_query = _normalize_query(query)
    bounded_results = _clamp_num_results(num_results, search_settings.max_results)
    query_hash = _hash_query(resolved_provider, normalized_query, bounded_results)

    cached = get_cached_web_search(resolved_provider, query_hash)
    if cached is not None:
        log_tool_invocation(
            session_id,
            "web_search",
            {
                "provider": resolved_provider,
                "query": normalized_query,
                "num_results": bounded_results,
                "cache_hit": True,
            },
            {"results": cached["results"]},
            success=True,
        )
        return cached["results"]

    try:
        results = _search_live(
            resolved_provider,
            normalized_query,
            bounded_results,
            search_settings.timeout_seconds,
        )
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=search_settings.cache_ttl_seconds)
        ).isoformat()
        store_cached_web_search(resolved_provider, query_hash, results, expires_at)
        log_tool_invocation(
            session_id,
            "web_search",
            {
                "provider": resolved_provider,
                "query": normalized_query,
                "num_results": bounded_results,
                "cache_hit": False,
            },
            {"results": results},
            success=True,
        )
        return results
    except Exception as exc:
        log_tool_invocation(
            session_id,
            "web_search",
            {
                "provider": resolved_provider,
                "query": normalized_query,
                "num_results": bounded_results,
                "cache_hit": False,
            },
            success=False,
            error_text=str(exc),
        )
        raise
