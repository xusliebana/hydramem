"""Anthropic Claude LLM provider — external API, key sourced from env var only."""
from __future__ import annotations

import os

import requests

from hydramem.core.logging import get_logger

logger = get_logger(__name__)

_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicProvider:
    """Calls the Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        api_key_env: str = "ANTHROPIC_API_KEY",
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model

    def _api_key(self) -> str:
        key = (
            os.getenv(self._api_key_env)
            or os.getenv("HYDRAMEM_ANTHROPIC_KEY")
            or os.getenv("ANTHROPIC_API_KEY", "")
        )
        if not key:
            raise RuntimeError(
                f"Anthropic API key not found. Set the {self._api_key_env!r} env var."
            )
        return key

    def complete(self, prompt: str, model: str | None = None) -> str:
        try:
            resp = requests.post(
                _MESSAGES_ENDPOINT,
                headers={
                    "x-api-key": self._api_key(),
                    "anthropic-version": _API_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or self._model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("content", [{}])[0].get("text", "")
        except Exception as exc:
            logger.warning("AnthropicProvider.complete failed: %s", exc)
            return ""
