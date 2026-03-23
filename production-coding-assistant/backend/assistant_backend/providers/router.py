from __future__ import annotations

import logging

from assistant_backend.config import get_cached_settings
from assistant_backend.providers import (
    anthropic_provider,
    groq_provider,
    local_model_provider,
    ollama_provider,
    openai_provider,
)
from assistant_backend.providers.base import ProviderConfig, ProviderResponse, ProviderUnavailableError

logger = logging.getLogger(__name__)


def _dispatch(prompt: str, provider_name: str, config: ProviderConfig) -> ProviderResponse:
    """Call the correct provider module based on provider_name."""
    if provider_name == "openai":
        return openai_provider.generate(prompt, config.model, config.api_key_env)
    if provider_name == "anthropic":
        return anthropic_provider.generate(prompt, config.model, config.api_key_env)
    if provider_name == "groq":
        return groq_provider.generate(prompt, config.model, config.api_key_env)
    if provider_name == "ollama":
        return ollama_provider.generate(prompt, config.model, config.base_url)
    if provider_name == "local_path":
        return local_model_provider.generate(prompt, config.model, config.model_path)
    raise ValueError(f"Provider '{provider_name}' is not supported")


def _candidate_provider_names(selected: str, available_names: list[str]) -> list[str]:
    """Return providers to try, in priority order, starting with the selected one."""
    ordered = [selected, "groq", "openai", "anthropic", "ollama", "local_path"]
    result: list[str] = []
    for name in ordered:
        if name in available_names and name not in result:
            result.append(name)
    return result


def generate(prompt: str, provider_name: str | None = None) -> ProviderResponse:
    """Generate a response using the best available provider.

    Tries the selected provider first, then falls back through the priority
    list until one succeeds. Raises ProviderUnavailableError if all fail.
    """
    settings = get_cached_settings()
    selected = provider_name or settings.default_provider

    if selected not in settings.providers:
        raise ValueError(f"Unknown provider '{selected}'")

    errors: list[str] = []
    candidates = _candidate_provider_names(selected, list(settings.providers.keys()))
    logger.debug("Provider candidates: %s", candidates)

    for candidate in candidates:
        config = settings.providers.get(candidate)
        if config is None or not config.enabled:
            errors.append(f"{candidate}: disabled")
            logger.debug("Skipping provider %s (disabled)", candidate)
            continue
        try:
            logger.info("Trying provider: %s", candidate)
            response = _dispatch(prompt, candidate, config)
            logger.info("Provider %s responded successfully", candidate)
            return response
        except Exception as exc:
            logger.warning("Provider %s failed: %s", candidate, exc)
            errors.append(f"{candidate}: {exc}")

    raise ProviderUnavailableError("All providers failed. " + " | ".join(errors))
