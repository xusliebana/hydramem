"""Ollama LLM provider — local, free, privacy-preserving."""
from __future__ import annotations

from hydramem.core.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider:
    """Calls a locally running Ollama daemon."""

    name = "ollama"

    def __init__(self, host: str = "http://localhost:11434", model: str = "gemma4:e4b") -> None:
        self._host = host
        self._model = model

    def complete(self, prompt: str, model: str | None = None) -> str:
        try:
            import ollama as _ollama  # type: ignore

            response = _ollama.chat(
                model=model or self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            if hasattr(response, "message"):
                return response.message.content or ""
            return response.get("message", {}).get("content", "")  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("OllamaProvider.complete failed: %s", exc)
            return ""
