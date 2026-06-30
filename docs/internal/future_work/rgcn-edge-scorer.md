# R-GCN Edge Scorer (replaces LightGNN heuristic) �

> **Roadmap slot:** Research branch — no shipping commitment (👍 vote to prioritize)
> **Owner:** unassigned
> **Status:** Research branch — converts a placeholder module into a real model

## Why it matters

The current `LightGNN` in [`hydramem/gnn_prune.py`](../../../hydramem/gnn_prune.py)
runs a 2-layer GCN over identity / random features. Without structural
features the model has nothing meaningful to learn, and the heuristic
fallback is in practice indistinguishable from it on small graphs. By
upgrading to:

- **Features**: Laplacian PE (see
  [laplacian-pe.md](laplacian-pe.md)) + degree + relation-type one-hot +
  text-embedding projection
- **Backbone**: relational GCN (R-GCN) or CompGCN — both relation-aware
- **Task**: contrastive link prediction on verified edges vs. corruptions

the GNN becomes a **real edge scorer** usable for:

1. Spurious-edge detection (current LightGNN role)
2. Candidate ranking for the Night Gardener
3. Path scoring in PPR/BFS retrieval re-ranking
4. Confidence boost/dampen during VoG borderline cases

## State of the art

- **R-GCN** (Schlichtkrull et al., 2017) — basis decomposition for many
  relations
- **CompGCN** (Vashishth et al., 2020) — composition operators between
  entity and relation embeddings
- **NBFNet** (Zhu et al., 2021) — strong inductive KGC baseline
- **GraphSAGE** (Hamilton et al., 2017) — sampling for scale
- **BGRL / GRACE** — self-supervised contrastive pretraining

For HydraMem we want the best **inductive** model that fits in CPU/GPU
consumer hardware. R-GCN with shallow depth is the right starting point.

## Proposed architecture

### Training data

Auto-generated each Night Gardener run:

- **Positives**: all relations with `verifier ∈ {vog, manual}` (high
  trust signal)
- **Negatives**: head/tail corruption against random sampled entities,
  filtered to remove existing positives

### Model

```python
# hydramem/garden/rgcn_scorer.py
class RGCNScorer(nn.Module):
    """2-layer R-GCN with DistMult-style scoring head."""
    def __init__(self, num_nodes, num_relations, hidden=128):
        ...
    def forward(self, edge_index, edge_type, x_init):
        ...
    def score(self, h, r, t):
        return torch.sum(self.h_emb[h] * self.r_emb[r] * self.t_emb[t], dim=-1)
```

### Loss

Margin ranking (BPR) with `margin=0.5`, AdamW, ~30 epochs, early stop on
validation AUC.

### Backend gating

Mirrors the existing LightGNN gating:

```python
if num_nodes > MAX_GNN_NODES:
    fallback to heuristic
```

`pyg` extra is opt-in. On CPU-only installs, fallback to a smaller
TransE/DistMult shallow embedding (no PyG required).

## Risks

- **Heavy dependency**: PyTorch + PyG ≈ 2 GB. Keep behind extras and
  document plain alternative.
- **Catastrophic forgetting** between runs. Mitigate by warm-starting
  from previous embedding checkpoint.
- **Bias toward popular relations** — mitigate via sampling weighted by
  relation rarity.
- **Honesty contract**: model output is a *score*, not ground truth.
  Always pass through the same accept/reject thresholds as SR-MKG.

## Computational cost

- Train (10⁴ edges): ~1–3 minutes on CPU, seconds on GPU
- Train (10⁵ edges): ~10–20 minutes on CPU, < 2 minutes on GPU
- Inference: < 1 ms per edge (cached node embeddings)

## Privacy implications

None — purely local.

## Local-first viability

Good with `[gnn]` extra; degrades to heuristic without PyG.

## Suggested implementation strategy

1. Implement `RGCNScorer` in `hydramem/garden/rgcn_scorer.py`.
2. Define training harness in `hydramem/garden/rgcn_train.py` invoked by
   the Night Gardener pruning phase.
3. Cache node embeddings under `~/.hydramem/projects/<p>/rgcn.pt`.
4. Wire into `gnn_prune.py` as a new backend (`backend: "rgcn"`).
5. Add `train_gnn_tool` MCP integration: report train/val AUC.
6. Benchmark vs. LightGNN heuristic on a synthetic noisy graph.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/garden/rgcn_scorer.py` | **NEW** — model |
| `hydramem/garden/rgcn_train.py` | **NEW** — training loop |
| [`hydramem/gnn_prune.py`](../../../hydramem/gnn_prune.py) | Register rgcn backend |
| [`hydramem/server.py`](../../../hydramem/server.py) | `train_gnn_tool` returns AUC |
| [`pyproject.toml`](../../../pyproject.toml) | New `[gnn]` extra (`torch`, `torch_geometric`) |
| `tests/test_gnn_scorer.py` | **NEW** — synthetic graph regression |

## References

- Schlichtkrull et al., *Modeling Relational Data with Graph Convolutional
  Networks*, ESWC 2018
- Vashishth et al., *Composition-based Multi-Relational Graph Convolutional
  Networks*, ICLR 2020
- Zhu et al., *Neural Bellman-Ford Networks: A General Graph Neural
  Network Framework for Link Prediction*, NeurIPS 2021
- Bordes et al., *Translating Embeddings for Modeling Multi-relational
  Data* (TransE), NeurIPS 2013
- Yang et al., *Embedding Entities and Relations for Learning and
  Inference in Knowledge Bases* (DistMult), ICLR 2015
