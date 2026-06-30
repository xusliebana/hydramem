"""Storage factory — auto-selects backends and wires them together.

KnowledgeStore composes one GraphRepository and one VectorRepository.
Callers receive a single facade; they are not coupled to concrete backends.

Default stack (no env vars): Grafeo for **both** graph and vector data,
sharing a single embedded database directory.  Other backends remain
available behind environment switches:

  * ``HYDRAMEM_GRAPH_BACKEND``  — ``grafeo`` (default) | ``networkx`` |
                                  ``kuzu`` | ``ladybug``
  * ``HYDRAMEM_VECTOR_BACKEND`` — ``grafeo`` (default) | ``lancedb`` |
                                  ``memory``
"""

from __future__ import annotations

import os as _os
from typing import Any

from hydramem.core.config import Config, load_config
from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, Entity, Relation
from hydramem.storage.base import GraphRepository, VectorRepository

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared Grafeo handle — one GrafeoDB per (process, path) so the graph and
# the vector repository write to the same ACID database.
# ---------------------------------------------------------------------------

_grafeo_handles: dict[str, Any] = {}


def _open_grafeo(db_path: str) -> Any:
    """Return a (cached) ``GrafeoDB`` instance for ``db_path``.

    Raises ImportError if grafeo is not installed.
    """
    cached = _grafeo_handles.get(db_path)
    if cached is not None:
        return cached
    from pathlib import Path

    from grafeo import GrafeoDB  # type: ignore

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = GrafeoDB(db_path)
    _grafeo_handles[db_path] = db
    return db


# ---------------------------------------------------------------------------
# Backend selection helpers
# ---------------------------------------------------------------------------


def _grafeo_db_path(config: Config) -> str:
    """Resolve the Grafeo DB directory (alias of legacy ``ladybug_db_path``)."""
    return getattr(config, "grafeo_db_path", None) or config.ladybug_db_path


def _create_graph_repo(config: Config) -> GraphRepository:
    """Persistent graph: Grafeo (default) → NetworkX pickle fallback."""
    backend = _os.getenv("HYDRAMEM_GRAPH_BACKEND", "").lower()
    db_path = _grafeo_db_path(config)

    if backend == "kuzu":
        try:
            import kuzu as _mod  # type: ignore

            from hydramem.storage.graph.ladybug_repo import LadybugGraphRepository

            logger.info("Graph backend: Kuzu (opt-in)")
            return LadybugGraphRepository(config.ladybug_db_path, _mod)
        except ImportError:
            logger.warning("Kuzu requested but not installed — falling back")

    if backend == "ladybug":
        try:
            import ladybug as _mod  # type: ignore

            from hydramem.storage.graph.ladybug_repo import LadybugGraphRepository

            logger.info("Graph backend: LadybugDB (opt-in)")
            return LadybugGraphRepository(config.ladybug_db_path, _mod)
        except ImportError:
            logger.warning("LadybugDB requested but not installed — falling back")

    if backend == "networkx":
        from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository

        logger.info("Graph backend: NetworkX (forced) @ %s", db_path)
        return NetworkXGraphRepository(db_path)

    # Default → Grafeo
    if backend in ("", "grafeo"):
        try:
            db = _open_grafeo(db_path)
            from hydramem.storage.graph.grafeo_repo import GrafeoGraphRepository

            logger.info("Graph backend: Grafeo @ %s", db_path)
            return GrafeoGraphRepository(db=db)
        except ImportError:
            if backend == "grafeo":
                logger.warning("Grafeo requested but not installed — falling back")
            else:
                logger.info("Grafeo not available (needs Python ≥ 3.12) — using NetworkX")

    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository

    logger.info("Graph backend: NetworkX (persistent pickle at %s)", db_path)
    return NetworkXGraphRepository(db_path)


def _create_vector_repo(config: Config) -> VectorRepository:
    """Persistent vectors: Grafeo HNSW (default) → LanceDB → in-memory fallback."""
    backend = _os.getenv("HYDRAMEM_VECTOR_BACKEND", "").lower()

    if backend == "lancedb":
        try:
            from hydramem.storage.vector.lancedb_repo import LanceDBVectorRepository

            logger.info("Vector backend: LanceDB (opt-in) @ %s", config.lancedb_path)
            return LanceDBVectorRepository(config.lancedb_path, config.embedding_dim)
        except ImportError:
            logger.warning("LanceDB requested but not installed — falling back")

    if backend == "memory":
        from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

        logger.info("Vector backend: in-memory (forced)")
        return InMemoryVectorRepository()

    # Default → Grafeo HNSW (sharing the GrafeoDB handle with the graph repo).
    if backend in ("", "grafeo"):
        try:
            db = _open_grafeo(_grafeo_db_path(config))
            from hydramem.storage.vector.grafeo_repo import GrafeoVectorRepository

            logger.info(
                "Vector backend: Grafeo HNSW (shared DB) dim=%d",
                config.embedding_dim,
            )
            return GrafeoVectorRepository(db=db, dim=config.embedding_dim)
        except ImportError:
            if backend == "grafeo":
                logger.warning("Grafeo requested but not installed — falling back")

    # Fallback chain: LanceDB → in-memory.
    try:
        from hydramem.storage.vector.lancedb_repo import LanceDBVectorRepository

        logger.info("Vector backend: LanceDB (auto fallback) @ %s", config.lancedb_path)
        return LanceDBVectorRepository(config.lancedb_path, config.embedding_dim)
    except ImportError:
        pass
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    logger.info("Vector backend: in-memory (install grafeo or lancedb for persistence)")
    return InMemoryVectorRepository()


# ---------------------------------------------------------------------------
# KnowledgeStore — unified facade (ISP: exposes only needed methods)
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """Thin facade over GraphRepository + VectorRepository.

    Consumers only interact with this class.  Concrete backends are injected
    via the factory and can be replaced independently (DIP).
    """

    def __init__(
        self,
        graph: GraphRepository,
        vector: VectorRepository,
    ) -> None:
        self._graph = graph
        self._vector = vector

    # ── Write ──────────────────────────────────────────────────────────────

    def add_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        self._graph.add_chunk(chunk)
        self._vector.add(chunk, embedding)

    def add_entity(self, entity: Entity) -> None:
        self._graph.add_entity(entity)

    def add_mention(self, chunk_id: str, entity_id: str) -> None:
        """Persist a MENTIONS edge if the backend supports it (no-op otherwise)."""
        fn = getattr(self._graph, "add_mention", None)
        if fn is not None:
            fn(chunk_id, entity_id)

    def add_relation(self, relation: Relation) -> None:
        self._graph.add_relation(relation)

    def delete_relation(self, from_entity: str, to_entity: str, relation_type: str) -> bool:
        return self._graph.delete_relation(from_entity, to_entity, relation_type)

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity node (and incident edges) if the backend supports it."""
        delete = getattr(self._graph, "delete_entity", None)
        if delete is None:
            return False
        return bool(delete(entity_id))

    def adjust_confidences(
        self,
        entity_id: str,
        delta: float,
        *,
        min_confidence: float = 0.05,
        max_confidence: float = 0.99,
    ) -> int:
        """Shift the confidence of *entity_id*'s outgoing relations by *delta*.

        Clamped to ``[min_confidence, max_confidence]``. Returns the number of
        relations adjusted. No-op (returns 0) on backends that do not implement
        it, so the Night Gardener consolidation phase degrades gracefully.
        """
        fn = getattr(self._graph, "adjust_confidences", None)
        if fn is None:
            return 0
        return int(
            fn(
                entity_id,
                delta,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
            )
        )

    def supersede_relations(
        self, from_entity: str, relation_type: str, keep_to: str, valid_to: str
    ) -> int:
        """Temporally invalidate older edges superseded by a newer functional fact.

        Stamps ``valid_to`` on conflicting ``(from_entity, relation_type, *)``
        edges whose target differs from *keep_to*. Returns the count invalidated.
        No-op (returns 0) on backends that do not implement it.
        """
        fn = getattr(self._graph, "supersede_relations", None)
        if fn is None:
            return 0
        return int(fn(from_entity, relation_type, keep_to, valid_to))

    # ── Read ───────────────────────────────────────────────────────────────

    def vector_search(
        self, query_vector: list[float], k: int = 5, project: str = "default"
    ) -> list[Chunk]:
        return self._vector.search(query_vector, k=k, project=project)

    def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> list[dict]:
        return self._graph.get_entity_neighbors(entity_id, hops=hops)

    def get_chunks_near_entity(self, entity_id: str) -> list[Chunk]:
        return self._graph.get_chunks_near_entity(entity_id)

    def list_entities(self, project: str = "default") -> list[dict]:
        return self._graph.list_entities(project=project)

    def list_relations(self, project: str = "default") -> list[dict]:
        return self._graph.list_relations(project=project)

    def get_all_chunks(self) -> list[Chunk]:
        return self._graph.get_all_chunks()

    def get_all_chunks_for_telemetry(self) -> list[dict]:
        return self._vector.get_all_raw()

    def get_full_document(self, doc_id: str) -> str:
        """Reconstruct the full text of a document from its stored chunks."""
        chunks = sorted(
            [c for c in self._graph.get_all_chunks() if c.doc_id == doc_id],
            key=lambda c: c.chunk_idx,
        )
        return "\n\n".join(c.text for c in chunks)


# ---------------------------------------------------------------------------
# Factory function + module-level singleton
# ---------------------------------------------------------------------------


def create_store(config: Config | None = None) -> KnowledgeStore:
    """Build a KnowledgeStore with auto-selected backends."""
    cfg = config or load_config()
    cfg.ensure_data_dirs()
    return KnowledgeStore(
        graph=_create_graph_repo(cfg),
        vector=_create_vector_repo(cfg),
    )


_default_store: KnowledgeStore | None = None


def get_store() -> KnowledgeStore:
    """Return the process-level singleton KnowledgeStore."""
    global _default_store
    if _default_store is None:
        _default_store = create_store()
    return _default_store
