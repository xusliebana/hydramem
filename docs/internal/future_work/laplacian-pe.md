# Laplacian Positional Encodings for the GNN Pruner 🟢

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Immediate win

## Why it matters

The current `gnn_prune.py` uses random low-rank features (or identity for
small graphs). With those features, a 2-layer GCN is **functionally
indistinguishable from heuristic message passing on degree** — there is
no structural signal to learn from. Laplacian Positional Encodings (LPE)
give every node a feature vector that already encodes its position in
the global graph structure, turning the GNN into a real spectral model
at near-zero compute cost.

## State of the art

- **Laplacian Eigenmaps** (Belkin & Niyogi, 2003) — foundational
- **Spectral Networks** (Bruna et al., 2014)
- **Positional Encodings for Graphs** (Dwivedi et al., 2022) — formalises
  LPE as the dominant non-trainable PE for GNNs
- **GraphGPS** (Rampášek et al., 2022) — combines LPE with attention
- **Sign-flip ambiguity** — addressed by SignNet (Lim et al., 2022) and
  random sign augmentation

The non-trainable, low-k LPE variant is the cheap and effective option for
a local-first system.

## Proposed architecture

For each project's verified graph:

1. Build the symmetric normalised Laplacian
   $L = I - D^{-1/2} A D^{-1/2}$ (sparse, scipy).
2. Compute the smallest `k` eigenvectors with `scipy.sparse.linalg.eigsh`,
   excluding the trivial eigenvector `1`. Default `k = 32`.
3. Apply random sign flip per eigenvector to mitigate sign ambiguity.
4. Concatenate with normalised node degree, relation-type one-hot, and
   (optionally) a 32-d projection of the entity-name embedding.
5. Cache the LPE in `~/.hydramem/projects/{project}/lpe.npz` keyed by
   the graph hash; recompute when the hash changes.

## Risks

- **Eigendecomposition cost** scales as O(N · k) with sparse Lanczos but
  can fail to converge on disconnected graphs. Solution: compute LPE
  per connected component and zero-pad.
- **Sign ambiguity** — addressed via random flips at training time.
- **Stale cache** — invalidate on every graph mutation that changes node
  set or edge density beyond a threshold.

## Computational cost

- 10⁴ nodes, k=32: < 1 s
- 10⁵ nodes, k=32: ~10–30 s with sparse Lanczos
- Memory: O(N · k) = ~25 MB for 10⁵ × 32 floats

## Privacy implications

None.

## Local-first viability

Excellent — `scipy.sparse.linalg.eigsh` is in the standard scientific
stack already used by HydraMem.

## Suggested implementation strategy

1. Add `hydramem/garden/spectral.py` with `compute_lpe(graph, k)`.
2. In [`hydramem/gnn_prune.py`](../../../hydramem/gnn_prune.py), replace the
   identity / random feature path with LPE + degree + rtype concatenation.
3. Cache LPE per project under `~/.hydramem/projects/<p>/lpe.npz`.
4. Add `gnn.use_laplacian_pe: true` toggle in config (default on).
5. A/B test on dogfood: AUC of edge spuriousness with/without LPE.
6. Document the geometric interpretation in `docs/architecture.md`.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/garden/spectral.py` | **NEW** — `compute_lpe`, `compute_heat_kernel` (latter is a research branch) |
| [`hydramem/gnn_prune.py`](../../../hydramem/gnn_prune.py) | Use LPE features |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `gnn.use_laplacian_pe`, `gnn.lpe_k` |
| [`config.yml.example`](../../../config.yml.example) | Document new options |
| `tests/test_spectral.py` | **NEW** — eigvec dimensions, sign-flip stability |

## References

- Belkin & Niyogi, *Laplacian Eigenmaps for Dimensionality Reduction
  and Data Representation*, Neural Computation 2003
- Dwivedi et al., *Graph Neural Networks with Learnable Structural and
  Positional Representations*, ICLR 2022
- Lim et al., *Sign and Basis Invariant Networks for Spectral Graph
  Representation Learning*, ICLR 2023
- Rampášek et al., *Recipe for a General, Powerful, Scalable Graph
  Transformer*, NeurIPS 2022
