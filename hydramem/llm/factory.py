"""LLM factory — maps provider names to concrete implementations (OCP).

Adding a new provider only requires:
  1. Create a new module in hydramem/llm/
  2. Register it in _REGISTRY below
  3. No changes to callers
"""
from __future__ import annotations

from hydramem.core.config import Config, load_config
from hydramem.core.logging import get_logger
from hydramem.llm.anthropic import AnthropicProvider
from hydramem.llm.base import LLMProvider
from hydramem.llm.mistral import MistralProvider
from hydramem.llm.ollama import OllamaProvider
from hydramem.llm.openai import OpenAIProvider

logger = get_logger(__name__)

# Registry: provider name → factory callable
# To add a new backend, add an entry here — no other file needs to change.
_REGISTRY: dict[str, type] = {
    "ollama": OllamaProvider,
    "local": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "mistral": MistralProvider,
}


def create_provider(config: Config | None = None) -> LLMProvider:
    """Instantiate the correct LLMProvider from the resolved Config."""
    cfg = config or load_config()
    provider_name = cfg.llm_provider.lower()
    cls = _REGISTRY.get(provider_name, OllamaProvider)

    if cls is OllamaProvider:
        return OllamaProvider(host=cfg.ollama_host, model=cfg.ollama_model)
    if cls is OpenAIProvider:
        return OpenAIProvider(api_key_env=cfg.external_api_key_env, model=cfg.external_model)
    if cls is AnthropicProvider:
        return AnthropicProvider(api_key_env=cfg.external_api_key_env, model=cfg.external_model)
    if cls is MistralProvider:
        return MistralProvider(api_key_env=cfg.external_api_key_env, model=cfg.external_model)

    logger.warning("Unknown provider %r, falling back to Ollama", provider_name)
    return OllamaProvider(host=cfg.ollama_host, model=cfg.ollama_model)


# Module-level singleton — lazy-initialised on first call
_default_provider: LLMProvider | None = None


def _get_default() -> LLMProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = create_provider()
    return _default_provider


def call_llm(
    prompt: str,
    model: str | None = None,
    provider: LLMProvider | None = None,
) -> str:
    """Convenience wrapper: call the default provider (or an explicit one).

    Never raises — returns empty string on any failure.
    """
    p = provider or _get_default()
    return p.complete(prompt, model=model)
