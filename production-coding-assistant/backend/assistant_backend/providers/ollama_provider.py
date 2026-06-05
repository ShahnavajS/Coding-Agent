from __future__ import annotations

import json
import logging
from typing import Iterator

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120


def generate(prompt: str, model: str, base_url: str) -> ProviderResponse:
    """Call a locally running Ollama instance (blocking) and return a ProviderResponse."""
    if not base_url:
        raise ValueError("Ollama base_url is not configured")

    url = f"{base_url.rstrip('/')}/generate"
    logger.debug("Calling Ollama (blocking) at %s model=%s", url, model)
    try:
        response = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"Ollama timed out after {_TIMEOUT_SECONDS}s")
    except requests.ConnectionError:
        raise RuntimeError(f"Could not connect to Ollama at {base_url}. Is it running?")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Ollama HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    payload = response.json()
    content = payload.get("response", "")
    logger.debug("Ollama response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="ollama", model=model)


def _ollama_stream(response: requests.Response) -> Iterator[str]:
    """Parse Ollama NDJSON stream and yield token strings."""
    assembled: list[str] = []
    try:
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = obj.get("response", "")
            if token:
                assembled.append(token)
                yield token
            if obj.get("done", False):
                break
    finally:
        logger.debug(
            "Ollama stream finished (%d chars assembled)", sum(len(t) for t in assembled)
        )


def generate_stream(prompt: str, model: str, base_url: str) -> ProviderResponse:
    """Call a locally running Ollama instance in streaming mode.

    Returns a ProviderResponse whose stream_iter yields token strings using
    Ollama's native NDJSON streaming protocol.
    """
    if not base_url:
        raise ValueError("Ollama base_url is not configured")

    url = f"{base_url.rstrip('/')}/generate"
    logger.debug("Calling Ollama (streaming) at %s model=%s", url, model)
    try:
        response = requests.post(
            url,
            json={"model": model, "prompt": prompt, "stream": True},
            stream=True,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"Ollama streaming timed out after {_TIMEOUT_SECONDS}s")
    except requests.ConnectionError:
        raise RuntimeError(f"Could not connect to Ollama at {base_url}. Is it running?")
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Ollama streaming HTTP error: {exc.response.status_code} {exc.response.text[:200]}"
        )

    return ProviderResponse(
        content="",
        provider="ollama",
        model=model,
        stream_iter=_ollama_stream(response),
    )

