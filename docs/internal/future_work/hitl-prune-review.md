# Human-in-the-Loop Pruner Training (active learning) ✅ Shipped (0.2.0)

> **Status:** Shipped in 0.2.0. This doc records the design and the SOTA
> rationale (why it makes sense for a small, local-first system).

## Why it matters

The GNN pruner (`hydramem/gnn_prune.py`) scores graph edges for *spuriousness*
but, until now, had **no supervised signal**: the PyG backend trains
unsupervised (adjacency reconstruction) and the default is a structural
heuristic. There was no way for the system to learn *this deployment's* notion
of a bad edge. Pruning is also irreversible, so blindly trusting an unsupervised
score is risky.

This feature closes the loop: a human verifies a *small, well-chosen* sample of
prune decisions, and those verified labels train a learned scorer. The graph
gets smarter at removing noise without ever shipping data off the machine.

## State of the art

- **Active learning / uncertainty sampling** (Settles, 2009; Lewis & Gale,
  1994) — query the human only for the *most informative* examples: those near
  the decision boundary. We sample edges whose spuriousness is closest to the
  pruner threshold (0.65), so a handful of labels move the model the most.
- **Weak supervision / data programming** (Ratner et al., *Snorkel*, 2017) — the
  heuristic/GNN is a noisy labelling function; human verification turns it into a
  high-quality (golden) training set.
- **Confident Learning / Cleanlab** (Northcutt et al., 2021) — framing "is this
  prune correct?" as label-error detection on graph edges.
- **Graph denoising** — NRGNN (Dai et al., 2021), Pro-GNN (Jin et al., 2020),
  GraphCleaner — learn to drop spurious edges; a little supervision helps a lot.
- **RLHF-style human feedback**, but applied to a *cheap structural classifier*
  rather than an LLM — appropriate for a local, CPU-only budget.

**Does it make sense here?** Yes. For a project competing on *honest + local*,
this is high-leverage and low-cost: no GPU, no cloud, ~100 lines of NumPy, and it
directly attacks the weakest honest link (an unsupervised pruner). It degrades
gracefully (no labels → heuristic as before) and is fully opt-in.

## Architecture

```
Night Gardener cycle (review.enabled)
  └── Phase 3.5: capture
        GNNPruner.feature_rows(project)  → per-edge structural features
        uncertainty band around 0.65     → keep borderline edges
        sample (sample_rate, max_per_run)→ PruneReviewStore (pending)   [no deletion]

hydramem review        → human labels each queued edge: prune | keep | skip
                         (PruneReviewStore → golden dataset, exportable JSONL)

hydramem train-pruner  → pure-NumPy logistic regression over PRUNE_FEATURES
   (or auto_train)       → ~/.hydramem/projects/<p>/prune_weights.json

GNNPruner.analyse()    → prefers the `learned` backend when weights exist
```

Shared feature vector (`PRUNE_FEATURES`, identical at capture / train / score):
`heuristic, jaccard, common, deg_u, deg_v, hub`.

## Configuration

```yaml
night_gardener:
  review:
    enabled: false          # master switch
    sample_rate: 0.2        # fraction of borderline candidates queued
    uncertainty_band: 0.25  # |spuriousness - 0.65| <= band → uncertain
    max_per_run: 50         # cap per cycle
    auto_train: false       # step 2: retrain once enough labels exist
```

## CLI

```bash
hydramem review --project default            # interactive labelling
hydramem review --status                     # queue counts (JSON)
hydramem review --export golden.jsonl        # export the golden dataset
hydramem train-pruner --project default      # learn the edge scorer
hydramem garden-status                        # prune_reviews_queued / pruner_retrained
```

## Risks & honesty

- **Irreversibility of pruning.** The capture step *never deletes* — it only
  flags candidates. Deletion stays with the existing SR-MKG-guarded `apply`.
- **Degenerate models.** The trainer refuses to fit with `< MIN_SAMPLES` labels
  or a single class, rather than persisting a useless model.
- **Bias.** Uncertainty sampling targets borderline edges (informative) and
  yields both classes; we do not only label "obvious" prunes.
- **No client data.** Only public graph structure (degrees, common neighbours)
  is stored — never client text or chain-of-thought.

## Computational cost

Capture: one structural pass over edges (O(E·deg), no torch). Training:
logistic regression on a few hundred rows — sub-second. Scoring: one dot product
per edge. All CPU, all local.

## References

- Settles, *Active Learning Literature Survey*, 2009.
- Ratner et al., *Snorkel: Rapid Training Data Creation with Weak Supervision*, 2017.
- Northcutt et al., *Confident Learning*, JAIR 2021.
- Dai et al., *NRGNN*, KDD 2021; Jin et al., *Pro-GNN*, KDD 2020.
