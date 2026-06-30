"""Personalized PageRank retrieval (HippoRAG-style).

Pure NumPy implementation — runs on the existing scientific stack with no
extra dependencies. The matrix is built lazily per project and cached
until the caller invalidates it (e.g. after Night Gardener mutations).

Roadmap slot: 0.4.x — Geometric memory.
See ``docs/internal/future_work/ppr-retrieval.md``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from hydramem.core.logging import get_logger

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 60.0


@dataclass
class PPRResult:
    """Outcome of a personalized PageRank retrieval call."""

    node_scores: dict[str, float]
    iterations: int
    converged: bool
    seeds: list[str]


class PPRRetriever:
    """Run Personalized PageRank over the project's entity graph.

    The retriever builds a row-stochastic transition matrix on first use
    and caches it for ``_CACHE_TTL_SECONDS``. ``invalidate(project)``
    clears the cache for ingest / Night Gardener writers.
    """

    def __init__(self, store) -> None:
        self._store = store
        # project -> (nodes, P, built_at)
        self._cache: dict[str, tuple[list[str], object, float]] = {}

    # ------------------------------------------------------------------ API
    def invalidate(self, project: str | None = None) -> None:
        if project is None:
            self._cache.clear()
        else:
            self._cache.pop(project, None)

    def run(
        self,
        seed_nodes: list[str],
        *,
        project: str = "default",
        alpha: float = 0.5,
        max_iter: int = 50,
        tol: float = 1e-4,
        top_k: int = 30,
    ) -> PPRResult:
        """Compute PPR scores seeded at ``seed_nodes``.

        Returns scores for the top-``top_k`` nodes. Falls back to an empty
        result if the graph is empty or none of the seeds are present.
        """
        if not seed_nodes:
            return PPRResult({}, 0, True, [])

        try:
            import numpy as np
        except ImportError:  # pragma: no cover — numpy is a hard dep elsewhere
            logger.warning("PPRRetriever: numpy unavailable, skipping")
            return PPRResult({}, 0, True, [])

        nodes, transition = self._matrix(project)
        if not nodes:
            return PPRResult({}, 0, True, [])

        idx = {nid: i for i, nid in enumerate(nodes)}
        valid_seeds = [s for s in seed_nodes if s in idx]
        if not valid_seeds:
            return PPRResult({}, 0, True, [])

        n = len(nodes)
        s = np.zeros(n, dtype=np.float64)
        weight = 1.0 / len(valid_seeds)
        for sd in valid_seeds:
            s[idx[sd]] = weight

        r = s.copy()
        converged = False
        iters = 0
        for it in range(1, max_iter + 1):
            iters = it
            r_next = (1.0 - alpha) * (transition @ r) + alpha * s
            # L1 normalisation — guards against drift on dangling nodes.
            total = r_next.sum()
            if total > 0:
                r_next = r_next / total
            if float(np.abs(r_next - r).sum()) < tol:
                r = r_next
                converged = True
                break
            r = r_next

        # Top-k by score
        order = np.argsort(-r)
        keep = order[:top_k]
        scores = {nodes[i]: float(r[i]) for i in keep if r[i] > 0.0}
        return PPRResult(
            node_scores=scores,
            iterations=iters,
            converged=converged,
            seeds=valid_seeds,
        )

    # -------------------------------------------------------------- internals
    def _matrix(self, project: str):
        cached = self._cache.get(project)
        now = time.monotonic()
        if cached and (now - cached[2]) < _CACHE_TTL_SECONDS:
            return cached[0], cached[1]

        import numpy as np

        entities = self._store.list_entities(project=project)
        nodes = [e["id"] for e in entities if e.get("id")]
        if not nodes:
            self._cache[project] = (nodes, np.zeros((0, 0)), now)
            return nodes, self._cache[project][1]

        idx = {nid: i for i, nid in enumerate(nodes)}
        n = len(nodes)
        # Sparse-ish: build dense for small graphs (n <= 5k typical), which
        # matches the GNN pruner's safe-mode cap.
        a = np.zeros((n, n), dtype=np.float64)
        for nid in nodes:
            i = idx[nid]
            for nb in self._store.get_entity_neighbors(nid, hops=1):
                j = idx.get(nb.get("id"))
                if j is None:
                    continue
                # Confidence-weighted if available, else uniform.
                w = float(nb.get("confidence", 1.0) or 1.0)
                a[i, j] = max(a[i, j], w)

        # Symmetrise — undirected random walk gives more stable PPR for
        # multi-hop QA where edge direction is often arbitrary.
        a = np.maximum(a, a.T)

        row_sum = a.sum(axis=1, keepdims=True)
        # Replace dangling rows with uniform restart distribution.
        dangling = row_sum.flatten() == 0.0
        row_sum[row_sum == 0.0] = 1.0
        transition = a / row_sum
        if dangling.any():
            transition[dangling, :] = 1.0 / n

        # We use P^T in the iteration: r_next = (1-α) P^T r + α s.
        transition_t = transition.T.copy()
        self._cache[project] = (nodes, transition_t, now)
        return nodes, transition_t


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked lists with the standard RRF formula.

    Cormack et al., SIGIR 2009 — ``score(d) = Σ 1 / (k + rank_i(d))``.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
