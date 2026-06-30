"""RelationInferrer — Phase 1 of the Night Gardener cycle.

Single responsibility: given session text + known entities, propose candidate
relations using an LLM.  Does not verify or persist anything.

Honesty contract: when no real session text is available, **no relations are
proposed**. Earlier versions emitted random ``co_mentioned`` placeholders
between adjacent entities, which polluted the graph and inflated
``relations_proposed`` / ``relations_accepted`` in ``garden-status``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from hydramem.core.logging import get_logger
from hydramem.core.types import Relation
from hydramem.llm.base import LLMProvider

logger = get_logger(__name__)

_PROMPT = """\
You are a knowledge-graph curator. Analyse the following Q&A session and \
propose up to 5 NEW relations between entities that are NOT yet explicitly stated.

Session:
{session_text}

Known entities: {entity_names}

For each proposed relation output one line:
  FROM_ENTITY –[RELATION_TYPE]→ TO_ENTITY  |  CONFIDENCE: <0.0-1.0>

Only propose relations supported by evidence in the session.
"""

_PATTERN = re.compile(
    r"(.+?)\s*[-–—]+\[(.+?)\][-–—]+[>→]\s*(.+?)\s*\|?\s*CONFIDENCE:\s*([0-9.]+)",
    re.IGNORECASE,
)


class RelationInferrer:
    """Uses an LLM to infer new graph edges from stored Q&A sessions."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def infer(
        self,
        sessions: list[dict],
        entity_names: list[str],
        project: str = "default",
    ) -> list[Relation]:
        """Return a list of candidate Relation objects inferred from *sessions*.

        Returns an empty list if no usable session evidence is available. We
        do **not** invent ``co_mentioned`` placeholders — honest emptiness
        beats fake metrics.
        """
        candidates: list[Relation] = []
        for session in sessions:
            text = session.get("text", "")
            if text:
                candidates.extend(
                    self._infer_from_session(
                        text,
                        entity_names,
                        project,
                        session_id=session.get("session_id", ""),
                    )
                )
        return candidates

    def _infer_from_session(
        self,
        session_text: str,
        entity_names: list[str],
        project: str,
        session_id: str = "",
    ) -> list[Relation]:
        prompt = _PROMPT.format(
            session_text=session_text[:2000],
            entity_names=", ".join(entity_names[:30]),
        )
        answer = self._provider.complete(prompt)

        if not answer:
            logger.debug("RelationInferrer: LLM returned empty for one session")
            return []

        relations: list[Relation] = []
        for line in answer.splitlines():
            m = _PATTERN.search(line)
            if m:
                try:
                    conf = float(m.group(4))
                except ValueError:
                    conf = 0.5
                relations.append(
                    Relation(
                        from_entity=m.group(1).strip(),
                        to_entity=m.group(3).strip(),
                        relation_type=m.group(2).strip().lower(),
                        confidence=round(conf, 4),
                        project=project,
                        session_id=session_id,
                        origin_tool="night_gardener",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                )
        return relations
