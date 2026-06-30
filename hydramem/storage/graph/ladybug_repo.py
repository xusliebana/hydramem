"""LadybugDB / Kuzu graph repository (Cypher-based, persistent).

DEPRECATED: upstream Kuzu is unmaintained (Graphiti dropped it in 2026 for the
same reason). This backend still works but will be removed in a future release.
Use the default Grafeo (Python 3.12+) or NetworkX backend instead.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, Entity, Relation

logger = get_logger(__name__)

_SCHEMA: list[str] = [
    """CREATE NODE TABLE IF NOT EXISTS Chunk (
        id STRING, text STRING, source STRING,
        chunk_idx INT64, doc_id STRING, project STRING,
        PRIMARY KEY(id)
    )""",
    """CREATE NODE TABLE IF NOT EXISTS Entity (
        id STRING, name STRING, type STRING, project STRING,
        PRIMARY KEY(id)
    )""",
    """CREATE REL TABLE IF NOT EXISTS RELATES_TO (
        FROM Entity TO Entity,
        relation_type STRING, confidence DOUBLE, verified BOOLEAN,
        session_id STRING, origin_tool STRING, created_at STRING,
        qualifiers STRING
    )""",
    """CREATE REL TABLE IF NOT EXISTS MENTIONS (FROM Chunk TO Entity)""",
]


class LadybugGraphRepository:
    """Persistent graph repository backed by LadybugDB or Kuzu.

    Both share the same API — `_mod` is whichever is installed.
    """

    def __init__(self, db_path: str, mod: Any) -> None:
        warnings.warn(
            "The Kuzu / LadybugDB graph backend is deprecated and will be removed "
            "in a future release (upstream Kuzu is unmaintained). Migrate to the "
            "default Grafeo (Python 3.12+) or NetworkX backend "
            "(HYDRAMEM_GRAPH_BACKEND=grafeo|networkx).",
            DeprecationWarning,
            stacklevel=2,
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db = mod.Database(db_path)
        self._conn = mod.Connection(db)
        self._apply_schema()
        logger.warning(
            "LadybugGraphRepository @ %s — DEPRECATED backend (unmaintained "
            "upstream); prefer Grafeo or NetworkX.",
            db_path,
        )

    def _apply_schema(self) -> None:
        for stmt in _SCHEMA:
            try:
                self._conn.execute(stmt)
            except Exception:  # noqa: BLE001 — table already exists
                pass

    def _q(self, cypher: str, params: dict | None = None) -> Any:
        return self._conn.execute(cypher, params or {})

    # ── Entities ──────────────────────────────────────────────────────────────

    def add_entity(self, entity: Entity) -> None:
        try:
            self._q(
                "MERGE (e:Entity {id: $id}) SET e.name = $name, e.type = $type,"
                " e.project = $project",
                {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type,
                    "project": entity.project,
                },
            )
        except Exception as exc:
            logger.debug("add_entity: %s", exc)

    def list_entities(self, project: str = "default") -> list[dict]:
        try:
            res = self._q(
                "MATCH (e:Entity) WHERE e.project = $p RETURN e.id, e.name, e.type LIMIT 200",
                {"p": project},
            )
            rows = []
            while res.has_next():
                r = res.get_next()
                rows.append({"id": r[0], "name": r[1], "type": r[2]})
            return rows
        except Exception as exc:
            logger.debug("list_entities: %s", exc)
            return []

    # ── Relations ─────────────────────────────────────────────────────────────

    def add_relation(self, relation: Relation) -> None:
        try:
            self._q(
                "MATCH (a:Entity {id: $from_id}), (b:Entity {id: $to_id})"
                " MERGE (a)-[r:RELATES_TO {relation_type: $rtype}]->(b)"
                " SET r.confidence = $conf, r.verified = $verified,"
                " r.session_id = $sid, r.origin_tool = $origin,"
                " r.created_at = $created_at, r.qualifiers = $qualifiers",
                {
                    "from_id": relation.from_entity,
                    "to_id": relation.to_entity,
                    "rtype": relation.relation_type,
                    "conf": relation.confidence,
                    "verified": relation.verified,
                    "sid": relation.session_id,
                    "origin": relation.origin_tool,
                    "created_at": relation.created_at,
                    "qualifiers": json.dumps(relation.qualifiers or {}),
                },
            )
        except Exception as exc:
            logger.debug("add_relation: %s", exc)

    def delete_relation(self, from_entity: str, to_entity: str, relation_type: str) -> bool:
        try:
            self._q(
                "MATCH (a:Entity {id: $f})-[r:RELATES_TO {relation_type: $t}]->(b:Entity {id: $to})"
                " DELETE r",
                {"f": from_entity, "t": relation_type, "to": to_entity},
            )
            return True
        except Exception as exc:
            logger.debug("delete_relation: %s", exc)
            return False

    def delete_entity(self, entity_id: str) -> bool:
        """Detach and delete an entity node (and any incident edges)."""
        try:
            self._q(
                "MATCH (e:Entity {id: $eid}) DETACH DELETE e",
                {"eid": entity_id},
            )
            return True
        except Exception as exc:
            logger.debug("delete_entity: %s", exc)
            return False

    def list_relations(self, project: str = "default") -> list[dict]:
        try:
            res = self._q(
                "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)"
                " RETURN a.id, b.id, r.relation_type, r.confidence, r.verified,"
                " r.qualifiers"
            )
            rows = []
            while res.has_next():
                r = res.get_next()
                raw_q = r[5]
                if isinstance(raw_q, str) and raw_q:
                    try:
                        raw_q = json.loads(raw_q)
                    except (ValueError, TypeError):
                        raw_q = {}
                rows.append(
                    {
                        "from": r[0],
                        "to": r[1],
                        "relation_type": r[2],
                        "confidence": r[3],
                        "verified": r[4],
                        "qualifiers": raw_q if isinstance(raw_q, dict) else {},
                    }
                )
            return rows
        except Exception as exc:
            logger.debug("list_relations: %s", exc)
            return []

    # ── Traversal ─────────────────────────────────────────────────────────────

    def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> list[dict]:
        try:
            res = self._q(
                "MATCH (a:Entity {id: $eid})-[*1..$hops]-(b:Entity)"
                " RETURN DISTINCT b.id, b.name, b.type",
                {"eid": entity_id, "hops": hops},
            )
            rows = []
            while res.has_next():
                r = res.get_next()
                rows.append({"id": r[0], "name": r[1], "type": r[2]})
            return rows
        except Exception as exc:
            logger.debug("get_entity_neighbors: %s", exc)
            return []

    # ── Chunks ────────────────────────────────────────────────────────────────

    def add_chunk(self, chunk: Chunk) -> None:
        try:
            self._q(
                "MERGE (c:Chunk {id: $id}) SET c.text = $text, c.source = $source,"
                " c.chunk_idx = $idx, c.doc_id = $doc_id, c.project = $project",
                {
                    "id": chunk.id,
                    "text": chunk.text,
                    "source": chunk.source,
                    "idx": chunk.chunk_idx,
                    "doc_id": chunk.doc_id,
                    "project": chunk.project,
                },
            )
        except Exception as exc:
            logger.debug("add_chunk (graph): %s", exc)

    def add_mention(self, chunk_id: str, entity_id: str) -> None:
        """Persist a MENTIONS edge from a chunk to an entity."""
        try:
            self._q(
                "MATCH (c:Chunk {id: $cid}), (e:Entity {id: $eid}) MERGE (c)-[:MENTIONS]->(e)",
                {"cid": chunk_id, "eid": entity_id},
            )
        except Exception as exc:
            logger.debug("add_mention: %s", exc)

    def get_chunks_near_entity(self, entity_id: str) -> list[Chunk]:
        try:
            res = self._q(
                "MATCH (c:Chunk)-[:MENTIONS]->(e:Entity {id: $eid})"
                " RETURN c.id, c.text, c.source, c.chunk_idx, c.doc_id, c.project",
                {"eid": entity_id},
            )
            chunks = []
            while res.has_next():
                r = res.get_next()
                chunks.append(
                    Chunk(
                        id=r[0], text=r[1], source=r[2], chunk_idx=r[3], doc_id=r[4], project=r[5]
                    )
                )
            return chunks
        except Exception as exc:
            logger.debug("get_chunks_near_entity: %s", exc)
            return []

    def get_all_chunks(self) -> list[Chunk]:
        try:
            res = self._q(
                "MATCH (c:Chunk) RETURN c.id, c.text, c.source, c.chunk_idx, c.doc_id, c.project"
            )
            chunks = []
            while res.has_next():
                r = res.get_next()
                chunks.append(
                    Chunk(
                        id=r[0], text=r[1], source=r[2], chunk_idx=r[3], doc_id=r[4], project=r[5]
                    )
                )
            return chunks
        except Exception as exc:
            logger.debug("get_all_chunks: %s", exc)
            return []
