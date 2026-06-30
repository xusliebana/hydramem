"""KnowledgePruner — Phase 3 of the Night Gardener cycle.

Single responsibility: remove isolated or spurious graph elements.
Does not infer or verify — only prunes.
"""

from __future__ import annotations

from hydramem.core.logging import get_logger
from hydramem.storage.factory import KnowledgeStore

logger = get_logger(__name__)


class KnowledgePruner:
    """Removes isolated entities and optionally runs LightGNN spurious-edge detection.

    The pruner now actually deletes orphaned entities through the
    ``KnowledgeStore.delete_entity`` API. Earlier versions only counted
    candidates without removing them, which inflated ``garden-status``
    metrics — see CHANGELOG entry for v0.2.0.
    """

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def prune(self, project: str = "default", protected_ids: set[str] | None = None) -> dict:
        """Run rule-based pruning. Returns counts of *actually* removed items.

        Entities in *protected_ids* (reuse-protected by the consolidation
        phase) are never removed, even when isolated — a single-degree node
        that gets reused across sessions is meaningful, not noise.
        """
        protected = protected_ids or set()
        pruned_entities = 0
        pruned_edges = 0
        skipped_entities = 0
        prune_protected = 0

        entities = self._store.list_entities(project=project)
        for ent in entities:
            neighbours = self._store.get_entity_neighbors(ent["id"], hops=1)
            chunks = self._store.get_chunks_near_entity(ent["id"])
            if neighbours or chunks:
                continue

            if ent["id"] in protected:
                prune_protected += 1
                continue

            removed = self._store.delete_entity(ent["id"])
            if removed:
                logger.debug("Pruned isolated entity: %s", ent.get("name"))
                pruned_entities += 1
            else:
                # Backend does not yet support deletion: do NOT inflate metrics.
                skipped_entities += 1

        if skipped_entities:
            logger.warning(
                "Pruner: %d isolated entities could not be deleted (backend lacks delete_entity)",
                skipped_entities,
            )

        return {
            "pruned_entities": pruned_entities,
            "pruned_edges": pruned_edges,
            "skipped_entities": skipped_entities,
            "prune_protected": prune_protected,
        }

    def gnn_suggestions(self, project: str = "default", threshold: float = 0.6) -> dict:
        """Run LightGNN spurious-edge detection (optional, requires networkx).

        Returns a dict with 'suggested_edges' and 'method'.
        """
        try:
            from hydramem.gnn_prune import prune_suggestions  # type: ignore

            return prune_suggestions(threshold=threshold).__dict__
        except Exception as exc:
            logger.warning("GNN pruning unavailable: %s", exc)
            return {"suggested_edges": [], "method": "unavailable"}
