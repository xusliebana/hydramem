# Retrieval-Success Telemetry → Memory Consolidation 🟡

> **Roadmap slot:** 0.5.x — Learned consolidation
> **Owner:** unassigned
> **Status:** Mid-term bet — turns the Night Gardener into a real consolidator

## Why it matters

HydraMem already stores sessions, but no signal of *retrieval success*
ever feeds back into the graph. The Night Gardener today is a `cron +
LLM`. To behave like a hippocampus → neocortex consolidator it must
re-weight memory based on **what gets reused** across sessions:

- An entity returned to the agent in 5 separate sessions across 3 days is
  high-value — boost its outgoing relations' confidence and exempt it
  from prune.
- An isolated entity touched once and never again should decay.

The signal is already on disk; we just need to extract it. **No LLM call
is required** in the critical path.

## State of the art

- **Hippocampal replay** (McClelland et al., 1995; O'Reilly & Norman,
  2002) — biological inspiration for episodic→semantic consolidation
- **HippoRAG** (Gutiérrez et al., 2024) — explicit hippocampal-cortical
  framing in retrieval-augmented LLMs
- **MemGPT recall scoring** — frequency / recency heuristics
- **Forgetting curves** (Ebbinghaus) — exponential decay as default
- **NRGNN / GraphCleaner** — graph denoising via consistency

## Proposed architecture

### 1. Reuse signal

Add a derived view over the existing telemetry events:

```sql
-- materialised in hydramem/telemetry/storage.py
CREATE VIEW entity_reuse_view AS
SELECT
  entity_id,
  project,
  COUNT(DISTINCT session_id)              AS sessions_touched,
  COUNT(*)                                AS total_touches,
  MAX(ts)                                 AS last_touched_at,
  julianday('now') - julianday(MAX(ts))   AS days_since
FROM events_entity_join
GROUP BY entity_id, project;
```

`events_entity_join` is itself derived from the existing `events` table
joined on the entities recorded in each tool call.

### 2. Consolidation phase in the Night Gardener

Add a phase between Inference and Pruning:

```python
# hydramem/garden/gardener.py
def _consolidate(self, project):
    reuse = self._telemetry.entity_reuse(project, window_days=30)
    for entity_id, score in reuse:
        boost = math.tanh(score.sessions_touched / 5.0) * 0.1
        decay = -0.05 * math.exp(-score.days_since / 14.0) if score.sessions_touched == 0 else 0
        self._store.adjust_confidences(entity_id, delta=boost + decay)
```

### 3. Prune protection

Pruning skips any entity whose `sessions_touched > 1` regardless of
isolation — a single-degree node that gets reused is meaningful, not
noise.

### 4. Configuration

```yaml
night_gardener:
  consolidation:
    enabled: true
    window_days: 30
    boost_per_session: 0.02
    decay_after_days: 14
    decay_per_step: 0.05
    min_confidence: 0.05
    max_confidence: 0.99
```

### 5. Audit

Expose in `garden-status`:

```
consolidation:
  entities_boosted: 24
  entities_decayed: 11
  prune_protected: 6
```

## Risks

- **Popularity bias.** A few hubs accumulate boost forever. Mitigate by
  normalising boost by entity degree.
- **Adversarial drift** if a misbehaving agent loops on the same query.
  Mitigate by capping `total_touches` per session and requiring distinct
  sessions for boost.
- **Confidence inflation.** Hard min/max bounds prevent runaway.

## Computational cost

- One pass per Night Gardener run, O(events)
- Sub-second on typical corpora

## Privacy implications

Uses only telemetry already stored locally. No new collection.

## Local-first viability

Excellent.

## Suggested implementation strategy

1. Materialise `entity_reuse_view` (or compute lazily).
2. Add `consolidate()` phase to `NightGardener.run()`.
3. Update `StatusRepository` schema with consolidation counters.
4. CLI: `hydramem garden-status` exposes consolidation block.
5. Tests: synthetic events stream → expected confidence deltas.
6. Document in [`docs/night-gardener.md`](../../night-gardener.md).

## Concrete code changes

| File | Change |
|------|--------|
| [`hydramem/telemetry/storage.py`](../../../hydramem/telemetry/storage.py) | `entity_reuse(project, window_days)` API |
| [`hydramem/garden/gardener.py`](../../../hydramem/garden/gardener.py) | New `_consolidate` phase |
| [`hydramem/garden/repository.py`](../../../hydramem/garden/repository.py) | Counters in `StatusRepository` |
| [`hydramem/storage/base.py`](../../../hydramem/storage/base.py) | `adjust_confidences(entity_id, delta)` |
| [`hydramem/storage/graph/ladybug_repo.py`](../../../hydramem/storage/graph/ladybug_repo.py) | Implement |
| [`hydramem/storage/graph/networkx_repo.py`](../../../hydramem/storage/graph/networkx_repo.py) | Implement |
| [`hydramem/cli.py`](../../../hydramem/cli.py) | Show consolidation block in `garden-status` |
| `tests/test_gardener.py` | Synthetic stream → expected deltas |
| [`docs/night-gardener.md`](../../night-gardener.md) | New consolidation section |

## References

- McClelland, McNaughton & O'Reilly, *Why there are complementary
  learning systems in the hippocampus and neocortex*, Psych Review 1995
- O'Reilly & Norman, *Hippocampal and neocortical contributions to
  memory*, Trends in Cog Sci 2002
- Gutiérrez et al., *HippoRAG*, NeurIPS 2024
- Ebbinghaus, *Memory: A Contribution to Experimental Psychology*, 1885
