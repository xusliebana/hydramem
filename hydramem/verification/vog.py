"""VoG (Verification of Groundedness) — LLM step-by-step relation checker."""

from __future__ import annotations

import re

from hydramem.core.logging import get_logger
from hydramem.core.types import Relation
from hydramem.llm.base import LLMProvider
from hydramem.verification.base import VerificationResult

logger = get_logger(__name__)

_PROMPT = """\
You are a knowledge-graph auditor. Given two text fragments and a proposed \
relation between them, decide if the relation is GROUNDED in the texts.

Proposed relation: "{from_entity}" –[{relation_type}]→ "{to_entity}"

Fragment A (source):
\"\"\"
{source_text}
\"\"\"

Fragment B (target):
\"\"\"
{target_text}
\"\"\"

Answer with exactly one of:
  GROUNDED – the relation is clearly supported by both fragments.
  PARTIAL   – the relation is partially supported or ambiguous.
  REJECTED  – the relation is not supported or contradicted.

Then on a new line write CONFIDENCE: <float between 0.0 and 1.0>.
"""


class VoGVerifier:
    """LLM-based Verification of Groundedness.

    Receives a candidate relation + source texts and asks an LLM to confirm
    that the relation is genuinely grounded in the provided evidence.

    The LLMProvider is injected (DIP) — any provider can be used.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def verify(self, relation: Relation) -> VerificationResult:
        """Verify *relation* using the injected LLM provider.

        Honest contract: a relation without source/target evidence cannot be
        verified by VoG and is therefore REJECTED. We previously returned a
        random optimistic score here, which silently inflated dashboard
        metrics; that behaviour was a bug and has been removed.
        """
        if not relation.source_text or not relation.target_text:
            return VerificationResult(
                accepted=False,
                score=0.0,
                level="vog_no_evidence",
                vog_verdict="UNGROUNDED",
            )

        prompt = _PROMPT.format(
            from_entity=relation.from_entity,
            to_entity=relation.to_entity,
            relation_type=relation.relation_type,
            source_text=relation.source_text[:800],
            target_text=relation.target_text[:800],
        )
        answer = self._provider.complete(prompt)

        if not answer:
            # LLM unavailable: be conservative — do not pretend the relation
            # is verified. Counted as a borderline rejection (score 0.0) so
            # operators can detect provider outages from the metrics.
            logger.warning("VoGVerifier: LLM returned empty — rejecting candidate")
            return VerificationResult(
                accepted=False,
                score=0.0,
                level="vog_unavailable",
                vog_verdict="REJECTED",
            )

        upper = answer.upper()
        if "GROUNDED" in upper:
            verdict = "GROUNDED"
            accepted = True
        elif "PARTIAL" in upper:
            verdict = "PARTIAL"
            accepted = True
        else:
            verdict = "REJECTED"
            accepted = False

        confidence = 0.6
        m = re.search(r"CONFIDENCE:\s*([0-9.]+)", answer, re.IGNORECASE)
        if m:
            try:
                confidence = float(m.group(1))
            except ValueError:
                pass

        if verdict == "PARTIAL":
            confidence *= 0.6

        return VerificationResult(
            accepted=accepted,
            score=round(confidence, 4),
            level="vog",
            vog_verdict=verdict,
        )
