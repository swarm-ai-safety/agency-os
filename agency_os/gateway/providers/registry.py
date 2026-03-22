"""Provider registry — lazily initializes LLM providers."""

from __future__ import annotations

import logging
import os

from agency_os.gateway.provider_key_store import GatewayProviderKeyStore
from agency_os.gateway.providers.base import LLMProvider

logger = logging.getLogger(__name__)

# OpenAI-compatible provider configs: (default_base_url, api_key_env, require_api_key)
_OPENAI_COMPAT_PROVIDERS: dict[str, tuple[str, str, bool]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", True),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", True),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", True),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", True),
    "ollama": ("http://localhost:11434/v1", "OLLAMA_API_KEY", False),
    "custom_openai": ("http://localhost:8000/v1", "CUSTOM_OPENAI_API_KEY", False),
}


class ProviderRegistry:
    """Maps provider names to LLMProvider instances.

    Providers are initialized lazily on first access.
    """

    def __init__(self, key_store: GatewayProviderKeyStore | None = None) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._key_store = key_store

    def get(self, name: str, base_url: str | None = None) -> LLMProvider | None:
        """Get a provider by name, initializing it if needed.

        For OpenAI-compatible providers with a custom base_url, a separate
        instance is cached per (name, base_url) pair.
        """
        cache_key = f"{name}:{base_url}" if base_url else name
        if cache_key in self._providers:
            return self._providers[cache_key]
        return self._try_init(name, base_url, cache_key)

    def _try_init(
        self, name: str, base_url: str | None, cache_key: str
    ) -> LLMProvider | None:
        try:
            provider: LLMProvider
            if name in _OPENAI_COMPAT_PROVIDERS:
                from agency_os.gateway.providers.openai_provider import (
                    OpenAIProvider,
                )

                default_url, api_key_env, require_key = _OPENAI_COMPAT_PROVIDERS[name]
                api_key = self._resolve_api_key(name, api_key_env)
                provider = OpenAIProvider(
                    api_key=api_key,
                    base_url=base_url or default_url,
                    api_key_env=api_key_env,
                    require_api_key=require_key,
                )
            elif name == "anthropic":
                from agency_os.gateway.providers.anthropic_provider import (
                    AnthropicProvider,
                )

                provider = AnthropicProvider(
                    api_key=self._resolve_api_key("anthropic", "ANTHROPIC_API_KEY")
                )
            else:
                logger.warning("Unknown provider: %s", name)
                return None
        except RuntimeError:
            logger.warning("Provider %s not available (API key not set)", name)
            return None

        self._providers[cache_key] = provider
        return provider

    def _resolve_api_key(self, provider: str, env_var: str) -> str:
        if self._key_store is not None:
            stored = self._key_store.get_key(provider)
            if stored:
                return stored
        return os.environ.get(env_var, "")

    def create_with_key(
        self, name: str, api_key: str, base_url: str | None = None
    ) -> LLMProvider | None:
        """Create a one-off provider instance with an explicit API key (not cached)."""
        try:
            if name in _OPENAI_COMPAT_PROVIDERS:
                from agency_os.gateway.providers.openai_provider import (
                    OpenAIProvider,
                )

                default_url, _, require_key = _OPENAI_COMPAT_PROVIDERS[name]
                return OpenAIProvider(
                    api_key=api_key,
                    base_url=base_url or default_url,
                    require_api_key=require_key,
                )
            elif name == "anthropic":
                from agency_os.gateway.providers.anthropic_provider import (
                    AnthropicProvider,
                )

                return AnthropicProvider(api_key=api_key)
            else:
                logger.warning("Unknown provider for BYOK: %s", name)
                return None
        except RuntimeError:
            logger.warning("Failed to create BYOK provider %s", name, exc_info=True)
            return None

    def invalidate(self, provider: str | None = None) -> None:
        """Invalidate cached provider clients so new credentials take effect."""
        if provider is None:
            self._providers.clear()
            return
        provider_name = provider.strip().lower()
        if not provider_name:
            return
        for key in list(self._providers.keys()):
            if key == provider_name or key.startswith(f"{provider_name}:"):
                self._providers.pop(key, None)
