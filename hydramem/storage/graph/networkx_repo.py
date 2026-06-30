"""NetworkX graph repository with pickle persistence.

Pure-Python graph backend — no native binaries, no external DB.
State is serialised to a single pickle file under ``db_path`` after every
mutation (atomic write via temp file + ``os.replace``).

For a personal KMS (≲100k entities) this is fast enough and removes the
need for a heavyweight embedded engine like Kuzu/LadybugDB.
"""
from __future__ import annotations

import atexit
import os
import pickle
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

import networkx as nx

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, Entity, Relation, merge_qualifiers

logger = get_logger(__name__)

_PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL


class NetworkXGraphRepository:
    """Persistent NetworkX-backed graph repository.

    State (graph, chunks, mentions) is loaded from ``db_path`` on construction
    and atomically rewritten on every mutation. Thread-safe for the kind of
    single-process access pattern HydraMem expects.
    """

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._chunks: dict[str, Chunk] = {}
        # MENTIONS adjacency: entity_id -> set of chunk_ids
        self._mentions: dict[str, set[str]] = {}
        self._lock = threading.RLock()
        self._dirty = False

        if db_path is None:
            self._path: Path | None = None
            logger.info("NetworkXGraphRepository: in-memory only (no db_path provided)")
            return

        self._path = Path(db_path)
        # If the configured path points at a directory (Kuzu legacy layout)
        # or has no suffix, treat it as a *directory* and place the pickle inside.
        if self._path.suffix == "" or self._path.is_dir():
            self._path.mkdir(parents=True, exist_ok=True)
            self._path = self._path / "graph.pkl"
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._load()
        # Flush on interpreter exit as a safety net.
        atexit.register(self._safe_flush)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            logger.info("NetworkXGraphRepository: starting empty (%s)", self._path)
            return
        try:
            with self._path.open("rb") as f:
                state = pickle.load(f)
            self._graph = state.get("graph", nx.DiGraph())
            self._chunks = state.get("chunks", {})
            self._mentions = state.get("mentions", {})
            logger.info(
                "NetworkXGraphRepository: loaded %d nodes, %d edges, %d chunks from %s",
                self._graph.number_of_nodes(),
                self._graph.number_of_edges(),
                len(self._chunks),
                self._path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load %s: %s — starting empty", self._path, exc)

    def flush(self) -> None:
        """Atomically persist state to disk. Safe to call repeatedly."""
        if self._path is None:
            return
        with self._lock:
            if not self._dirty:
                return
            state = {
                "graph": self._graph,
                "chunks": self._chunks,
                "mentions": self._mentions,
            }
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=".graph-", suffix=".pkl.tmp", dir=str(self._path.parent)
            )
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    pickle.dump(state, f, protocol=_PICKLE_PROTOCOL)
                os.replace(tmp_name, self._path)
                self._dirty = False
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise

    def _safe_flush(self) -> None:
        try:
            self.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("NetworkXGraphRepository: flush at exit failed: %s", exc)

    def _mark_dirty_and_flush(self) -> None:
        self._dirty = True
        self.flush()

    # ── Entities ──────────────────────────────────────────────────────────────

    def add_entity(self, entity: Entity) -> None:
        with self._lock:
            attrs = asdict(entity)
            attrs["_node_type"] = "entity"
            self._graph.add_node(entity.id, **attrs)
            self._mark_dirty_and_flush()

    def list_entities(self, project: str = "default") -> list[dict]:
        return [
            {"id": n, **data}
            for n, data in self._graph.nodes(data=True)
            if data.get("_node_type") == "entity" and data.get("project") == project
        ]

    # ── Relations ─────────────────────────────────────────────────────────────

    def add_relation(self, relation: Relation) -> None:
        with self._lock:
            existing = self._graph.get_edge_data(
                relation.from_entity, relation.to_entity
            )
            qualifiers = dict(relation.qualifiers)
            confidence = relation.confidence
            verified = relation.verified
            # Collision avoidance: a DiGraph keeps a single edge per (from, to)
            # pair, so a blind add_edge would drop accumulated provenance when
            # the same typed edge is re-observed (re-ingest, re-verify). Merge
            # qualifiers and keep the strongest confidence / verified verdict.
            if existing and existing.get("relation_type") == relation.relation_type:
                qualifiers = merge_qualifiers(
                    existing.get("qualifiers") or {}, qualifiers
                )
                confidence = max(confidence, float(existing.get("confidence", 0.0)))
                verified = verified or bool(existing.get("verified", False))
            self._graph.add_edge(
                relation.from_entity,
                relation.to_entity,
                relation_type=relation.relation_type,
                confidence=confidence,
                verified=verified,
                session_id=relation.session_id,
                origin_tool=relation.origin_tool,
                created_at=relation.created_at,
                qualifiers=qualifiers,
            )
            self._mark_dirty_and_flush()

    def delete_relation(
        self, from_entity: str, to_entity: str, relation_type: str
    ) -> bool:
        with self._lock:
            if self._graph.has_edge(from_entity, to_entity):
                self._graph.remove_edge(from_entity, to_entity)
                self._mark_dirty_and_flush()
                return True
            return False

    def delete_entity(self, entity_id: str) -> bool:
        with self._lock:
            if entity_id in self._graph:
                self._graph.remove_node(entity_id)
                self._mentions.pop(entity_id, None)
                self._mark_dirty_and_flush()
                return True
            return False

    def adjust_confidences(
        self,
        entity_id: str,
        delta: float,
        *,
        min_confidence: float = 0.05,
        max_confidence: float = 0.99,
    ) -> int:
        """Shift *entity_id*'s outgoing edge confidences by *delta* (clamped).

        Returns the number of relations adjusted. Used by the Night Gardener's
        consolidation phase to re-weight memory by retrieval reuse.
        """
        with self._lock:
            if entity_id not in self._graph:
                return 0
            adjusted = 0
            for _u, _v, data in self._graph.out_edges(entity_id, data=True):
                current = float(data.get("confidence", 0.0))
                new = min(max_confidence, max(min_confidence, current + delta))
                if new != current:
                    data["confidence"] = new
                    adjusted += 1
            if adjusted:
                self._mark_dirty_and_flush()
            return adjusted

    def supersede_relations(
        self, from_entity: str, relation_type: str, keep_to: str, valid_to: str
    ) -> int:
        """Close the validity window of edges superseded by a newer fact.

        For a *functional* relation a new ``(from_entity, relation_type, keep_to)``
        supersedes any existing ``(from_entity, relation_type, other_to)``: we
        stamp the old edges' ``valid_to`` (temporal invalidation) rather than
        deleting them, so history is preserved and ``as_of`` queries stay
        correct. Returns the number of edges invalidated.
        """
        with self._lock:
            if from_entity not in self._graph:
                return 0
            invalidated = 0
            for _u, v, data in self._graph.out_edges(from_entity, data=True):
                if v == keep_to or data.get("relation_type") != relation_type:
                    continue
                quals = dict(data.get("qualifiers") or {})
                if quals.get("valid_to"):
                    continue  # already closed
                quals["valid_to"] = valid_to
                data["qualifiers"] = quals
                invalidated += 1
            if invalidated:
                self._mark_dirty_and_flush()
            return invalidated

    def list_relations(self, project: str = "default") -> list[dict]:
        return [
            {"from": u, "to": v, **data}
            for u, v, data in self._graph.edges(data=True)
        ]

    # ── Traversal ─────────────────────────────────────────────────────────────

    def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> list[dict]:
        try:
            ego = nx.ego_graph(self._graph, entity_id, radius=hops)
            return [
                {"id": n, **self._graph.nodes[n]}
                for n in ego.nodes
                if n != entity_id
            ]
        except Exception as exc:  # noqa: BLE001
            logger.debug("NetworkXGraphRepository.get_entity_neighbors: %s", exc)
            return []

    # ── Chunks ────────────────────────────────────────────────────────────────

    def add_chunk(self, chunk: Chunk) -> None:
        with self._lock:
            self._chunks[chunk.id] = chunk
            attrs = asdict(chunk)
            attrs["_node_type"] = "chunk"
            self._graph.add_node(chunk.id, **attrs)
            self._mark_dirty_and_flush()

    def get_chunks_near_entity(self, entity_id: str) -> list[Chunk]:
        chunk_ids = self._mentions.get(entity_id, set())
        return [self._chunks[cid] for cid in chunk_ids if cid in self._chunks]

    def add_mention(self, chunk_id: str, entity_id: str) -> None:
        with self._lock:
            self._mentions.setdefault(entity_id, set()).add(chunk_id)
            self._mark_dirty_and_flush()

    def get_all_chunks(self) -> list[Chunk]:
        return list(self._chunks.values())
