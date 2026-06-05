from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


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
    """Normalised response returned by every provider.

    For streaming responses, `content` contains the fully assembled text and
    `stream_iter` is an iterator that yields token strings as they arrive.
    `stream_iter` is None for non-streaming (blocking) responses.
    """
    content: str
    provider: str
    model: str
    # Optional token iterator for streaming responses.
    # Consumers must fully iterate this to receive all tokens.
    # stream_iter is set to None for standard blocking responses.
    stream_iter: Iterator[str] | None = field(default=None, compare=False, repr=False)


class ProviderUnavailableError(RuntimeError):
    """Raised when no provider is able to fulfil the request."""
    pass


class StreamNotSupportedError(RuntimeError):
    """Raised when a provider does not support streaming for the current config."""
    pass
