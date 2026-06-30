# Spectral Community Summaries �

> **Roadmap slot:** Research branch — no shipping commitment (👍 vote to prioritize)
> **Owner:** unassigned
> **Status:** Research branch — local equivalent of GraphRAG community summaries

## Why it matters

Microsoft GraphRAG popularised **community summaries**: detect graph
communities, summarise each with an LLM, and serve those summaries for
"global" queries that would otherwise require traversing the entire
graph. HydraMem can do this locally and cheaply with **spectral
clustering**, avoiding the heavyweight Leiden + per-cluster LLM-summary
pattern. The result:

- O(1) answers for *"what does the corpus know about X thematically?"*
- Cheap fuel for the **typed retrieval planner**
  (see [typed-retrieval-planner.md](typed-retrieval-planner.md))
- A natural granularity for the dashboard

## State of the art

- **Spectral clustering** (Ng, Jordan, Weiss, 2001)
- **Microsoft GraphRAG** (Edge et al., 2024) — Leiden + hierarchical
  summaries
- **LightRAG** — dual-level retrieval, simpler than GraphRAG
- **Eigengap heuristic** (von Luxburg, 2007) — automatic k selection
- **Spectral co-clustering** for bipartite chunk-entity graphs

## Proposed architecture

### Pipeline (runs inside Night Gardener)

```
1. Build sparse weighted adjacency (weight = relation confidence)
2. Compute Laplacian eigenvectors
3. Detect k via eigengap
4. KMeans on first k eigenvectors → cluster labels
5. For each cluster:
     - top-N entities by PageRank within cluster
     - top-M relations
     - LLM prompt → summary (cached, only re-summarise if cluster
       Jaccard with previous version < threshold)
6. Persist to ~/.hydramem/projects/<p>/communities/{cluster_id}.json
```

### MCP tool

New tool `community_overview_tool(query: str | None, top_n: int = 3)`:

- if `query`: embed → cosine vs cluster centroid embeddings → return
  top_n summaries
- else: return all summaries

### Cache invalidation

Versioned by:

- graph mutation count
- cluster Jaccard similarity vs. previous version (skip re-summary
  unless < 0.7)

## Risks

- **LLM cost** of (re-)summarising. Mitigate via Jaccard threshold and a
  hard cap on summaries per Night Gardener run.
- **Disconnected components** make spectral clustering brittle. Solve
  per-component, then merge.
- **Concept drift** — old summaries linger. Use TTL of 30 days as
  fallback.

## Computational cost

- Eigendecomposition (k=20 over 10⁵ nodes): ~30 s with sparse Lanczos
- KMeans: < 1 s
- LLM summary cost: dominated by token budget; cap to ~300 tokens out
- Cache hit: < 5 ms

## Privacy implications

None — local processing. Summaries are stored alongside the graph.

## Local-first viability

Excellent.

## Suggested implementation strategy

1. Reuse `hydramem/garden/spectral.py` (introduced for Laplacian PE).
2. Add `hydramem/garden/communities.py` with `detect_communities` and
   `summarise_community`.
3. Add MCP tool `community_overview_tool` in
   [`hydramem/server.py`](../../../hydramem/server.py).
4. Hook into Night Gardener as an optional phase
   (`night_gardener.communities.enabled`).
5. Surface counts in `garden-status`.
6. Document the workflow in [`docs/architecture.md`](../../architecture.md).

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/garden/communities.py` | **NEW** |
| [`hydramem/garden/gardener.py`](../../../hydramem/garden/gardener.py) | Optional community phase |
| [`hydramem/server.py`](../../../hydramem/server.py) | New `community_overview_tool` |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `night_gardener.communities` |
| [`docs/architecture.md`](../../architecture.md) | Document community pipeline |
| `tests/test_communities.py` | **NEW** — synthetic graph clustering |

## References

- Ng, Jordan & Weiss, *On Spectral Clustering: Analysis and an Algorithm*,
  NeurIPS 2001
- von Luxburg, *A Tutorial on Spectral Clustering*, 2007
- Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused
  Summarization*, 2024 (Microsoft GraphRAG)
- Guo et al., *LightRAG: Simple and Fast Retrieval-Augmented Generation*,
  2024
