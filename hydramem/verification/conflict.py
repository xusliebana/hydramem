"""ConflictChecker — detects contradictions between two text passages."""
from __future__ import annotations

from hydramem.core.logging import get_logger
from hydramem.llm.base import LLMProvider

logger = get_logger(__name__)

_PROMPT = """\
Do these two passages contradict each other?

Entity A: {entity_a}
Passage A:
\"\"\"
{text_a}
\"\"\"

Entity B: {entity_b}
Passage B:
\"\"\"
{text_b}
\"\"\"

Answer with CONFLICT or NO CONFLICT, then on a new line explain why.
On a third line write CONFIDENCE: <0.0–1.0>.
"""


class ConflictChecker:
    """Uses an LLM to detect contradictions between two text passages."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def check(
        self,
        entity_a: str,
        entity_b: str,
        text_a: str,
        text_b: str,
    ) -> dict:
        """Return a dict with ``conflict`` (bool), ``confidence``, and ``explanation``."""
        prompt = _PROMPT.format(
            entity_a=entity_a,
            entity_b=entity_b,
            text_a=text_a[:600],
            text_b=text_b[:600],
        )
        answer = self._provider.complete(prompt)
        if not answer:
            return {"conflict": False, "confidence": 0.5, "explanation": "LLM unavailable"}

        upper = answer.upper()
        conflict = "CONFLICT" in upper and "NO CONFLICT" not in upper

        confidence = 0.7
        import re
        m = re.search(r"CONFIDENCE:\s*([0-9.]+)", answer, re.IGNORECASE)
        if m:
            try:
                confidence = float(m.group(1))
            except ValueError:
                pass

        lines = answer.strip().splitlines()
        explanation = "\n".join(lines[1:]).strip() if len(lines) > 1 else answer

        return {"conflict": conflict, "confidence": confidence, "explanation": explanation}
