"""OpenAI LLM provider — external API, key sourced from env var only."""
from __future__ import annotations

import os

import requests

from hydramem.core.logging import get_logger

logger = get_logger(__name__)

_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
    """Calls the OpenAI Chat Completions API."""

    name = "openai"

    def __init__(
        self,
        api_key_env: str = "HYDRAMEM_OPENAI_KEY",
        model: str = "gpt-4o-mini",
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model

    def _api_key(self) -> str:
        key = os.getenv(self._api_key_env) or os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                f"OpenAI API key not found. Set the {self._api_key_env!r} env var."
            )
        return key

    def complete(self, prompt: str, model: str | None = None) -> str:
        try:
            resp = requests.post(
                _CHAT_ENDPOINT,
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
            logger.warning("OpenAIProvider.complete failed: %s", exc)
            return ""
