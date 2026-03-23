from __future__ import annotations

import logging
import os

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT_SECONDS = 60


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Anthropic Messages API and return a ProviderResponse."""
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Missing environment variable: {api_key_env}")

    logger.debug("Calling Anthropic API with model=%s", model)
    try:
        response = requests.post(
            _API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"Anthropic API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(f"Anthropic API HTTP error: {exc.response.status_code} {exc.response.text[:200]}")

    payload = response.json()
    blocks = payload.get("content", [])
    content = "\n".join(
        block.get("text", "") for block in blocks if block.get("type") == "text"
    )
    logger.debug("Anthropic response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="anthropic", model=model)
