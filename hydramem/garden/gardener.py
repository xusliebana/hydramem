"""NightGardener — orchestrator for the three-phase autonomous learning cycle.

Single responsibility: coordinate Phase 1 (Inferrer), Phase 2 (VerificationPipeline),
and Phase 3 (Pruner).  Does not implement any phase logic itself (SRP + DIP).
"""
from __future__ import annotations

import math
from datetime import UTC, datetime

from hydramem.core.config import Config, load_config
from hydramem.core.logging import get_logger
from hydramem.core.types import Relation
from hydramem.garden.inferrer import RelationInferrer
from hydramem.garden.pruner import KnowledgePruner
from hydramem.garden.repository import SessionRepository, StatusRepository
from hydramem.llm.factory import create_provider
from hydramem.llm.ollama import OllamaProvider
from hydramem.storage.factory import KnowledgeStore, get_store
from hydramem.telemetry.storage import entity_reuse as _entity_reuse
from hydramem.verification.pipeline import VerificationPipeline

logger = get_logger(__name__)


class NightGardener:
    """Autonomous offline knowledge refinement.

    All dependencies are injected so any component can be swapped or mocked
    (DIP, testability).  Default construction wires everything from config.
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        session_repo: SessionRepository | None = None,
        status_repo: StatusRepository | None = None,
        inferrer: RelationInferrer | None = None,
        pipeline: VerificationPipeline | None = None,
        pruner: KnowledgePruner | None = None,
        config: Config | None = None,
        reuse_fn=None,
        review_store=None,
    ) -> None:
        cfg = config or load_config()
        self._cfg = cfg
        self._store = store or get_store()
        self._session_repo = session_repo or SessionRepository()
        self._status_repo = status_repo or StatusRepository()
        # Retrieval-reuse signal for the consolidation phase (injectable/DIP).
        self._reuse_fn = reuse_fn or _entity_reuse
        # Optional HITL prune-review store (lazily built when review is enabled).
        self._review_store = review_store

        # Phase 1: Inferrer — uses gardener_infer_with provider
        infer_provider = self._make_provider(cfg.gardener_infer_with, cfg)
        self._inferrer = inferrer or RelationInferrer(infer_provider)

        # Phase 2: Verification pipeline
        self._pipeline = pipeline or VerificationPipeline(cfg)

        # Phase 3: Pruner
        self._pruner = pruner or KnowledgePruner(self._store)

    @staticmethod
    def _make_provider(preset: str, cfg: Config):
        if preset in ("local", "ollama"):
            return OllamaProvider(host=cfg.ollama_host, model=cfg.ollama_model)
        if preset == "auto":
            return create_provider(cfg)
        return create_provider(cfg)

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, project: str = "default") -> dict:
        """Execute a full Gardener cycle.  Returns a summary dict."""
        status = self._status_repo.load()
        if status.get("is_running"):
            return {"error": "Night Gardener is already running", "status": status}

        status["is_running"] = True
        self._status_repo.save(status)

        try:
            result = self._run_cycle(project)
        except Exception as exc:
            logger.error("Night Gardener cycle failed: %s", exc)
            result = {"error": str(exc)}
        finally:
            # Reload the latest status so the increments persisted by
            # ``_run_cycle`` are not overwritten by our stale local copy.
            current = self._status_repo.load()
            current["is_running"] = False
            self._status_repo.save(current)

        return result

    def get_status(self) -> dict:
        return self._status_repo.load()

    def save_session(self, session: dict) -> None:
        self._session_repo.save(session)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _run_cycle(self, project: str) -> dict:
        sessions, session_metrics = self._prepare_sessions(
            self._session_repo.last_n(20),
            min_repeat_count=self._cfg.gardener_min_repeat_count,
        )
        entities = self._store.list_entities(project=project)
        entity_names = [e["name"] for e in entities]

        # Phase 1 — Infer
        self._pipeline.reset_vog_cap()
        candidates = self._inferrer.infer(sessions, entity_names, project)

        # Phase 2 — Verify
        accepted: list[Relation] = []
        rejected = 0
        for rel in candidates:
            result = self._pipeline.verify(rel)
            if result.accepted:
                rel.confidence = result.score
                rel.verified = True
                # Provenance (honesty contract): stamp which layer vouched for
                # the edge so the graph stays auditable and SR-MKG can later
                # weigh fresh-vs-stale verifier verdicts.
                _level = getattr(result, "level", "") or ""
                rel.qualifiers["verifier"] = (
                    "vog" if _level.startswith("vog") else "srmkg"
                )
                self._store.add_relation(rel)
                accepted.append(rel)
            else:
                rejected += 1

        # Phase 2.4 — Temporal invalidation of superseded functional relations
        invalidated = self._invalidate_superseded(accepted)

        # Phase 2.5 — Consolidate (retrieval-success re-weighting, no LLM)
        consolidation = self._consolidate(project)

        # Phase 3 — Prune (reuse-protected entities are never removed)
        pruning = self._pruner.prune(
            project=project, protected_ids=consolidation["protected_ids"]
        )

        # Phase 3.5 — Capture borderline prune candidates for human review
        review = self._capture_prune_reviews(project)
        retrained = self._maybe_autotrain(project)

        # Persist status
        status = self._status_repo.load()
        now = datetime.now(UTC).isoformat()
        status.update(
            {
                "last_run": now,
                "total_runs": status.get("total_runs", 0) + 1,
                "relations_proposed": status.get("relations_proposed", 0) + len(candidates),
                "relations_accepted": status.get("relations_accepted", 0) + len(accepted),
                "relations_rejected": status.get("relations_rejected", 0) + rejected,
                "relations_invalidated": (
                    status.get("relations_invalidated", 0) + invalidated
                ),
                "session_entries_filtered_repeat_threshold": (
                    status.get("session_entries_filtered_repeat_threshold", 0)
                    + session_metrics["entries_filtered_repeat_threshold"]
                ),
                "nodes_pruned": status.get("nodes_pruned", 0) + pruning["pruned_entities"],
                "edges_pruned": status.get("edges_pruned", 0) + pruning["pruned_edges"],
                "entities_boosted": (
                    status.get("entities_boosted", 0) + consolidation["entities_boosted"]
                ),
                "entities_decayed": (
                    status.get("entities_decayed", 0) + consolidation["entities_decayed"]
                ),
                "prune_protected": (
                    status.get("prune_protected", 0) + pruning.get("prune_protected", 0)
                ),
                "prune_reviews_queued": (
                    status.get("prune_reviews_queued", 0) + review["queued"]
                ),
                "pruner_retrained": (
                    status.get("pruner_retrained", 0) + (1 if retrained else 0)
                ),
            }
        )
        self._status_repo.save(status)

        logger.info(
            "Night Gardener done: proposed=%d accepted=%d rejected=%d pruned=%d",
            len(candidates), len(accepted), rejected, pruning["pruned_entities"],
        )

        return {
            "project": project,
            "candidates_proposed": len(candidates),
            "relations_accepted": len(accepted),
            "relations_rejected": rejected,
            "relations_invalidated": invalidated,
            "sessions_considered": session_metrics["sessions_considered"],
            "sessions_used": session_metrics["sessions_used"],
            "session_entries_considered": session_metrics["entries_considered"],
            "session_entries_used": session_metrics["entries_used"],
            "session_entries_filtered_repeat_threshold": session_metrics["entries_filtered_repeat_threshold"],
            "nodes_pruned": pruning["pruned_entities"],
            "edges_pruned": pruning["pruned_edges"],
            "entities_boosted": consolidation["entities_boosted"],
            "entities_decayed": consolidation["entities_decayed"],
            "prune_protected": pruning.get("prune_protected", 0),
            "prune_reviews_queued": review["queued"],
            "pruner_retrained": retrained,
            "last_run": now,
        }

    def _invalidate_superseded(self, accepted: list[Relation]) -> int:
        """Phase 2.4 — temporally invalidate older functional relations.

        Zep/Graphiti-style fact supersession: when a newly accepted relation has
        a *functional* type (configured), older edges with the same subject +
        type but a different object get their ``valid_to`` stamped (closed)
        instead of lingering as a stale contradiction. ``as_of`` retrieval then
        returns the old fact before the change and the new one after it. Opt-in
        (``night_gardener.temporal_invalidation.enabled``); only acts on the
        configured ``functional_types``.
        """
        cfg = self._cfg
        if not getattr(cfg, "temporal_invalidation_enabled", False):
            return 0
        ftypes = {t.lower() for t in getattr(cfg, "functional_relation_types", [])}
        if not ftypes:
            return 0
        supersede = getattr(self._store, "supersede_relations", None)
        if supersede is None:
            return 0
        now = datetime.now(UTC).isoformat()
        total = 0
        for rel in accepted:
            if rel.relation_type.lower() not in ftypes:
                continue
            valid_to = rel.qualifiers.get("valid_from") or now
            total += supersede(
                rel.from_entity, rel.relation_type, rel.to_entity, valid_to
            )
        if total:
            logger.info("temporal invalidation: closed %d superseded edge(s)", total)
        return total

    def _consolidate(self, project: str) -> dict:
        """Phase 2.5 — re-weight memory by retrieval reuse (no LLM in the path).

        Boosts the outgoing relations of entities reused across ≥2 distinct
        sessions, decays aged one-off isolates, and returns the set of
        reuse-protected entity ids so the pruner never removes a reused node.
        Boost is tanh-saturated and degree-normalised (÷√degree) to damp hub
        popularity bias; confidences are clamped to [min, max] (no runaway).
        """
        cfg = self._cfg
        result: dict = {
            "entities_boosted": 0,
            "entities_decayed": 0,
            "protected_ids": set(),
        }
        if not getattr(cfg, "consolidation_enabled", True):
            return result
        try:
            reuse = self._reuse_fn(
                project, window_days=getattr(cfg, "consolidation_window_days", 30)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("consolidation: reuse signal unavailable: %s", exc)
            return result

        boost_unit = float(getattr(cfg, "consolidation_boost_per_session", 0.02))
        decay_after = float(getattr(cfg, "consolidation_decay_after_days", 14))
        decay_step = float(getattr(cfg, "consolidation_decay_per_step", 0.05))
        min_conf = float(getattr(cfg, "consolidation_min_confidence", 0.05))
        max_conf = float(getattr(cfg, "consolidation_max_confidence", 0.99))
        adjust = getattr(self._store, "adjust_confidences", None)

        for rec in reuse:
            eid = rec.get("entity_id")
            if not eid:
                continue
            sessions = int(rec.get("sessions_touched", 0))
            days_since = float(rec.get("days_since", 0.0))

            if sessions >= 2:
                # Reuse-protected: a node returned across ≥2 sessions is
                # meaningful even if low-degree — exempt it from pruning.
                result["protected_ids"].add(eid)
                try:
                    degree = max(
                        1, len(self._store.get_entity_neighbors(eid, hops=1))
                    )
                except Exception:  # noqa: BLE001
                    degree = 1
                boost = math.tanh(sessions / 5.0) * boost_unit / math.sqrt(degree)
                if adjust is not None and boost > 0:
                    changed = adjust(
                        eid, boost,
                        min_confidence=min_conf, max_confidence=max_conf,
                    )
                    if changed:
                        result["entities_boosted"] += 1
            elif sessions == 1 and days_since > decay_after:
                # Aged one-off isolate: decay grows with how overdue it is,
                # bounded by decay_per_step (forgetting curve, clamped).
                overdue = days_since - decay_after
                decay = decay_step * (1.0 - math.exp(-overdue / max(decay_after, 1.0)))
                if adjust is not None and decay > 0:
                    changed = adjust(
                        eid, -decay,
                        min_confidence=min_conf, max_confidence=max_conf,
                    )
                    if changed:
                        result["entities_decayed"] += 1
        return result

    def _capture_prune_reviews(self, project: str) -> dict:
        """Phase 3.5 — sample borderline prune candidates for human labelling.

        Active-learning capture: among the GNN pruner's per-edge spuriousness
        scores, keep those near the decision threshold (uncertainty sampling),
        randomly sample a fraction, and queue them for review. **Nothing is
        deleted** — the human's labels become the golden training set. Off
        unless ``night_gardener.review.enabled`` is set.
        """
        cfg = self._cfg
        if not getattr(cfg, "prune_review_enabled", False):
            return {"queued": 0}
        try:
            import random

            from hydramem.garden.review import PruneReviewStore
            from hydramem.gnn_prune import GNNPruner

            store = self._review_store or PruneReviewStore()
            rows = GNNPruner(self._store).feature_rows(project)
        except Exception as exc:  # noqa: BLE001
            logger.warning("prune-review capture unavailable: %s", exc)
            return {"queued": 0}

        threshold = 0.65  # GNNPruner._SPURIOUS_THRESHOLD
        band = float(getattr(cfg, "prune_review_band", 0.25))
        rate = float(getattr(cfg, "prune_review_sample_rate", 0.2))
        cap = int(getattr(cfg, "prune_review_max_per_run", 50))

        candidates = [r for r in rows if abs(r["spuriousness"] - threshold) <= band]
        candidates.sort(key=lambda r: abs(r["spuriousness"] - threshold))
        rng = random.Random(0)
        queued = 0
        for r in candidates:
            if queued >= cap:
                break
            if rng.random() >= rate:
                continue
            if store.add_candidate(
                project=project,
                from_id=r["from_id"], to_id=r["to_id"],
                from_name=r["from_name"], to_name=r["to_name"],
                spuriousness=r["spuriousness"], features=r["features"],
                source="gnn",
            ):
                queued += 1
        if queued:
            logger.info("prune-review: queued %d candidate(s) for labelling", queued)
        return {"queued": queued}

    def _maybe_autotrain(self, project: str) -> bool:
        """Step 2 (opt-in) — retrain the learned pruner from labelled reviews.

        Runs only when ``night_gardener.review.auto_train`` is set and enough
        labels exist. Honest: if the trainer refuses (too few samples / single
        class) we skip rather than persist a degenerate model.
        """
        if not getattr(self._cfg, "prune_review_auto_train", False):
            return False
        try:
            from hydramem.garden.prune_trainer import MIN_SAMPLES, train_pruner
            from hydramem.garden.review import PruneReviewStore

            store = self._review_store or PruneReviewStore()
            labelled = store.stats(project)["labeled"]
            if labelled < MIN_SAMPLES:
                return False
            train_pruner(project, store=store, save=True)
            logger.info(
                "prune-review: auto-trained learned pruner from %d labels", labelled
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("prune-review auto-train skipped: %s", exc)
            return False

    @staticmethod
    def _prepare_sessions(
        sessions: list[dict], min_repeat_count: int = 1
    ) -> tuple[list[dict], dict[str, int]]:
        prepared: list[dict] = []
        metrics = {
            "sessions_considered": len(sessions),
            "sessions_used": 0,
            "entries_considered": 0,
            "entries_used": 0,
            "entries_filtered_repeat_threshold": 0,
        }
        for session in sessions:
            entries = list(session.get("entries") or [])
            if entries:
                metrics["entries_considered"] += len(entries)
                filtered = [
                    entry
                    for entry in entries
                    if int(entry.get("repeat_count", 1) or 1) >= min_repeat_count
                ]
                metrics["entries_used"] += len(filtered)
                metrics["entries_filtered_repeat_threshold"] += len(entries) - len(filtered)
                filtered.sort(
                    key=lambda entry: (
                        int(entry.get("repeat_count", 1) or 1),
                        entry.get("last_seen_at") or entry.get("ts") or "",
                    ),
                    reverse=True,
                )
                if not filtered:
                    continue
                text = SessionRepository._build_text(filtered)
                prepared.append({**session, "entries": filtered, "text": text})
                metrics["sessions_used"] += 1
                continue

            if session.get("text"):
                prepared.append(session)
                metrics["sessions_used"] += 1
                metrics["entries_considered"] += 1
                metrics["entries_used"] += 1

        prepared.sort(
            key=lambda item: max(
                (int(entry.get("repeat_count", 1) or 1) for entry in item.get("entries") or []),
                default=1,
            ),
            reverse=True,
        )
        return prepared, metrics
