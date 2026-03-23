from __future__ import annotations

import logging

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60


def generate(prompt: str, model: str, base_url: str) -> ProviderResponse:
    """Call a locally running Ollama instance and return a ProviderResponse."""
    if not base_url:
        raise ValueError("Ollama base_url is not configured")

    url = f"{base_url.rstrip('/')}/generate"
    logger.debug("Calling Ollama at %s with model=%s", url, model)
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
        raise RuntimeError(f"Ollama HTTP error: {exc.response.status_code} {exc.response.text[:200]}")

    payload = response.json()
    content = payload.get("response", "")
    logger.debug("Ollama response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="ollama", model=model)
