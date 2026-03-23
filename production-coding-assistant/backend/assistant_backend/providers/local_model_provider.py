from __future__ import annotations

from assistant_backend.providers.base import ProviderResponse


def generate(prompt: str, model: str, model_path: str) -> ProviderResponse:
    content = (
        "Local-path provider is registered, but this build does not bundle a local runtime "
        f"adapter yet. Model '{model}' at '{model_path}' is available as configuration.\n\n"
        f"Prompt preview:\n{prompt[:400]}"
    )
    return ProviderResponse(content=content, provider="local_path", model=model)

