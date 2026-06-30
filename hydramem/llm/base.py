"""LLMProvider Protocol — Dependency Inversion boundary.

All concrete providers implement this interface.  Callers depend only on this
contract, never on a specific implementation (DIP).  New providers can be
added without touching existing code (OCP).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface every LLM backend must satisfy."""

    #: Human-readable name used in logs and telemetry (e.g. "ollama", "openai").
    name: str

    def complete(self, prompt: str, model: str | None = None) -> str:
        """Send *prompt* to the LLM and return the text response.

        Must return an empty string — not raise — when the backend is
        unreachable or the response is malformed.
        """
        ...
