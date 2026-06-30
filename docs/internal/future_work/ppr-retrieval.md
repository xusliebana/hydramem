# Personalized PageRank Retrieval (HippoRAG-style) 🟢

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Immediate win — highest-leverage retrieval upgrade

## Why it matters

The current `hydra_search` performs BFS over the graph from query-derived
seed entities. BFS has no notion of *global importance* and treats every
edge equally, which produces shallow, easily-distracted multi-hop
results. **Personalized PageRank (PPR)** seeded at query entities gives a
principled stationary distribution over the entire graph that
consistently outperforms BFS on multi-hop QA, and it is the backbone of
**HippoRAG / HippoRAG 2** — currently SOTA for memory-augmented LLMs.

## State of the art

- **Topic-Sensitive PageRank** (Haveliwala, 2002) — original PPR
- **HippoRAG** (Gutiérrez et al., 2024) — PPR over entity graph derived
  from passages; outperforms vanilla RAG on multi-hop benchmarks
- **HippoRAG 2** (2024) — adds factual recall via dense retrieval fused
  with PPR scores
- **GNN-RAG / SubgraphRAG** — learned alternatives to PPR; heavier
- **Random-walk with restart** — equivalent formulation, useful for
  intuition

## Proposed architecture

Add PPR as a first-class retrieval mode alongside BFS:

```yaml
search:
  traversal: hybrid          # bfs | ppr | hybrid
  ppr:
    alpha: 0.5               # restart probability (0.3–0.7 typical)
    max_iter: 50
    tol: 1.0e-4
    top_k: 30                # number of nodes to keep before chunk fetch
    edge_weight: confidence  # uniform | confidence | learned
```

**Algorithm in `SearchService`:**

1. Extract seed entities from query (existing logic).
2. Optionally enrich seeds with top-k vector hits' entities.
3. Build personalisation vector `s` with mass `1/|seeds|` on each seed.
4. Run PPR via `scipy.sparse` power iteration over the weighted adjacency.
5. Take top-k nodes by PPR score → fetch their chunks → feed VoG.

In **hybrid** mode, fuse vector and PPR scores via Reciprocal Rank Fusion
(RRF) before VoG.

Cache the sparse adjacency matrix per project; invalidate on mutation.

## Risks

- **Cold start** with no extractable seeds — fall back to vector top-k.
- **Hub explosion**: highly-connected nodes (e.g., "Python") dominate.
  Mitigate with `edge_weight: confidence` and degree-normalisation.
- **Cache staleness** during heavy ingest — version the matrix by
  graph-mutation counter, not by hash (cheaper).

## Computational cost

- Build sparse adjacency: O(E)
- Power iteration: O(E · iters) per query, ~20–50 ms for 10⁵ edges
- Cache hit reduces this to pure SpMV
- RAM: ~50 MB per 10⁵ edges

Comfortably under the existing 1–10 s budget for `hydra_search`.

## Privacy implications

None.

## Local-first viability

Excellent. Pure scipy.

## Suggested implementation strategy

1. Add `hydramem/search/ppr.py` with a `PPRRetriever` class.
2. Extend [`hydramem/search.py`](../../../hydramem/search.py) `hydra_search` with
   `traversal` parameter.
3. Implement RRF fusion when `traversal: hybrid`.
4. Telemetry events `traversal_mode`, `ppr_iters`, `ppr_converged`.
5. Benchmark BFS vs PPR vs hybrid on MuSiQue subset of the dogfood
   corpus; promote winner to default.
6. Update [`docs/architecture.md`](../../architecture.md) with the new
   traversal table.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/search/ppr.py` | **NEW** — sparse PPR with cache |
| [`hydramem/search.py`](../../../hydramem/search.py) | New `traversal` arg, RRF fusion |
| [`hydramem/server.py`](../../../hydramem/server.py) | Expose `traversal` in `hydra_search_tool` |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `SearchConfig.ppr` |
| [`hydramem/storage/graph/networkx_repo.py`](../../../hydramem/storage/graph/networkx_repo.py) | Sparse adjacency export helper |
| [`hydramem/storage/graph/ladybug_repo.py`](../../../hydramem/storage/graph/ladybug_repo.py) | Same export helper |
| `tests/test_search.py` | PPR convergence, RRF correctness, fallback |
| [`scripts/benchmark.py`](../../../scripts/benchmark.py) | BFS vs PPR comparison |

## References

- Haveliwala, *Topic-Sensitive PageRank*, WWW 2002
- Jeh & Widom, *Scaling Personalized Web Search*, WWW 2003
- Gutiérrez et al., *HippoRAG: Neurobiologically Inspired Long-Term Memory
  for Large Language Models*, NeurIPS 2024
- Cormack et al., *Reciprocal Rank Fusion outperforms Condorcet and
  individual Rank Learning Methods*, SIGIR 2009
