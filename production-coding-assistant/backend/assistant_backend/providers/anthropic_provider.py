from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT_SECONDS = 120
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 8192
_STREAM_CHUNK_SIZE = 1024


def _get_api_key(api_key_env: str) -> str:
    key = os.getenv(api_key_env, "").strip()
    if not key:
        raise ValueError(f"Missing environment variable: {api_key_env}")
    return key


def _build_headers(api_key: str, stream: bool = False) -> dict[str, str]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    if stream:
        headers["accept"] = "text/event-stream"
    return headers


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Anthropic Messages API (blocking) and return a ProviderResponse."""
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling Anthropic API (blocking) model=%s", model)
    try:
        response = requests.post(
            _API_URL,
            headers=_build_headers(api_key),
            json={
                "model": model,
                "max_tokens": _MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"Anthropic API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Anthropic API HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    payload = response.json()
    blocks = payload.get("content", [])
    content = "\n".join(
        block.get("text", "") for block in blocks if block.get("type") == "text"
    )
    logger.debug("Anthropic response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="anthropic", model=model)


def _anthropic_stream(response: requests.Response) -> Iterator[str]:
    """Parse Anthropic SSE events and yield text delta tokens."""
    assembled: list[str] = []
    try:
        for raw_line in response.iter_lines(chunk_size=_STREAM_CHUNK_SIZE):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data: "):
                continue
            payload_str = line[6:].strip()
            try:
                event = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type", "")
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    token = delta.get("text", "")
                    if token:
                        assembled.append(token)
                        yield token
            elif event_type == "message_stop":
                break
    finally:
        logger.debug(
            "Anthropic stream finished (%d chars assembled)",
            sum(len(t) for t in assembled),
        )


def generate_stream(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Anthropic Messages API in streaming mode.

    Returns a ProviderResponse whose stream_iter yields token strings.
    """
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling Anthropic API (streaming) model=%s", model)
    try:
        response = requests.post(
            _API_URL,
            headers=_build_headers(api_key, stream=True),
            json={
                "model": model,
                "max_tokens": _MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
            stream=True,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"Anthropic streaming API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Anthropic streaming HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    return ProviderResponse(
        content="",
        provider="anthropic",
        model=model,
        stream_iter=_anthropic_stream(response),
    )

