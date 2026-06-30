"""SearchService — hybrid knowledge retrieval.

Combines vector search (LanceDB), graph traversal, and the SR-MKG + VoG
verification pipeline into a single cohesive class.

All dependencies are injected for testability (DIP).

Performance notes
-----------------
* Per-project entity lookup is cached as a *case-folded inverted index* with a
  short TTL (default 30 s). This avoids the O(N · terms) substring scan that
  used to run on every query. The TTL keeps the cache eventually-consistent
  with concurrent writes (Night Gardener / new ingests).
* ``trace_path`` builds the NetworkX projection on demand and caches it for
  the same TTL window so repeated path queries do not pay the rebuild cost.
"""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict
from dataclasses import replace

from hydramem.core.config import Config, load_config
from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk, relation_valid_at
from hydramem.ingest.embedder import EmbeddingService
from hydramem.storage.factory import KnowledgeStore, get_store
from hydramem.verification.pipeline import VerificationPipeline

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 30.0


class _BM25Index:
    """Tiny Okapi BM25 index over a fixed chunk corpus (pure-Python).

    Built lazily per project and cached with a short TTL. Lexical scoring lets
    exact keyword / identifier hits (names, code spans, rare terms) surface
    even when the dense embedder misses them — the keyword half of hybrid
    retrieval, the way MemPalace's BM25 boosting complements vectors.
    """

    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, chunks: list[Chunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._tf: list[dict[str, int]] = []
        self._len: list[int] = []
        df: dict[str, int] = {}
        for chunk in chunks:
            counts: dict[str, int] = {}
            for tok in self._tokenize(chunk.text):
                counts[tok] = counts.get(tok, 0) + 1
            self._tf.append(counts)
            self._len.append(sum(counts.values()))
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        n_docs = len(chunks)
        self._avgdl = (sum(self._len) / n_docs) if n_docs else 0.0
        self._idf = {tok: math.log(1.0 + (n_docs - n + 0.5) / (n + 0.5)) for tok, n in df.items()}

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        return cls._TOKEN.findall(text.lower())

    def top(self, query: str, top_k: int) -> list[Chunk]:
        terms = [t for t in self._tokenize(query) if t in self._idf]
        if not terms:
            return []
        scored: list[tuple[int, float]] = []
        for i in range(len(self._chunks)):
            dl = self._len[i] or 1
            tf = self._tf[i]
            score = 0.0
            for term in terms:
                f = tf.get(term, 0)
                if not f:
                    continue
                denom = f + self._k1 * (1 - self._b + self._b * dl / (self._avgdl or 1))
                score += self._idf[term] * (f * (self._k1 + 1)) / denom
            if score > 0:
                scored.append((i, score))
        if not scored:
            return []
        scored.sort(key=lambda item: item[1], reverse=True)
        top = scored[:top_k]
        max_score = top[0][1] or 1.0
        out: list[Chunk] = []
        for i, score in top:
            chunk = self._chunks[i]
            # Normalised BM25 as a keyword-boost similarity proxy so lexical
            # hits stay first-class through the downstream vector prefilter.
            boost = round(score / max_score, 4)
            out.append(replace(chunk, similarity=max(chunk.similarity, boost)))
        return out


class SearchService:
    """Unified hybrid search: vector + graph + verification pipeline.

    Usage::

        svc = SearchService()
        result = svc.priming_context("What is the Night Gardener?", k=3)
        result = svc.hydra_search("multi-hop query about LanceDB")
    """

    def __init__(
        self,
        store: KnowledgeStore | None = None,
        embedder: EmbeddingService | None = None,
        pipeline: VerificationPipeline | None = None,
        config: Config | None = None,
    ) -> None:
        cfg = config or load_config()
        self._store = store or get_store()
        self._embedder = embedder or EmbeddingService(
            cfg.embedding_model,
            dim=cfg.embedding_dim,
            backend=getattr(cfg, "embedding_backend", None),
        )
        self._pipeline = pipeline or VerificationPipeline(cfg)
        self._embedding_dim = cfg.embedding_dim
        self._cfg = cfg
        # Per-project caches: (entity_name_index, list_of_entities, last_built_at)
        self._entity_index: dict[str, tuple[dict[str, list[dict]], list[dict], float]] = {}
        # Per-project NetworkX graph cache for trace_path
        self._graph_cache: dict[str, tuple[object, float]] = {}
        # Lazy PPR retriever (built on first use)
        self._ppr = None
        # Lazy typed-retrieval planner (built on first use)
        self._planner = None
        # Lexical BM25 settings + per-project tokenised-index cache.
        self._bm25_enabled = bool(getattr(cfg, "search_bm25", True))
        self._bm25_k1 = float(getattr(cfg, "bm25_k1", 1.5))
        self._bm25_b = float(getattr(cfg, "bm25_b", 0.75))
        self._bm25_top_k = int(getattr(cfg, "bm25_top_k", 0))
        self._bm25_cache: dict[str, tuple[_BM25Index | None, float]] = {}

    def invalidate_cache(self, project: str | None = None) -> None:
        """Drop cached entity index / graph projection.

        Call after bulk writes (ingest, Night Gardener) for immediate consistency.
        Otherwise, caches expire automatically after :data:`_CACHE_TTL_SECONDS`.
        """
        if project is None:
            self._entity_index.clear()
            self._graph_cache.clear()
            self._bm25_cache.clear()
            if self._ppr is not None:
                self._ppr.invalidate()
        else:
            self._entity_index.pop(project, None)
            self._graph_cache.pop(project, None)
            self._bm25_cache.pop(project, None)
            if self._ppr is not None:
                self._ppr.invalidate(project)

    def _entities_with_index(self, project: str) -> tuple[list[dict], dict[str, list[dict]]]:
        """Return (entities, lowercase-token → entities) for *project*.

        The token index lets us resolve query terms in O(terms) instead of
        scanning every entity for every term on every query.
        """
        cached = self._entity_index.get(project)
        now = time.monotonic()
        if cached and (now - cached[2]) < _CACHE_TTL_SECONDS:
            return cached[1], cached[0]

        entities = self._store.list_entities(project=project)
        index: dict[str, list[dict]] = defaultdict(list)
        for ent in entities:
            name = str(ent.get("name", "")).lower()
            if not name:
                continue
            # Index full lowercase name + each whitespace-separated token.
            index[name].append(ent)
            for token in name.split():
                if len(token) >= 2:
                    index[token].append(ent)

        self._entity_index[project] = (dict(index), entities, now)
        return entities, dict(index)

    @staticmethod
    def _lookup_entities(index: dict[str, list[dict]], term: str) -> list[dict]:
        """Substring-match a term against the cached entity name index."""
        term_l = term.lower()
        if not term_l:
            return []
        # Exact-token / full-name hit first (cheap).
        direct = index.get(term_l)
        if direct:
            return direct
        # Fallback: substring match against keys (still bounded by index size,
        # which is much smaller than the full entity list).
        out: list[dict] = []
        for key, ents in index.items():
            if term_l in key:
                out.extend(ents)
        # De-dup by id while preserving order.
        seen: set[str] = set()
        return [e for e in out if not (e.get("id") in seen or seen.add(e.get("id")))]

    # ── Public API ────────────────────────────────────────────────────────────

    def priming_context(self, query: str, project: str = "default", k: int = 3) -> dict:
        """Fast top-k retrieval + immediate graph neighbours. No LLM call."""
        try:
            embedding = self._embedder.embed(query, is_query=True)
        except Exception as exc:
            logger.warning("priming_context embed failed: %s", exc)
            return {"chunks": [], "context": "", "entities": []}

        top_chunks = self._store.vector_search(embedding, k=k, project=project)
        extra: list[Chunk] = []
        terms = self._extract_terms(query)
        if terms:
            _, index = self._entities_with_index(project)
            for term in terms[:3]:
                for ent in self._lookup_entities(index, term):
                    extra.extend(self._store.get_chunks_near_entity(ent["id"]))

        all_chunks = self._deduplicate(top_chunks + extra)
        return {
            "chunks": [c.__dict__ for c in all_chunks],
            "context": self._build_context(all_chunks[: k + 2]),
            "entities": terms,
        }

    def expand_context(
        self, entity_ids: list[str], hops: int = 2, project: str = "default"
    ) -> dict:
        """Expand context from entity IDs via graph traversal."""
        all_chunks: list[Chunk] = []
        all_neighbours: list[dict] = []
        for eid in entity_ids:
            all_neighbours.extend(self._store.get_entity_neighbors(eid, hops=hops))
            all_chunks.extend(self._store.get_chunks_near_entity(eid))
        all_chunks = self._deduplicate(all_chunks)
        return {
            "chunks": [c.__dict__ for c in all_chunks],
            "neighbours": all_neighbours,
            "context": self._build_context(all_chunks),
        }

    def trace_path(self, from_entity: str, to_entity: str, project: str = "default") -> dict:
        """Return the shortest graph path between two entities."""
        try:
            import networkx as nx

            graph = self._cached_graph(project, nx)
            if from_entity in graph and to_entity in graph:
                try:
                    path = nx.shortest_path(graph, from_entity, to_entity)
                    return {"path": path, "length": len(path) - 1, "found": True}
                except nx.NetworkXNoPath:
                    return {"path": [], "length": -1, "found": False}
        except Exception as exc:
            logger.debug("trace_path: %s", exc)
        return {"path": [], "length": -1, "found": False}

    def _cached_graph(self, project: str, nx_module):
        """Return a (cached) NetworkX projection of the entity graph."""
        cached = self._graph_cache.get(project)
        now = time.monotonic()
        if cached and (now - cached[1]) < _CACHE_TTL_SECONDS:
            return cached[0]

        graph = nx_module.DiGraph()
        for ent in self._store.list_entities(project=project):
            graph.add_node(ent["id"], **ent)
            for nb in self._store.get_entity_neighbors(ent["id"], hops=1):
                graph.add_edge(ent["id"], nb["id"])
        self._graph_cache[project] = (graph, now)
        return graph

    def graph_only_search(
        self,
        query: str,
        project: str = "default",
        max_hops: int = 2,
        top_k: int = 10,
    ) -> dict:
        """Pure graph-only retrieval — no vector embeddings.

        Implements the "native Cypher planner" path from the roadmap: resolves
        query terms against the cached entity index, walks neighbours up to
        ``max_hops``, and returns the chunks attached to those entities via
        MENTIONS edges. Useful when the embedder is unavailable or when the
        caller wants a purely symbolic answer.
        """
        terms = self._extract_terms(query)[:8]
        if not terms:
            return {
                "chunks": [],
                "context": "",
                "entities": [],
                "matched_entities": [],
                "method": "graph_only",
            }

        _, index = self._entities_with_index(project)
        seen_entities: dict[str, dict] = {}
        chunks: list[Chunk] = []
        for term in terms:
            for ent in self._lookup_entities(index, term):
                eid = ent.get("id")
                if not eid or eid in seen_entities:
                    continue
                seen_entities[eid] = ent
                chunks.extend(self._store.get_chunks_near_entity(eid))
                if max_hops > 1:
                    for nb in self._store.get_entity_neighbors(eid, hops=max_hops - 1):
                        nb_id = nb.get("id")
                        if nb_id and nb_id not in seen_entities:
                            seen_entities[nb_id] = nb
                            chunks.extend(self._store.get_chunks_near_entity(nb_id))

        chunks = self._deduplicate(chunks)[:top_k]
        return {
            "chunks": [c.__dict__ for c in chunks],
            "context": self._build_context(chunks),
            "entities": terms,
            "matched_entities": list(seen_entities.values()),
            "method": "graph_only",
        }

    # ── Temporal queries (hyper-relational qualifiers) ──────────────────────

    def entity_relations(
        self,
        entity_id: str,
        project: str = "default",
        as_of: str = "",
        direction: str = "both",
    ) -> list[dict]:
        """Relationship facts for *entity_id*, optionally valid at *as_of*.

        The HydraMem-native temporal knowledge-graph query (cf. MemPalace's
        ``query_entity``): reads the qualifier-carrying relation list — so it
        works identically on every graph backend — and filters by temporal
        validity. ``direction`` is ``outgoing`` | ``incoming`` | ``both``.
        """
        facts: list[dict] = []
        for rel in self._store.list_relations(project=project):
            src, dst = rel.get("from"), rel.get("to")
            if direction == "outgoing" and src != entity_id:
                continue
            if direction == "incoming" and dst != entity_id:
                continue
            if direction == "both" and entity_id not in (src, dst):
                continue
            quals = rel.get("qualifiers") or {}
            if as_of and not relation_valid_at(quals, as_of):
                continue
            facts.append(
                {
                    "from": src,
                    "to": dst,
                    "relation_type": rel.get("relation_type"),
                    "confidence": rel.get("confidence"),
                    "valid_from": quals.get("valid_from", ""),
                    "valid_to": quals.get("valid_to", ""),
                    "verifier": quals.get("verifier", ""),
                    "current": not quals.get("valid_to"),
                }
            )
        return facts

    def temporal_neighbors(
        self,
        entity_id: str,
        project: str = "default",
        as_of: str = "",
        hops: int = 1,
        direction: str = "both",
    ) -> list[dict]:
        """Entities reachable from *entity_id* via edges valid at *as_of*.

        Backend-agnostic multi-hop walk over the (time-filtered) relation list,
        so it behaves identically on NetworkX, Grafeo and Ladybug. An empty
        *as_of* includes every edge (a plain neighbour walk).
        """
        adjacency = self._temporal_adjacency(project, as_of, direction)
        seen: set[str] = set()
        frontier: set[str] = {entity_id}
        for _ in range(max(1, hops)):
            nxt: set[str] = set()
            for node in frontier:
                for neighbour in adjacency.get(node, ()):
                    if neighbour != entity_id and neighbour not in seen:
                        seen.add(neighbour)
                        nxt.add(neighbour)
            frontier = nxt
            if not frontier:
                break
        by_id = {e["id"]: e for e in self._store.list_entities(project=project)}
        return [by_id[i] for i in seen if i in by_id]

    def _temporal_adjacency(self, project: str, as_of: str, direction: str) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for rel in self._store.list_relations(project=project):
            quals = rel.get("qualifiers") or {}
            if as_of and not relation_valid_at(quals, as_of):
                continue
            src, dst = rel.get("from"), rel.get("to")
            if not src or not dst:
                continue
            if direction in ("outgoing", "both"):
                adjacency[src].add(dst)
            if direction in ("incoming", "both"):
                adjacency[dst].add(src)
        return adjacency

    def hydra_search(
        self,
        query: str,
        project: str = "default",
        max_hops: int = 3,
        top_k: int = 10,
        traversal: str | None = None,
        strategy_override: str | None = None,
    ) -> dict:
        """Full hybrid search: vector + graph expansion + SR-MKG + VoG.

        ``traversal`` selects how the graph is walked from the query seeds:

        - ``"bfs"``    — original behaviour (default).
        - ``"ppr"``    — Personalized PageRank seeded at query entities.
        - ``"hybrid"`` — BFS chunks + PPR-derived chunks fused via RRF.

        When omitted, falls back to ``cfg.search_traversal`` (``"bfs"``) — or,
        if the typed retrieval planner is enabled, to a zero-shot strategy
        (overridden by an explicit ``strategy_override``).
        """
        # Typed retrieval planner (opt-in): only when the caller did not pin a
        # traversal and gave no explicit override. Low-confidence queries fall
        # through to the configured default (honesty: no fabricated certainty).
        plan = None
        if (
            traversal is None
            and not strategy_override
            and getattr(self._cfg, "planner_enabled", False)
        ):
            plan = self._plan_query(query, top_k)
        if strategy_override:
            traversal = strategy_override
        elif plan is not None:
            traversal = plan.traversal
        traversal = (traversal or getattr(self._cfg, "search_traversal", "bfs")).lower()
        if traversal not in ("bfs", "ppr", "hybrid"):
            traversal = "bfs"
        skip_vog = bool(plan.skip_vog) if plan is not None else False
        bm25_enabled = plan.bm25 if plan is not None else self._bm25_enabled

        try:
            embedding = self._embedder.embed(query, is_query=True)
        except Exception as exc:
            logger.warning("hydra_search embed failed: %s", exc)
            embedding = [0.0] * self._embedding_dim

        vector_chunks = self._store.vector_search(embedding, k=top_k, project=project)

        graph_chunks: list[Chunk] = []
        ppr_chunks: list[Chunk] = []
        ppr_meta: dict | None = None
        seed_ids: list[str] = []
        terms = self._extract_terms(query)[:5]

        if terms:
            _, index = self._entities_with_index(project)
            seen_ent: set[str] = set()
            for term in terms:
                for ent in self._lookup_entities(index, term):
                    eid = ent.get("id")
                    if not eid or eid in seen_ent:
                        continue
                    seen_ent.add(eid)
                    seed_ids.append(eid)
                    if traversal in ("bfs", "hybrid"):
                        graph_chunks.extend(self._store.get_chunks_near_entity(eid))
                        if max_hops > 1:
                            for nb in self._store.get_entity_neighbors(eid, hops=max_hops - 1):
                                graph_chunks.extend(self._store.get_chunks_near_entity(nb["id"]))

            if traversal in ("ppr", "hybrid") and seed_ids:
                ppr_chunks, ppr_meta = self._ppr_chunks(seed_ids, project=project, top_k=top_k)

        if traversal == "hybrid" and ppr_chunks:
            all_chunks = self._fuse_rrf(vector_chunks, graph_chunks, ppr_chunks)
        elif traversal == "ppr":
            all_chunks = self._deduplicate(vector_chunks + ppr_chunks)
        else:
            all_chunks = self._deduplicate(vector_chunks + graph_chunks)

        # Lexical (BM25) arm — recall exact-keyword hits the embedder may miss,
        # then fuse with the semantic/graph ranking via RRF. Degrades to a
        # no-op on an empty corpus or any backend hiccup (local-first safety).
        bm25_chunks: list[Chunk] = []
        if bm25_enabled:
            bm25_chunks = self._bm25_chunks(query, project=project, top_k=top_k)
            if bm25_chunks:
                all_chunks = self._fuse_rankings(all_chunks, bm25_chunks)

        for c in all_chunks:
            c.from_other_project = c.project != project

        if skip_vog:
            # Factoid fast-path: skip the verification prefilter entirely.
            verified: list[Chunk] = []
            vog_scores: list[float] = []
            result = {
                "filtered": all_chunks,
                "verified": [],
                "rejected_vector": [],
                "rejected_vog": [],
                "vog_scores": [],
            }
        else:
            self._pipeline.reset_vog_cap()
            result = self._pipeline.verify_chunks(all_chunks, query=query)
            verified = result["verified"]
            vog_scores = result["vog_scores"]
        final = verified if verified else all_chunks[:3]

        return {
            "chunks": [c.__dict__ for c in all_chunks],
            "filtered": [c.__dict__ for c in result["filtered"]],
            "verified": [c.__dict__ for c in verified],
            "final_context": self._build_context(final),
            "avg_vog_score": sum(vog_scores) / len(vog_scores) if vog_scores else 0.0,
            "chunks_total": len(all_chunks),
            "rejected_vector": len(result.get("rejected_vector", [])),
            "rejected_srmkg": len(result.get("rejected_vector", [])),  # DEPRECATED alias
            "rejected_vog": len(result["rejected_vog"]),
            "traversal": traversal,
            "ppr": ppr_meta,
            "bm25": {"enabled": bm25_enabled, "candidates": len(bm25_chunks)},
            "entities": seed_ids,
            "planner": (
                {"strategy": plan.name, "confidence": plan.confidence} if plan is not None else None
            ),
        }

    def _plan_query(self, query: str, top_k: int):
        """Run the typed retrieval planner; ``None`` on low confidence/error."""
        if self._planner is None:
            from hydramem.planner import ZeroShotPlanner

            self._planner = ZeroShotPlanner(
                self._embedder,
                threshold=getattr(self._cfg, "planner_threshold", 0.15),
            )
        try:
            return self._planner.plan(query, default_top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.debug("planner failed: %s", exc)
            return None

    # ── PPR / fusion helpers ──────────────────────────────────────────────

    def _ppr_chunks(
        self, seed_ids: list[str], *, project: str, top_k: int
    ) -> tuple[list[Chunk], dict]:
        """Run PPR and fetch chunks attached to the highest-PPR entities."""
        if self._ppr is None:
            from hydramem.ppr import PPRRetriever

            self._ppr = PPRRetriever(self._store)
        cfg = self._cfg
        try:
            result = self._ppr.run(
                seed_ids,
                project=project,
                alpha=getattr(cfg, "ppr_alpha", 0.5),
                max_iter=getattr(cfg, "ppr_max_iter", 50),
                tol=getattr(cfg, "ppr_tol", 1e-4),
                top_k=getattr(cfg, "ppr_top_k", max(top_k, 30)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("PPR retrieval failed: %s", exc)
            return [], {"available": False, "error": str(exc)}

        chunks: list[Chunk] = []
        for nid in result.node_scores:
            chunks.extend(self._store.get_chunks_near_entity(nid))
        return self._deduplicate(chunks), {
            "iterations": result.iterations,
            "converged": result.converged,
            "n_seeds": len(result.seeds),
            "n_scored": len(result.node_scores),
        }

    @staticmethod
    def _fuse_rrf(
        vector_chunks: list[Chunk],
        bfs_chunks: list[Chunk],
        ppr_chunks: list[Chunk],
        k: int = 60,
    ) -> list[Chunk]:
        """Fuse three rankings via Reciprocal Rank Fusion, return ordered chunks."""
        from hydramem.ppr import reciprocal_rank_fusion

        rankings = [
            [c.id for c in vector_chunks],
            [c.id for c in bfs_chunks],
            [c.id for c in ppr_chunks],
        ]
        order = reciprocal_rank_fusion(rankings, k=k)
        order_idx = {cid: pos for pos, (cid, _) in enumerate(order)}

        all_by_id: dict[str, Chunk] = {}
        for c in vector_chunks + bfs_chunks + ppr_chunks:
            all_by_id.setdefault(c.id, c)
        return sorted(
            all_by_id.values(),
            key=lambda c: order_idx.get(c.id, len(order_idx)),
        )

    def _bm25_chunks(self, query: str, project: str, top_k: int) -> list[Chunk]:
        """Top chunks for *query* by BM25 over the project corpus (cached)."""
        try:
            index = self._bm25_index(project)
            if index is None:
                return []
            limit = self._bm25_top_k or max(top_k, 10)
            return index.top(query, limit)
        except Exception as exc:  # noqa: BLE001 — lexical arm must never break search
            logger.debug("BM25 arm skipped: %s", exc)
            return []

    def _bm25_index(self, project: str) -> _BM25Index | None:
        cached = self._bm25_cache.get(project)
        now = time.monotonic()
        if cached and (now - cached[1]) < _CACHE_TTL_SECONDS:
            return cached[0]
        corpus = [c for c in self._store.get_all_chunks() if c.project == project]
        index = _BM25Index(corpus, k1=self._bm25_k1, b=self._bm25_b) if corpus else None
        self._bm25_cache[project] = (index, now)
        return index

    @staticmethod
    def _fuse_rankings(*chunk_lists: list[Chunk], k: int = 60) -> list[Chunk]:
        """RRF-fuse any number of already-ordered chunk rankings."""
        from hydramem.ppr import reciprocal_rank_fusion

        rankings = [[c.id for c in cl] for cl in chunk_lists if cl]
        if not rankings:
            return []
        order = reciprocal_rank_fusion(rankings, k=k)
        order_idx = {cid: pos for pos, (cid, _) in enumerate(order)}
        all_by_id: dict[str, Chunk] = {}
        for cl in chunk_lists:
            for c in cl:
                all_by_id.setdefault(c.id, c)
        return sorted(all_by_id.values(), key=lambda c: order_idx.get(c.id, len(order_idx)))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deduplicate(chunks: list[Chunk]) -> list[Chunk]:
        seen: set[str] = set()
        return [c for c in chunks if not (c.id in seen or seen.add(c.id))]  # type: ignore[func-returns-value]

    @staticmethod
    def _build_context(chunks: list[Chunk]) -> str:
        return "\n\n---\n\n".join(
            f"[{i}] Source: {c.source}\n{c.text}" for i, c in enumerate(chunks, 1)
        )

    @staticmethod
    def _extract_terms(query: str) -> list[str]:
        terms: list[str] = []
        terms.extend(re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query))
        terms.extend(re.findall(r"\b[A-Z][a-zA-Z]{1,}\b", query))
        terms.extend(re.findall(r"`([^`]+)`", query))
        return list(dict.fromkeys(terms))
