"""Grafeo vector repository — HNSW vector index inside the Grafeo graph DB.

This backend stores the embedding as a property on the same ``:Chunk`` node
that the graph repository maintains.  When both the graph and the vector
repositories are Grafeo, the factory shares a single ``GrafeoDB`` handle so
there is exactly one persistent directory per process (ACID writes across
graph and vector data, no dual-write inconsistency).

Design notes:
  * The HNSW index is created lazily on first use; ``create_vector_index``
    is idempotent in practice (re-creation raises and we swallow it).
  * Embeddings are attached to existing ``:Chunk`` nodes via Cypher
    ``SET c.embedding = $vec``.  If the chunk node does not exist yet (it
    should — ``KnowledgeStore.add_chunk`` writes the graph first), we
    create it minimally so the vector store never silently drops data.
  * ``vector_search`` return shape is normalised defensively because
    Grafeo's row representation varies by version (dict-with-node vs tuple).
"""

from __future__ import annotations

from typing import Any

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk

logger = get_logger(__name__)

_L_CHUNK = "Chunk"
_PROP_EMBEDDING = "embedding"


class GrafeoVectorRepository:
    """Vector store backed by a Grafeo HNSW index on ``(:Chunk {embedding})``."""

    def __init__(self, db: Any, dim: int = 384) -> None:
        self._db = db
        self._dim = dim
        try:
            self._db.create_vector_index(_L_CHUNK, _PROP_EMBEDDING, dimensions=dim)
            logger.info(
                "GrafeoVectorRepository: HNSW index on (:%s {%s}) dim=%d",
                _L_CHUNK,
                _PROP_EMBEDDING,
                dim,
            )
        except Exception as exc:  # noqa: BLE001 — already exists
            logger.debug("create_vector_index (already exists?): %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _node_props(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if not k.startswith("_")}
        return {}

    def _to_chunk(self, value: Any, similarity: float | None = None) -> Chunk:
        p = self._node_props(value)
        return Chunk(
            id=p.get("id", ""),
            text=p.get("text", ""),
            source=p.get("source", ""),
            chunk_idx=int(p.get("chunk_idx", 0)),
            doc_id=p.get("doc_id", ""),
            project=p.get("project", "default"),
            similarity=similarity if similarity is not None else 0.0,
        )

    # ── Writes ────────────────────────────────────────────────────────────────

    def add(self, chunk: Chunk, embedding: list[float]) -> None:
        vec = [float(x) for x in embedding]
        try:
            # Update if the chunk node already exists (normal path: graph repo
            # writes the node first via KnowledgeStore.add_chunk).
            res = self._db.execute_cypher(
                f"MATCH (c:{_L_CHUNK} {{id: $id}}) "
                f"SET c.{_PROP_EMBEDDING} = $vec RETURN id(c) AS nid",
                {"id": chunk.id, "vec": vec},
            )
            touched = False
            for _ in res:
                touched = True
                break
            if touched:
                return
            # Chunk node not present yet — create it ourselves.
            self._db.create_node(
                [_L_CHUNK],
                {
                    "id": chunk.id,
                    "text": chunk.text,
                    "source": chunk.source,
                    "chunk_idx": int(chunk.chunk_idx),
                    "doc_id": chunk.doc_id,
                    "project": chunk.project,
                    _PROP_EMBEDDING: vec,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("GrafeoVectorRepository.add(%s): %s", chunk.id, exc)

    # ── Reads ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        project: str = "default",
    ) -> list[Chunk]:
        qv = [float(x) for x in query_vector]
        # Over-fetch then filter by project (Grafeo's vector_search has no
        # predicate parameter in 0.5.x).
        try:
            rows = self._db.vector_search(_L_CHUNK, _PROP_EMBEDDING, qv, k=k * 3)
        except Exception as exc:  # noqa: BLE001
            logger.debug("GrafeoVectorRepository.search: %s", exc)
            return []

        results: list[Chunk] = []
        for row in rows or []:
            node_val: Any = None
            score: float | None = None
            if isinstance(row, dict):
                # Common shapes:  {"node": <node>, "score": float}
                #                 {"n": <node>, "_score": float}
                #                 {"id": ..., "text": ..., ...}  (flat)
                if "node" in row:
                    node_val = row["node"]
                elif "n" in row:
                    node_val = row["n"]
                else:
                    node_val = row
                score = row.get("score", row.get("_score"))
            elif isinstance(row, (list, tuple)) and row:
                node_val = row[0]
                if len(row) > 1 and isinstance(row[1], (int, float)):
                    score = float(row[1])
            else:
                node_val = row
            chunk = self._to_chunk(node_val, similarity=score)
            if chunk.project == project:
                results.append(chunk)
            if len(results) >= k:
                break
        return results

    def get_all_raw(self) -> list[dict]:
        try:
            rows = self._db.execute_cypher(
                f"MATCH (c:{_L_CHUNK}) RETURN c.id AS id, c.text AS text, "
                "c.source AS source, c.project AS project"
            )
            out: list[dict] = []
            for row in rows:
                if isinstance(row, dict):
                    out.append({k: row.get(k) for k in ("id", "text", "source", "project")})
                else:
                    out.append(
                        {
                            "id": row[0],
                            "text": row[1],
                            "source": row[2],
                            "project": row[3],
                        }
                    )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.debug("GrafeoVectorRepository.get_all_raw: %s", exc)
            return []
