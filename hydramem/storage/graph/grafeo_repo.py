"""Grafeo graph repository — high-performance embedded graph DB (Rust core, PyO3).

Backed by https://pypi.org/project/grafeo/.

Why Grafeo:
  * Single ~5 MB precompiled wheel (no Rust toolchain at install time).
  * Apache-2.0 license.
  * ACID transactions, native Cypher, HNSW vector indexes.
  * Embedded persistent storage in a single directory.

Design choices:
  * We use the native CRUD API (``create_node`` / ``create_edge``) for writes
    because it is strongly-typed and avoids string-escaping pitfalls.
  * Reads use Cypher with parameters for flexibility (traversal, filtering).
  * Grafeo assigns its own ``int`` node ids; HydraMem identifies entities and
    chunks by user-controlled strings (``Entity.id``, ``Chunk.id``).  We keep
    a bidirectional in-memory index that is rebuilt from the DB on open.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, Entity, Relation

logger = get_logger(__name__)

# Node labels
_L_ENTITY = "Entity"
_L_CHUNK = "Chunk"

# Edge types
_E_MENTIONS = "MENTIONS"


class GrafeoGraphRepository:
    """Persistent graph repository backed by Grafeo (Rust core, PyO3 bindings)."""

    def __init__(self, db_path: str | None = None, db: Any = None) -> None:
        """Open (or attach to) a Grafeo database.

        Either ``db_path`` (open new handle) or ``db`` (attach to a pre-opened
        ``GrafeoDB`` instance, used by the factory to share one handle between
        graph and vector repositories) must be provided.
        """
        if db is None:
            if not db_path:
                raise ValueError("GrafeoGraphRepository: db_path or db required")
            try:
                from grafeo import GrafeoDB  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "grafeo not installed — `pip install grafeo` (requires Python ≥ 3.12)"
                ) from exc

            from pathlib import Path

            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            db = GrafeoDB(db_path)

        self._db = db
        self._lock = threading.RLock()

        # external_id (str) -> internal node id (int) for both Entity and Chunk.
        self._entity_ix: dict[str, int] = {}
        self._chunk_ix: dict[str, int] = {}
        self._rebuild_indexes()

    # ── Index rebuild ─────────────────────────────────────────────────────────

    def _rebuild_indexes(self) -> None:
        """Repopulate the str→int id maps by scanning existing nodes."""
        try:
            for row in self._db.execute_cypher(
                f"MATCH (n:{_L_ENTITY}) RETURN id(n) AS nid, n.id AS xid"
            ):
                nid = row["nid"]
                xid = row["xid"]
                if xid is not None:
                    self._entity_ix[xid] = nid
            for row in self._db.execute_cypher(
                f"MATCH (n:{_L_CHUNK}) RETURN id(n) AS nid, n.id AS xid"
            ):
                nid = row["nid"]
                xid = row["xid"]
                if xid is not None:
                    self._chunk_ix[xid] = nid
            logger.info(
                "GrafeoGraphRepository: indexed %d entities, %d chunks",
                len(self._entity_ix),
                len(self._chunk_ix),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Grafeo index rebuild failed (%s) — starting empty", exc)

    @staticmethod
    def _node_props(row_value: Any) -> dict[str, Any]:
        """Extract the properties dict from a Cypher row value.

        When ``RETURN n`` is used, Grafeo returns the node as a plain dict
        with ``_id`` and ``_labels`` metadata keys mixed with the properties.
        """
        if isinstance(row_value, dict):
            return {k: v for k, v in row_value.items() if not k.startswith("_")}
        return {}

    # ── Entities ──────────────────────────────────────────────────────────────

    def add_entity(self, entity: Entity) -> None:
        with self._lock:
            if entity.id in self._entity_ix:
                return  # idempotent
            props = {
                "id": entity.id,
                "name": entity.name,
                "type": entity.type,
                "project": entity.project,
            }
            node = self._db.create_node([_L_ENTITY], props)
            self._entity_ix[entity.id] = node.id

    def list_entities(self, project: str = "default") -> list[dict]:
        rows = self._db.execute_cypher(
            f"MATCH (n:{_L_ENTITY}) WHERE n.project = $project RETURN n",
            {"project": project},
        )
        out: list[dict] = []
        for row in rows:
            props = self._node_props(row.get("n"))
            out.append({"id": props.get("id"), **props})
        return out

    def delete_entity(self, entity_id: str) -> bool:
        with self._lock:
            internal = self._entity_ix.pop(entity_id, None)
            if internal is None:
                return False
            try:
                self._db.delete_node(internal)
            except Exception as exc:  # noqa: BLE001
                logger.warning("delete_entity(%s) failed: %s", entity_id, exc)
                # Restore index entry if delete failed
                self._entity_ix[entity_id] = internal
                return False
            return True

    # ── Relations ─────────────────────────────────────────────────────────────

    def add_relation(self, relation: Relation) -> None:
        with self._lock:
            src = self._entity_ix.get(relation.from_entity)
            dst = self._entity_ix.get(relation.to_entity)
            if src is None or dst is None:
                logger.debug(
                    "add_relation: skipping — missing endpoint(s) %s/%s",
                    relation.from_entity,
                    relation.to_entity,
                )
                return
            props = {
                "relation_type": relation.relation_type,
                "confidence": float(relation.confidence),
                "verified": bool(relation.verified),
                "session_id": relation.session_id,
                "origin_tool": relation.origin_tool,
                "created_at": relation.created_at,
                "qualifiers": json.dumps(relation.qualifiers or {}),
            }
            self._db.create_edge(src, dst, relation.relation_type, props)

    def delete_relation(self, from_entity: str, to_entity: str, relation_type: str) -> bool:
        with self._lock:
            src = self._entity_ix.get(from_entity)
            dst = self._entity_ix.get(to_entity)
            if src is None or dst is None:
                return False
            # Find matching edges via Cypher (Grafeo doesn't expose a CRUD
            # "find edge between two nodes" so we resort to the query layer).
            try:
                rows = self._db.execute_cypher(
                    "MATCH (a)-[r]->(b) WHERE id(a) = $src AND id(b) = $dst "
                    "AND type(r) = $rt RETURN id(r) AS eid",
                    {"src": src, "dst": dst, "rt": relation_type},
                )
                deleted = False
                for row in rows:
                    eid = row["eid"] if isinstance(row, dict) else row[0]
                    try:
                        self._db.delete_edge(eid)
                        deleted = True
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("delete_edge(%s) failed: %s", eid, exc)
                return deleted
            except Exception as exc:  # noqa: BLE001
                logger.warning("delete_relation query failed: %s", exc)
                return False

    def list_relations(self, project: str = "default") -> list[dict]:
        rows = self._db.execute_cypher(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.project = $project "
            "RETURN a.id AS `from`, b.id AS `to`, type(r) AS relation_type, "
            "       r.confidence AS confidence, r.verified AS verified, "
            "       r.session_id AS session_id, r.origin_tool AS origin_tool, "
            "       r.created_at AS created_at, r.qualifiers AS qualifiers",
            {"project": project},
        )
        out: list[dict] = []
        for row in rows:
            if isinstance(row, dict):
                rec = dict(row)
            else:
                cols = [
                    "from",
                    "to",
                    "relation_type",
                    "confidence",
                    "verified",
                    "session_id",
                    "origin_tool",
                    "created_at",
                    "qualifiers",
                ]
                rec = dict(zip(cols, row, strict=False))
            raw_q = rec.get("qualifiers")
            if isinstance(raw_q, str) and raw_q:
                try:
                    raw_q = json.loads(raw_q)
                except (ValueError, TypeError):
                    raw_q = {}
            rec["qualifiers"] = raw_q if isinstance(raw_q, dict) else {}
            out.append(rec)
        return out

    # ── Traversal ─────────────────────────────────────────────────────────────

    def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> list[dict]:
        internal = self._entity_ix.get(entity_id)
        if internal is None:
            return []
        try:
            rows = self._db.execute_cypher(
                f"MATCH (a)-[*1..{int(hops)}]-(b:{_L_ENTITY}) "
                "WHERE id(a) = $src AND id(b) <> $src "
                "RETURN DISTINCT b",
                {"src": internal},
            )
            out: list[dict] = []
            seen: set[str] = set()
            for row in rows:
                props = self._node_props(row.get("b"))
                ext = props.get("id")
                if ext and ext not in seen:
                    seen.add(ext)
                    out.append({"id": ext, **props})
            return out
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_entity_neighbors(%s): %s", entity_id, exc)
            return []

    # ── Chunks ────────────────────────────────────────────────────────────────

    def add_chunk(self, chunk: Chunk) -> None:
        with self._lock:
            if chunk.id in self._chunk_ix:
                return  # idempotent
            props = {
                "id": chunk.id,
                "text": chunk.text,
                "source": chunk.source,
                "chunk_idx": int(chunk.chunk_idx),
                "doc_id": chunk.doc_id,
                "project": chunk.project,
            }
            node = self._db.create_node([_L_CHUNK], props)
            self._chunk_ix[chunk.id] = node.id

    def add_mention(self, chunk_id: str, entity_id: str) -> None:
        with self._lock:
            src = self._chunk_ix.get(chunk_id)
            dst = self._entity_ix.get(entity_id)
            if src is None or dst is None:
                return
            try:
                self._db.create_edge(src, dst, _E_MENTIONS, {})
            except Exception as exc:  # noqa: BLE001
                logger.debug("add_mention(%s→%s): %s", chunk_id, entity_id, exc)

    def get_chunks_near_entity(self, entity_id: str) -> list[Chunk]:
        internal = self._entity_ix.get(entity_id)
        if internal is None:
            return []
        try:
            rows = self._db.execute_cypher(
                f"MATCH (c:{_L_CHUNK})-[:{_E_MENTIONS}]->(e) WHERE id(e) = $eid RETURN c",
                {"eid": internal},
            )
            return [self._chunk_from_row(row.get("c")) for row in rows]
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_chunks_near_entity(%s): %s", entity_id, exc)
            return []

    def get_all_chunks(self) -> list[Chunk]:
        try:
            rows = self._db.execute_cypher(f"MATCH (c:{_L_CHUNK}) RETURN c")
            return [self._chunk_from_row(row.get("c")) for row in rows]
        except Exception as exc:  # noqa: BLE001
            logger.debug("get_all_chunks: %s", exc)
            return []

    def _chunk_from_row(self, row_value: Any) -> Chunk:
        p = self._node_props(row_value)
        return Chunk(
            id=p.get("id", ""),
            text=p.get("text", ""),
            source=p.get("source", ""),
            chunk_idx=int(p.get("chunk_idx", 0)),
            doc_id=p.get("doc_id", ""),
            project=p.get("project", "default"),
        )
