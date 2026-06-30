# Verification (honest edition)

HydraMem advertises **two-level verification** of relations and chunks. This
page describes exactly what each component does, what it does **not** do, and
how the metrics in `hydramem stats` are computed.

## Two layers, two domains

| Layer  | Operates on | Cost     | Decision                                    |
|--------|-------------|----------|---------------------------------------------|
| SR-MKG | Relations   | No LLM   | Topological score → accept / reject / vog   |
| VoG    | Relations   | 1 LLM    | LLM verdict (GROUNDED / PARTIAL / REJECTED) |

There is also a **chunk prefilter** used inside `hydra_search` that is
sometimes confused with SR-MKG — see the warning at the bottom of this page.

## Layer 1 — SR-MKG (topological scorer)

`hydramem/verification/srmkg.py`. Pure-Python, no LLM, no network. Given a
candidate `Relation(from_entity, to_entity, relation_type, confidence)` and
the topology around its endpoints, it returns:

```
score = w_base       * base_confidence
      + w_jaccard    * jaccard(common_neighbours, deg_a + deg_b - common)
      + w_type_boost * (relation_type is named, not "related_to" / "unknown")
      - penalty_isolated * (any endpoint isolated)
```

Defaults: `w_base = w_jaccard = 0.4`, `w_type_boost = 0.05`,
`penalty_isolated = 0.3`. All four are exposed in `Config` under
`verification.srmkg_*` so you can override them in `config.yml` or replace
them with a learned calibration (see
[Per-project calibration](#per-project-calibration) below).

Decision:

- `score >= srmkg_threshold_accept` (default `0.7`) → **accept**.
- `score < srmkg_threshold_reject` (default `0.3`) → **reject**.
- Otherwise → **borderline** → forward to VoG.

The weights are heuristic. They have not been tuned against a public
benchmark; we treat them as a starting point. The benchmark in
[benchmarks.md](benchmarks.md) is the place to validate any change.

## Layer 2 — VoG (Verification of Groundedness)

`hydramem/verification/vog.py`. Takes the borderline relation and asks an LLM
whether `source_text` and `target_text` actually support the proposed
relation, then parses the verdict (`GROUNDED` / `PARTIAL` / `REJECTED`) and a
confidence number.

**Honest contract** (changed in v0.2.0):

- No `source_text` / `target_text` → **reject** (`score=0`, level
  `vog_no_evidence`). VoG cannot verify what it cannot see.
- LLM unavailable / empty answer → **reject** (level `vog_unavailable`).
  Operators see provider outages immediately in the metrics instead of a
  silently inflated average score.

The pipeline caps VoG calls per cycle (`vog_max_candidates`, default 30) to
keep cost predictable. Borderline relations beyond the cap are accepted with
their SR-MKG score (level `srmkg_cap`).

## The chunk prefilter (NOT SR-MKG)

`VerificationPipeline.verify_chunks(chunks, query)` is used by `hydra_search`
to prune the chunk pool before assembling the final context. It uses **plain
cosine similarity** (`Chunk.similarity` from the vector store) plus VoG for
borderline cases. **It is not topological.** The output dictionary is:

```python
{
    "filtered":         [...],   # chunks kept
    "verified":         [...],   # subset accepted by sim or VoG
    "rejected_vector":  [...],   # cut by similarity prefilter
    "rejected_srmkg":   [...],   # DEPRECATED alias of rejected_vector (v0.1.x compat)
    "rejected_vog":     [...],   # cut by VoG
    "vog_scores":       [...],
}
```

Thresholds are configured separately under `verification.chunk_vector_*`.

The CLI label `Rejected (vector prefilter)` reflects this honestly. The
SQLite column `chunks_rejected_srmkg` is kept for back-compat with v0.1.x
databases but tracks the same number.

## Metrics in `hydramem stats`

| Metric                          | Source                                                 |
|---------------------------------|--------------------------------------------------------|
| `Avg VoG score`                 | mean of `vog_score` recorded in `events` rows          |
| `Rejected (vector prefilter)`   | `SUM(chunks_rejected_srmkg)` (column kept for compat)  |
| `Rejected by VoG`               | `SUM(chunks_rejected_vog)`                             |
| `Hallucinations blocked`        | `SUM(was_hallucination_blocked)` from `verify_relation`|

Use `hydramem stats --raw` to dump the per-event rows used to compute these
totals.

## Per-project calibration

The four SR-MKG weights above are sensible defaults, but every deployment
has a different relation-type distribution. HydraMem can replace the
hard-coded weights with a per-project **logistic regression** fitted on
the local decision history.

### How it works

1. Every SR-MKG decision (auto-accept, auto-reject, VoG verdict, or cap
   fallback) is logged to the `srmkg_decisions` table in
   `~/.hydramem/metrics.db` with its raw component breakdown
   (`base`, `jaccard`, `type_boost`, `isolated`) and the final accept /
   reject label. This is controlled by
   `verification.srmkg_log_decisions` (default `true`).
2. Once enough decisions have accumulated, run:

   ```bash
   hydramem calibrate-srmkg --project default --min-samples 50
   ```

3. The trainer fits an L2-regularised logistic regression on the
   components, holds out 20 % for an honest ROC-AUC estimate, and writes
   the result to:

   ```
   ~/.hydramem/projects/<project>/srmkg_weights.json
   ```

4. On the next instantiation, `SRMKGScorer(project=...)` loads the file
   transparently. The score becomes a sigmoid of the learned linear
   combination — same components, calibrated to the local distribution.

### Honesty rules (enforced)

- Refuses to train when fewer than `--min-samples` decisions exist
  (default 50).
- Refuses to train when only one class (all-accept or all-reject) is
  present — the calibration would be degenerate.
- Reports `auc` and `n_train` in the output JSON so operators can decide
  whether to keep the new weights.

### Useful flags

| Flag | Default | Effect |
|------|---------|--------|
| `--min-samples` | `50` | Minimum decisions required to train |
| `--test-fraction` | `0.2` | Held-out slice used for AUC |
| `--l2` | `1.0` | L2 regularisation strength |
| `--lr` | `0.1` | Gradient-descent learning rate |
| `--epochs` | `500` | Optimiser iterations |
| `--dry-run` | off | Train and print metrics, but do not persist weights |

To revert to the heuristic defaults, simply delete the weights file:

```bash
rm ~/.hydramem/projects/default/srmkg_weights.json
```

Implementation:
[`hydramem/verification/calibration.py`](../hydramem/verification/calibration.py),
[`hydramem/verification/srmkg.py`](../hydramem/verification/srmkg.py).
