from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterator

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_SECONDS = 90
_MAX_RATE_LIMIT_RETRIES = 2
_STREAM_CHUNK_SIZE = 1024


def _get_api_key(api_key_env: str) -> str:
    key = os.getenv(api_key_env, "").strip()
    if not key:
        raise ValueError(f"Missing environment variable: {api_key_env}")
    return key


def _rate_limit_delay(response: requests.Response, attempt: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1, min(int(float(retry_after)), 30))
        except ValueError:
            logger.debug("Could not parse Retry-After header: %s", retry_after)
    return min(10 * attempt, 30)


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Groq Chat Completions API (blocking) and return a ProviderResponse."""
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling Groq API (blocking) model=%s", model)
    response: requests.Response | None = None
    for attempt in range(1, _MAX_RATE_LIMIT_RETRIES + 2):
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
            if response.status_code == 429 and attempt <= _MAX_RATE_LIMIT_RETRIES:
                delay = _rate_limit_delay(response, attempt)
                logger.warning(
                    "Groq rate limit (blocking) model=%s. Retrying in %ss (%d/%d)",
                    model, delay, attempt, _MAX_RATE_LIMIT_RETRIES + 1,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            break
        except requests.Timeout:
            raise RuntimeError(f"Groq API timed out after {_TIMEOUT_SECONDS}s")
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Groq API HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
            )

    assert response is not None
    payload = response.json()
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    logger.debug("Groq response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="groq", model=model)


def _groq_stream(response: requests.Response) -> Iterator[str]:
    """Parse Groq's OpenAI-compatible SSE events and yield token strings."""
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
        logger.debug("Groq stream finished (%d tokens assembled)", len(assembled))


def generate_stream(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Groq Chat Completions API in streaming mode.

    Returns a ProviderResponse whose stream_iter yields token strings.
    Retries once on 429 rate-limit before raising.
    """
    api_key = _get_api_key(api_key_env)
    logger.debug("Calling Groq API (streaming) model=%s", model)

    for attempt in range(1, _MAX_RATE_LIMIT_RETRIES + 2):
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
            if response.status_code == 429 and attempt <= _MAX_RATE_LIMIT_RETRIES:
                delay = _rate_limit_delay(response, attempt)
                logger.warning(
                    "Groq rate limit (streaming) model=%s. Retrying in %ss", model, delay
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            break
        except requests.Timeout:
            raise RuntimeError(f"Groq streaming API timed out after {_TIMEOUT_SECONDS}s")
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Groq streaming HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
            )

    return ProviderResponse(
        content="",
        provider="groq",
        model=model,
        stream_iter=_groq_stream(response),
    )

