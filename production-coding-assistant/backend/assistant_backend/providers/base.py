from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    model_path: str = ""
    enabled: bool = False


@dataclass
class ProviderResponse:
    """Normalised response returned by every provider."""
    content: str
    provider: str
    model: str


class ProviderUnavailableError(RuntimeError):
    """Raised when no provider is able to fulfil the request."""
    pass
