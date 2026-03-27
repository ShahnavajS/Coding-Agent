from __future__ import annotations

import logging
import os
import time

import requests

from assistant_backend.providers.base import ProviderResponse

logger = logging.getLogger(__name__)

_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_SECONDS = 60
_MAX_RATE_LIMIT_RETRIES = 2


def _rate_limit_delay(response: requests.Response, attempt: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(1, min(int(float(retry_after)), 30))
        except ValueError:
            logger.debug("Could not parse Retry-After header: %s", retry_after)
    return min(10 * attempt, 30)


def generate(prompt: str, model: str, api_key_env: str) -> ProviderResponse:
    """Call the Groq Chat Completions API and return a ProviderResponse."""
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError(f"Missing environment variable: {api_key_env}")

    logger.debug("Calling Groq API with model=%s", model)
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
                },
                timeout=_TIMEOUT_SECONDS,
            )
            if response.status_code == 429 and attempt <= _MAX_RATE_LIMIT_RETRIES:
                delay = _rate_limit_delay(response, attempt)
                logger.warning(
                    "Groq rate limit reached for model=%s. Retrying in %ss (attempt %s/%s)",
                    model,
                    delay,
                    attempt,
                    _MAX_RATE_LIMIT_RETRIES + 1,
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

    payload = response.json()
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    logger.debug("Groq response received (%d chars)", len(content))
    return ProviderResponse(content=content, provider="groq", model=model)
