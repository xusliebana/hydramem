"""Mistral AI LLM provider — OpenAI-compatible API with EU data sovereignty.

Mistral's La Plateforme uses the same chat completions format as OpenAI,
so this provider reuses the same request shape with a different endpoint
and auth header.

Key advantages for HydraMem:
- EU data residency by default (French company, GDPR-native)
- No training on API data — contractual
- Open-weight models available for local fallback via Ollama
"""
from __future__ import annotations

import os

import requests

from hydramem.core.logging import get_logger

logger = get_logger(__name__)

_CHAT_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"


class MistralProvider:
    """Calls the Mistral AI Chat Completions API."""

    name = "mistral"

    def __init__(
        self,
        api_key_env: str = "MISTRAL_API_KEY",
        model: str = "mistral-large-latest",
        endpoint: str | None = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._endpoint = endpoint or _CHAT_ENDPOINT

    def _api_key(self) -> str:
        key = (
            os.getenv(self._api_key_env)
            or os.getenv("HYDRAMEM_MISTRAL_KEY")
            or os.getenv("MISTRAL_API_KEY", "")
        )
        if not key:
            raise RuntimeError(
                f"Mistral API key not found. Set the {self._api_key_env!r} env var."
            )
        return key

    def complete(self, prompt: str, model: str | None = None) -> str:
        try:
            resp = requests.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("MistralProvider.complete failed: %s", exc)
            return ""
