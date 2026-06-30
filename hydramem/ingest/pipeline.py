"""IngestionPipeline — orchestrates chunking, embedding, extraction, and storage.

Single responsibility: coordinate the other services.  Does not implement
any of their logic itself (SRP + DIP — depends on abstractions injected via __init__).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hydramem.core.config import Config, load_config
from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, Entity, Relation
from hydramem.ingest.chunker import MarkdownChunker
from hydramem.ingest.embedder import EmbeddingService
from hydramem.ingest.extractor import EntityExtractor, create_extractor
from hydramem.ingest.registry import EntityRegistry, entity_id
from hydramem.storage.factory import KnowledgeStore, get_store

logger = get_logger(__name__)


# Hard limits for agent-submitted payloads (defence-in-depth against
# runaway / malicious agents).  Configurable via Config.ingest_max_*.
_DEFAULT_MAX_CHUNKS = 200
_DEFAULT_MAX_ENTITIES = 1000
_DEFAULT_MAX_RELATIONS = 500


class IngestionPipeline:
    """Orchestrates the full ingestion flow for a Markdown document.

    Dependencies are injected; defaults are wired from the global config so
    callers don't need to build all objects manually.
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        chunker: MarkdownChunker | None = None,
        embedder: EmbeddingService | None = None,
        extractor: EntityExtractor | None = None,
        config: Config | None = None,
        verifier: Any = None,
    ) -> None:
        cfg = config or load_config()
        self._cfg = cfg
        self._store = store or get_store()
        self._chunker = chunker or MarkdownChunker()
        self._embedder = embedder or EmbeddingService(
            cfg.embedding_model,
            dim=cfg.embedding_dim,
            backend=getattr(cfg, "embedding_backend", None),
        )
        self._extractor = extractor or create_extractor(
            getattr(cfg, "extraction_backend", None), config=cfg
        )
        self._embedding_dim = cfg.embedding_dim
        # Lazy verifier (only built when prechunked ingestion is invoked).
        self._verifier = verifier
        self._max_chunks = int(
            getattr(cfg, "ingest_max_chunks", _DEFAULT_MAX_CHUNKS)
        )
        self._max_entities = int(
            getattr(cfg, "ingest_max_entities", _DEFAULT_MAX_ENTITIES)
        )
        self._max_relations = int(
            getattr(cfg, "ingest_max_relations", _DEFAULT_MAX_RELATIONS)
        )
        self._verify_agent_relations = bool(
            getattr(cfg, "ingest_verify_agent_relations", True)
        )
        self._entity_disambiguation = bool(
            getattr(cfg, "ingest_entity_disambiguation", True)
        )

    def ingest_file(self, file_path: str, project: str = "default") -> dict:
        """Ingest a single Markdown file.  Returns a summary dict."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Not found: {file_path}")
        text = path.read_text(encoding="utf-8")
        doc_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
        result = self.ingest_text(
            text, source=str(path), project=project, doc_id=doc_id
        )
        result["file"] = str(path)
        return result

    def ingest_text(
        self,
        text: str,
        source: str = "note",
        project: str = "default",
        doc_id: str | None = None,
    ) -> dict:
        """Ingest a raw text string through the full pipeline — chunk, embed,
        extract + canonicalise entities.

        This is what the ``remember`` MCP tool uses so an agent can persist a
        fact mid-conversation without writing a file first; the note becomes
        first-class graph knowledge (searchable, verifiable, consolidatable).
        """
        if doc_id is None:
            doc_id = hashlib.sha256(f"{source}:{text[:256]}".encode()).hexdigest()[:16]

        raw_chunks = self._chunker.chunk(text)
        if not raw_chunks:
            return {
                "source": source, "doc_id": doc_id,
                "chunks_added": 0, "entities_added": 0,
                "entities_merged": 0, "project": project,
            }

        # Build chunk metadata up front so we can do a single batched embed call.
        chunk_objs: list[Chunk] = []
        for idx, chunk_text in enumerate(raw_chunks):
            chunk_id = hashlib.md5(f"{doc_id}:{idx}".encode()).hexdigest()
            chunk_objs.append(
                Chunk(
                    id=chunk_id, text=chunk_text, source=source,
                    chunk_idx=idx, doc_id=doc_id, project=project,
                )
            )

        # Batch-embed: ~10× faster than calling embed() per chunk.
        try:
            embeddings = self._embedder.embed_batch([c.text for c in chunk_objs])
        except Exception as exc:
            logger.warning(
                "Batch embedding failed for %s (%s); falling back to zeros",
                source, exc,
            )
            embeddings = [[0.0] * self._embedding_dim for _ in chunk_objs]

        registry = (
            EntityRegistry(project, enabled=True)
            if self._entity_disambiguation
            else None
        )
        stored_chunks = 0
        # Pass A — persist chunks and extract entities, registering every
        # surface form so the registry can pick one best display per entity.
        per_chunk: list[tuple[str, list[Entity]]] = []
        for chunk, embedding in zip(chunk_objs, embeddings, strict=False):
            self._store.add_chunk(chunk, embedding)
            stored_chunks += 1
            extracted = self._extractor.extract(chunk.text, doc_id, project)
            if registry is not None:
                for ent in extracted:
                    registry.register(ent.name, ent.type)
            per_chunk.append((chunk.id, extracted))

        # Pass B — persist canonical entities + MENTIONS. The registry collapses
        # surface-form variants ("HydraMem" / "hydramem" / "Hydra Mem") into a
        # single node, avoiding entity-id collisions and graph fragmentation.
        unique_entities: set[str] = set()
        for chunk_id, extracted in per_chunk:
            for ent in extracted:
                entity = (
                    registry.resolve(ent.name, ent.type, project)
                    if registry
                    else ent
                )
                self._store.add_entity(entity)
                self._store.add_mention(chunk_id, entity.id)
                unique_entities.add(entity.id)

        stored_entities = len(unique_entities)
        merged = registry.merged_count if registry else 0

        logger.info(
            "Ingested %s: %d chunks, %d entities (%d aliases merged, project=%s)",
            source, stored_chunks, stored_entities, merged, project,
        )
        return {
            "source": source,
            "doc_id": doc_id,
            "chunks_added": stored_chunks,
            "entities_added": stored_entities,
            "entities_merged": merged,
            "project": project,
        }

    def ingest_directory(
        self, directory: str, project: str = "default", recursive: bool = True
    ) -> dict:
        """Ingest all .md files in *directory*.  Returns aggregated summary."""
        root = Path(directory)
        pattern = "**/*.md" if recursive else "*.md"
        files = list(root.glob(pattern))

        total_chunks = 0
        total_entities = 0
        files_processed = 0

        for f in files:
            try:
                result = self.ingest_file(str(f), project=project)
                total_chunks += result["chunks_added"]
                total_entities += result["entities_added"]
                files_processed += 1
            except Exception as exc:
                logger.error("Failed to ingest %s: %s", f, exc)

        return {
            "directory": str(root),
            "files_processed": files_processed,
            "chunks_added": total_chunks,
            "entities_added": total_entities,
            "project": project,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Agent-driven (BYO-extraction) ingestion
    # ─────────────────────────────────────────────────────────────────────────

    def ingest_prechunked(
        self,
        source: str,
        chunks: list[dict],
        *,
        doc_id: str | None = None,
        project: str = "default",
        session_id: str = "",
        origin_tool: str = "ingest_prechunked",
    ) -> dict:
        """Ingest a document whose chunking + ER was performed by the caller.

        Expected payload shape per chunk::

            {
              "text":  "raw chunk text",
              "idx":    0,                       # optional, defaults to list order
              "entities": [
                  {"name": "LanceDB", "type": "tool"},
                  ...
              ],
              "relations": [                     # optional
                  {"from": "LanceDB", "to": "HydraMem",
                   "type": "USED_BY", "confidence": 0.8},
                  ...
              ],
            }

        HydraMem still embeds the chunks locally and runs SR-MKG (+ VoG when
        borderline and ``ingest_verify_agent_relations=True``) on every
        relation, so agent hallucinations are filtered before persistence.

        Returns counters: chunks_added, entities_added, relations_proposed,
        relations_accepted, relations_rejected, truncated_*.
        """
        if not isinstance(chunks, list):
            raise TypeError("chunks must be a list")

        # ── Enforce hard limits (defence-in-depth) ────────────────────────
        truncated_chunks = max(0, len(chunks) - self._max_chunks)
        chunks = chunks[: self._max_chunks]

        # Stable doc_id if caller didn't pass one.
        if not doc_id:
            doc_id = hashlib.sha256(source.encode()).hexdigest()[:16]
        created_at = datetime.now(timezone.utc).isoformat()

        # ── 1) Build Chunk objects + batch embed ──────────────────────────
        chunk_objs: list[Chunk] = []
        for idx, payload in enumerate(chunks):
            text = (payload.get("text") or "").strip()
            if not text:
                continue
            chunk_idx = int(payload.get("idx", idx))
            cid = hashlib.md5(f"{doc_id}:{chunk_idx}".encode()).hexdigest()
            chunk_objs.append(
                Chunk(
                    id=cid, text=text, source=source,
                    chunk_idx=chunk_idx, doc_id=doc_id, project=project,
                )
            )

        try:
            embeddings = self._embedder.embed_batch([c.text for c in chunk_objs])
        except Exception as exc:
            logger.warning("ingest_prechunked: batch embed failed (%s) — zeros", exc)
            embeddings = [[0.0] * self._embedding_dim for _ in chunk_objs]

        # ── 2) Persist chunks + agent-supplied entities + MENTIONS ────────
        chunks_added = 0
        entities_added = 0
        # Map external entity name → deterministic id, shared across chunks.
        name_to_id: dict[str, str] = {}
        entity_count = 0
        for chunk, embedding in zip(chunk_objs, embeddings, strict=False):
            self._store.add_chunk(chunk, embedding)
            chunks_added += 1
            raw_payload = chunks[chunk.chunk_idx] if chunk.chunk_idx < len(chunks) else {}
            for ent_dict in raw_payload.get("entities", []) or []:
                if entity_count >= self._max_entities:
                    break
                name = (ent_dict.get("name") or "").strip()
                if not name:
                    continue
                etype = (ent_dict.get("type") or "concept").strip() or "concept"
                eid = name_to_id.get(name) or (
                    entity_id(project, name)
                    if self._entity_disambiguation
                    else hashlib.md5(f"{project}:{name}".encode()).hexdigest()[:12]
                )
                name_to_id[name] = eid
                entity = Entity(id=eid, name=name, type=etype, project=project)
                self._store.add_entity(entity)
                self._store.add_mention(chunk.id, eid)
                entities_added += 1
                entity_count += 1

        truncated_entities = sum(
            max(0, len((c or {}).get("entities") or []))
            for c in chunks
        ) - entities_added
        truncated_entities = max(0, truncated_entities)

        # ── 3) Process agent-supplied relations through verifier ──────────
        relations_proposed = 0
        relations_accepted = 0
        relations_rejected = 0
        truncated_relations = 0

        # Flatten + cap the relation list.
        flat_relations: list[dict] = []
        for payload in chunks:
            flat_relations.extend((payload or {}).get("relations") or [])
        truncated_relations = max(0, len(flat_relations) - self._max_relations)
        flat_relations = flat_relations[: self._max_relations]

        verifier = self._get_verifier() if self._verify_agent_relations else None

        for rel_dict in flat_relations:
            relations_proposed += 1
            from_name = (rel_dict.get("from") or "").strip()
            to_name = (rel_dict.get("to") or "").strip()
            rtype = (rel_dict.get("type") or rel_dict.get("relation_type") or "").strip()
            if not (from_name and to_name and rtype):
                relations_rejected += 1
                continue
            from_id = name_to_id.get(from_name)
            to_id = name_to_id.get(to_name)
            if not (from_id and to_id):
                # Relation references entity not declared in this payload.
                relations_rejected += 1
                continue
            try:
                confidence = float(rel_dict.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            relation = Relation(
                from_entity=from_id, to_entity=to_id,
                relation_type=rtype, confidence=confidence,
                source_text=rel_dict.get("source_text", ""),
                target_text=rel_dict.get("target_text", ""),
                project=project, session_id=session_id,
                origin_tool=origin_tool, created_at=created_at,
            )
            if verifier is None:
                # Verification disabled: trust the agent.
                relation.verified = True
                self._store.add_relation(relation)
                relations_accepted += 1
                continue
            try:
                vr = verifier.verify(relation)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ingest_prechunked: verify failed (%s) — skipping", exc)
                relations_rejected += 1
                continue
            if vr.accepted:
                relation.confidence = float(vr.score)
                relation.verified = True
                self._store.add_relation(relation)
                relations_accepted += 1
            else:
                relations_rejected += 1

        logger.info(
            "ingest_prechunked(%s): chunks=%d entities=%d "
            "relations proposed/accepted/rejected = %d/%d/%d",
            source, chunks_added, entities_added,
            relations_proposed, relations_accepted, relations_rejected,
        )
        return {
            "source": source,
            "doc_id": doc_id,
            "project": project,
            "chunks_added": chunks_added,
            "entities_added": entities_added,
            "relations_proposed": relations_proposed,
            "relations_accepted": relations_accepted,
            "relations_rejected": relations_rejected,
            "truncated_chunks": truncated_chunks,
            "truncated_entities": truncated_entities,
            "truncated_relations": truncated_relations,
            "verified": self._verify_agent_relations,
        }

    def submit_session_extraction(
        self,
        *,
        session_id: str,
        entities: list[dict],
        relations: list[dict],
        project: str = "default",
    ) -> dict:
        """Persist entities + verified relations extracted at session close.

        Unlike ``ingest_prechunked`` there are no chunks: this is a pure
        knowledge-graph contribution. Each entity must declare a ``name``;
        relations reference entities **by name**.
        """
        if not isinstance(entities, list) or not isinstance(relations, list):
            raise TypeError("entities and relations must be lists")

        entities = entities[: self._max_entities]
        truncated_relations = max(0, len(relations) - self._max_relations)
        relations = relations[: self._max_relations]

        created_at = datetime.now(timezone.utc).isoformat()
        name_to_id: dict[str, str] = {}
        entities_added = 0
        for ent_dict in entities:
            name = (ent_dict.get("name") or "").strip()
            if not name:
                continue
            etype = (ent_dict.get("type") or "concept").strip() or "concept"
            eid = hashlib.md5(f"{project}:{name}".encode()).hexdigest()[:12]
            name_to_id[name] = eid
            self._store.add_entity(
                Entity(id=eid, name=name, type=etype, project=project)
            )
            entities_added += 1

        verifier = self._get_verifier() if self._verify_agent_relations else None
        proposed = accepted = rejected = 0
        for rel_dict in relations:
            proposed += 1
            from_name = (rel_dict.get("from") or "").strip()
            to_name = (rel_dict.get("to") or "").strip()
            rtype = (rel_dict.get("type") or rel_dict.get("relation_type") or "").strip()
            if not (from_name and to_name and rtype):
                rejected += 1
                continue
            from_id = name_to_id.get(from_name)
            to_id = name_to_id.get(to_name)
            if not (from_id and to_id):
                rejected += 1
                continue
            try:
                confidence = float(rel_dict.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            relation = Relation(
                from_entity=from_id, to_entity=to_id,
                relation_type=rtype, confidence=confidence,
                project=project, session_id=session_id,
                origin_tool="submit_session_extraction",
                created_at=created_at,
            )
            if verifier is None:
                relation.verified = True
                self._store.add_relation(relation)
                accepted += 1
                continue
            try:
                vr = verifier.verify(relation)
            except Exception as exc:  # noqa: BLE001
                logger.debug("submit_session_extraction: verify failed (%s)", exc)
                rejected += 1
                continue
            if vr.accepted:
                relation.confidence = float(vr.score)
                relation.verified = True
                self._store.add_relation(relation)
                accepted += 1
            else:
                rejected += 1

        return {
            "project": project,
            "session_id": session_id,
            "entities_added": entities_added,
            "relations_proposed": proposed,
            "relations_accepted": accepted,
            "relations_rejected": rejected,
            "truncated_relations": truncated_relations,
            "verified": self._verify_agent_relations,
        }

    # ── Internals ────────────────────────────────────────────────────────

    def _get_verifier(self) -> Any:
        """Lazy build a ``VerificationPipeline`` (avoids LLM init at import)."""
        if self._verifier is None:
            from hydramem.verification.pipeline import VerificationPipeline
            self._verifier = VerificationPipeline(self._cfg)
        return self._verifier