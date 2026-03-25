from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_DIR = PROJECT_ROOT
APP_DIR = PROJECT_ROOT / ".assistant"
SETTINGS_PATH = APP_DIR / "settings.json"


@dataclass
class ProviderConfig:
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    model_path: str = ""
    enabled: bool = False


@dataclass
class AppSettings:
    workspace_path: str = str((PROJECT_ROOT / "workspace").resolve())
    backend_host: str = "0.0.0.0"
    backend_port: int = 5000
    cors_origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    default_provider: str = "ollama"
    shell_timeout_seconds: int = 30
    providers: dict[str, ProviderConfig] = field(
        default_factory=lambda: {
            "openai": ProviderConfig(
                model="gpt-4o",
                api_key_env="OPENAI_API_KEY",
                enabled=bool(os.getenv("OPENAI_API_KEY")),
            ),
            "anthropic": ProviderConfig(
                model="claude-sonnet-4-20250514",
                api_key_env="ANTHROPIC_API_KEY",
                enabled=bool(os.getenv("ANTHROPIC_API_KEY")),
            ),
            "groq": ProviderConfig(
                model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                api_key_env="GROQ_API_KEY",
                enabled=bool(os.getenv("GROQ_API_KEY")),
            ),
            "ollama": ProviderConfig(
                model="qwen3-coder",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api"),
                enabled=True,
            ),
            "local_path": ProviderConfig(
                model="local-model",
                model_path=os.getenv("LOCAL_MODEL_PATH", ""),
                enabled=bool(os.getenv("LOCAL_MODEL_PATH")),
            ),
        }
    )

    def to_public_dict(self) -> dict[str, Any]:
        providers = {}
        for name, cfg in self.providers.items():
            configured, available, reason = get_provider_status(name, cfg)
            providers[name] = {
                "model": cfg.model,
                "baseUrl": cfg.base_url,
                "apiKeyEnv": cfg.api_key_env,
                "modelPath": cfg.model_path,
                "enabled": cfg.enabled,
                "configured": configured,
                "available": available,
                "reason": reason,
            }
        return {
            "workspacePath": self.workspace_path,
            "backendHost": self.backend_host,
            "backendPort": self.backend_port,
            "corsOrigins": self.cors_origins,
            "defaultProvider": self.default_provider,
            "shellTimeoutSeconds": self.shell_timeout_seconds,
            "providers": providers,
        }


def _provider_from_mapping(data: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        model=str(data.get("model", "")),
        base_url=str(data.get("baseUrl", data.get("base_url", ""))),
        api_key_env=str(data.get("apiKeyEnv", data.get("api_key_env", ""))),
        model_path=str(data.get("modelPath", data.get("model_path", ""))),
        enabled=bool(data.get("enabled", False)),
    )


def _probe_ollama(base_url: str) -> tuple[bool, str]:
    if not base_url:
        return False, "Missing Ollama base URL"
    try:
        response = requests.get(f"{base_url.rstrip('/')}/tags", timeout=1)
        response.raise_for_status()
        return True, "Ollama reachable"
    except Exception as exc:
        return False, f"Ollama unavailable: {exc}"


def get_provider_status(name: str, cfg: ProviderConfig) -> tuple[bool, bool, str]:
    if name in {"openai", "anthropic", "groq"}:
        configured = bool(cfg.api_key_env and os.getenv(cfg.api_key_env))
        reason = "API key loaded" if configured else f"Missing {cfg.api_key_env}"
        return configured, configured, reason

    if name == "ollama":
        configured = bool(cfg.base_url)
        if not configured:
            return False, False, "Missing Ollama base URL"
        available, reason = _probe_ollama(cfg.base_url)
        return configured, available, reason

    if name == "local_path":
        configured = bool(cfg.model_path)
        available = configured and Path(cfg.model_path).exists()
        if not configured:
            return False, False, "Missing local model path"
        if not available:
            return True, False, f"Model path not found: {cfg.model_path}"
        return True, True, "Local model path exists"

    configured = bool(cfg.base_url or cfg.api_key_env or cfg.model_path)
    return configured, configured, "Provider configured"


def load_app_settings() -> AppSettings:
    """Load settings from .env and the JSON settings file.

    Note: call get_cached_settings() instead of this function in hot paths
    to avoid disk reads on every request.
    """
    load_dotenv(ROOT_DIR / ".env")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(
        workspace_path=os.getenv(
            "WORKSPACE_PATH", str((PROJECT_ROOT / "workspace").resolve())
        ),
        backend_host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        backend_port=int(os.getenv("BACKEND_PORT", "5000")),
        cors_origins=[
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
            ).split(",")
            if origin.strip()
        ],
        default_provider=os.getenv("DEFAULT_PROVIDER", "ollama"),
        shell_timeout_seconds=int(os.getenv("SHELL_TIMEOUT_SECONDS", "30")),
    )

    if SETTINGS_PATH.exists():
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if "workspacePath" in raw:
            settings.workspace_path = str(raw["workspacePath"])
        settings.default_provider = str(
            raw.get("defaultProvider", settings.default_provider)
        )
        settings.shell_timeout_seconds = int(
            raw.get("shellTimeoutSeconds", settings.shell_timeout_seconds)
        )
        provider_data = raw.get("providers", {})
        merged_providers: dict[str, ProviderConfig] = dict(settings.providers)
        for provider_name, provider_config in provider_data.items():
            merged_providers[provider_name] = _provider_from_mapping(provider_config)
        settings.providers = merged_providers

    logger.debug("App settings loaded (provider: %s)", settings.default_provider)
    return settings


@lru_cache(maxsize=1)
def get_cached_settings() -> AppSettings:
    """Return a cached AppSettings instance.

    Use this in hot paths (tool calls, request handlers) to avoid hitting
    disk on every request. Call _invalidate_settings_cache() after any write.
    """
    return load_app_settings()


def _invalidate_settings_cache() -> None:
    """Clear the settings cache so the next call to get_cached_settings() reloads from disk."""
    get_cached_settings.cache_clear()
    logger.debug("Settings cache cleared")


def save_app_settings(settings: AppSettings) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings.to_public_dict(), indent=2), encoding="utf-8"
    )
    logger.info("Settings saved to %s", SETTINGS_PATH)


def update_app_settings(payload: dict[str, Any]) -> AppSettings:
    settings = load_app_settings()
    if "workspacePath" in payload:
        settings.workspace_path = str(payload["workspacePath"])
    if "defaultProvider" in payload:
        settings.default_provider = str(payload["defaultProvider"])
    if "shellTimeoutSeconds" in payload:
        settings.shell_timeout_seconds = int(payload["shellTimeoutSeconds"])
    provider_payload = payload.get("providers", {})
    for provider_name, provider_config in provider_payload.items():
        settings.providers[provider_name] = _provider_from_mapping(provider_config)
    save_app_settings(settings)
    # Invalidate cache so the next call picks up the new settings.
    _invalidate_settings_cache()
    return settings
