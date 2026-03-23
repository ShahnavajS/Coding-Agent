from __future__ import annotations

import logging
import os

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_API_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT_SECONDS = 60


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the OpenAI Chat Completions API and return a ProviderResponse."""
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Missing environment variable: {api_key_env}")

    logger.debug("Calling OpenAI API with model=%s", model)
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
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(f"OpenAI API timed out after {_TIMEOUT_SECONDS}s")
    except requests.HTTPError as exc:
        raise RuntimeError(f"OpenAI API HTTP error: {exc.response.status_code} {exc.response.text[:200]}")

    payload = response.json()
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    logger.debug("OpenAI response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="openai", model=model)
