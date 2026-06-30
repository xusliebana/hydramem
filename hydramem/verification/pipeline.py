"""VerificationPipeline — composes SR-MKG + VoG into a two-level filter.

OCP: new stages can be inserted by modifying only this class.
DIP: depends on LLMProvider and Config abstractions, not concrete classes.
"""
from __future__ import annotations

from hydramem.core.config import Config, load_config
from hydramem.core.types import Chunk, Relation
from hydramem.llm.factory import create_provider
from hydramem.verification.base import VerificationResult
from hydramem.verification.srmkg import SRMKGScorer
from hydramem.verification.vog import VoGVerifier


class VerificationPipeline:
    """Two-level SR-MKG → VoG verification pipeline.

    Usage::

        pipeline = VerificationPipeline()
        result = pipeline.verify(relation)
    """

    def __init__(self, config: Config | None = None) -> None:
        cfg = config or load_config()
        self._cfg = cfg
        self._project = getattr(cfg, "project", "default")
        self._srmkg = SRMKGScorer(
            threshold_accept=cfg.srmkg_threshold_accept,
            threshold_reject=cfg.srmkg_threshold_reject,
            weight_base=cfg.srmkg_weight_base,
            weight_jaccard=cfg.srmkg_weight_jaccard,
            weight_type_boost=cfg.srmkg_weight_type_boost,
            penalty_isolated=cfg.srmkg_penalty_isolated,
            project=self._project,
        )
        # VoG LLM provider: respect vog_use_local_llm flag
        from hydramem.llm.ollama import OllamaProvider

        if cfg.vog_use_local_llm:
            vog_provider = OllamaProvider(host=cfg.ollama_host, model=cfg.ollama_model)
        else:
            vog_provider = create_provider(cfg)

        self._vog = VoGVerifier(vog_provider)
        self._max_vog = cfg.vog_max_candidates
        self._vog_calls = 0  # reset per pipeline run

    def verify(
        self,
        relation: Relation,
        common_neighbors: int = 0,
        degree_from: int = 1,
        degree_to: int = 1,
    ) -> VerificationResult:
        """Run SR-MKG; forward borderline cases to VoG (up to cap)."""
        result = self._srmkg.verify(
            relation,
            common_neighbors=common_neighbors,
            degree_from=degree_from,
            degree_to=degree_to,
        )
        if result.level != "srmkg_borderline":
            self._log_srmkg_decision(relation, result, source="srmkg")
            return result

        # Borderline: forward to VoG if cap not reached
        if self._vog_calls >= self._max_vog:
            # Cap reached — default accept with SR-MKG score
            capped = VerificationResult(
                accepted=True, score=result.score, level="srmkg_cap"
            )
            capped.breakdown = getattr(result, "breakdown", None)  # type: ignore[attr-defined]
            self._log_srmkg_decision(relation, capped, source="srmkg_cap")
            return capped

        self._vog_calls += 1
        vog_result = self._vog.verify(relation)
        # Carry the SR-MKG breakdown so callers / telemetry can train on it.
        vog_result.breakdown = getattr(result, "breakdown", None)  # type: ignore[attr-defined]
        self._log_srmkg_decision(
            relation, vog_result, source="vog", parent=result
        )
        return vog_result

    def _log_srmkg_decision(
        self,
        relation: Relation,
        result: VerificationResult,
        *,
        source: str,
        parent: VerificationResult | None = None,
    ) -> None:
        """Record (components → final_label) for later calibration."""
        if not getattr(self._cfg, "srmkg_log_decisions", True):
            return
        breakdown = getattr(result, "breakdown", None) or getattr(
            parent, "breakdown", None
        )
        if breakdown is None:
            return
        try:
            from hydramem.telemetry.storage import log_srmkg_decision

            log_srmkg_decision(
                project=getattr(relation, "project", self._project) or self._project,
                relation_type=getattr(relation, "relation_type", "") or "",
                base=breakdown.base,
                jaccard=breakdown.jaccard,
                type_boost=breakdown.type_boost,
                isolated=breakdown.isolated,
                score=breakdown.score,
                final_label=1 if result.accepted else 0,
                source=source,
            )
        except Exception:  # noqa: BLE001
            # Best-effort: never break verification on telemetry hiccups.
            pass

    def reset_vog_cap(self) -> None:
        """Reset the per-run VoG call counter."""
        self._vog_calls = 0

    def verify_chunks(
        self,
        chunks: list[Chunk],
        query: str = "",
    ) -> dict:
        """Apply a **vector-similarity prefilter + VoG** to a list of chunks.

        IMPORTANT — honesty notice: this method does NOT use SR-MKG (which is a
        topological filter over named relations). Chunks have no Jaccard /
        degree signal on their own, so the prefilter here is plain cosine
        similarity from the vector store, with VoG verifying borderline cases.

        Output keys:
          - ``rejected_vector``   : dropped by the cosine-similarity prefilter
          - ``rejected_vog``      : dropped by VoG
          - ``rejected_srmkg``    : DEPRECATED alias of ``rejected_vector``,
            kept for backward-compatibility with the v0.1.x telemetry schema.
        """
        accept_threshold = self._cfg.chunk_vector_threshold_accept
        reject_threshold = self._cfg.chunk_vector_threshold_reject

        filtered: list[Chunk] = []
        verified: list[Chunk] = []
        rejected_vector: list[Chunk] = []
        rejected_vog: list[Chunk] = []
        vog_scores: list[float] = []

        for chunk in chunks:
            sim = chunk.similarity

            if sim >= accept_threshold:
                filtered.append(chunk)
                verified.append(chunk)
                vog_scores.append(sim)
            elif sim < reject_threshold:
                rejected_vector.append(chunk)
            else:
                # Borderline: VoG verifies the (query, chunk) pair.
                rel = Relation(
                    from_entity=query[:50],
                    to_entity=chunk.source,
                    relation_type="answers",
                    confidence=sim,
                    source_text=query,
                    target_text=chunk.text,
                )
                vog_result = self._vog.verify(rel)
                if vog_result.accepted:
                    filtered.append(chunk)
                    verified.append(chunk)
                    vog_scores.append(vog_result.score)
                else:
                    rejected_vog.append(chunk)

        return {
            "filtered": filtered,
            "verified": verified,
            "rejected_vector": rejected_vector,
            "rejected_srmkg": rejected_vector,  # DEPRECATED alias — see docstring
            "rejected_vog": rejected_vog,
            "vog_scores": vog_scores,
        }
