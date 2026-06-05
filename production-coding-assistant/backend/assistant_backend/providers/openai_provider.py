from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import requests

from assistant_backend.providers.base import ProviderResponse, StreamNotSupportedError

logger = logging.getLogger(__name__)

_API_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT_SECONDS = 120  # longer for streaming
_STREAM_CHUNK_SIZE = 1024


def _get_api_key(api_key_env: str) -> str:
    key = os.getenv(api_key_env, "").strip()
    if not key:
        raise ValueError(f"Missing environment variable: {api_key_env}")
    return key


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the OpenAI Chat Completions API (blocking) and return a ProviderResponse."""
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling OpenAI API (blocking) model=%s", model)
    try:
        response = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 8192,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"OpenAI API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"OpenAI API HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    payload = response.json()
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    logger.debug("OpenAI response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="openai", model=model)


def _token_stream(response: requests.Response, model: str) -> Iterator[str]:
    """Parse SSE line-by-line and yield token strings."""
    assembled: list[str] = []
    try:
        for raw_line in response.iter_lines(chunk_size=_STREAM_CHUNK_SIZE):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data: "):
                continue
            payload_str = line[6:].strip()
            if payload_str == "[DONE]":
                break
            try:
                chunk = json.loads(payload_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token = delta.get("content", "")
                if token:
                    assembled.append(token)
                    yield token
            except (json.JSONDecodeError, IndexError, KeyError):
                continue
    finally:
        logger.debug(
            "OpenAI stream finished (%d tokens assembled)", len(assembled)
        )


def generate_stream(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the OpenAI Chat Completions API in streaming mode.

    Returns a ProviderResponse whose stream_iter yields token strings.
    content is set to empty string initially — callers should consume stream_iter
    and accumulate tokens themselves.

    Falls back to blocking generate() if streaming fails with a non-auth error.
    """
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling OpenAI API (streaming) model=%s", model)
    try:
        response = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 8192,
                "stream": True,
            },
            stream=True,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"OpenAI streaming API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"OpenAI streaming HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    return ProviderResponse(
        content="",  # populated by consuming stream_iter
        provider="openai",
        model=model,
        stream_iter=_token_stream(response, model),
    )

