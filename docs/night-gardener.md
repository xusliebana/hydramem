# Night Gardener

The Night Gardener is HydraMem's **autonomous offline learning engine**. It analyses stored conversations, infers new knowledge edges, verifies them with a two-level pipeline, and prunes stale or spurious relations — all without human intervention.

---

## Overview

```
Night Gardener cycle
  │
  ├── Phase 1: Relation Inference
  │     LLM reads stored Q&A sessions
  │     Proposes candidate edges between entities
  │
  ├── Phase 2: Two-level Verification
  │     SR-MKG  → topological confidence score (no LLM)
  │               ≥ 0.7 → accept   < 0.3 → reject
  │               0.3–0.7 → forward to VoG
  │     VoG     → LLM step-by-step groundedness check
  │               GROUNDED / PARTIAL / REJECTED + confidence
  │
  ├── Phase 2.4: Temporal invalidation (no LLM)
  │     New functional fact → close the old conflicting edge's valid_to
  │
  ├── Phase 2.5: Consolidation (no LLM)
  │     Boost relations of entities reused across ≥2 sessions
  │     Decay aged one-off isolates; protect reused nodes from prune
  │
  ├── Phase 3: Pruning
  │     Rule-based: remove isolated nodes, zero-confidence edges
  │     LightGNN:   neural spurious-edge scoring (optional)
  │
  └── Phase 3.5: Prune review (opt-in, no LLM)
        Sample borderline spurious-edge candidates → human labels
        Golden dataset → learned (supervised) edge scorer
```

---

## Running the Night Gardener

### On demand (CLI)

```bash
# Run a full cycle on the "default" project
uv run python -c "
from hydramem.garden.gardener import NightGardener
print(NightGardener().run())
"

# Run on a specific project
uv run python -c "
from hydramem.garden.gardener import NightGardener
print(NightGardener().run(project='myproject'))
"
```

### Via MCP tool (from your AI client)

```
"Run the Night Gardener on my default project"
→ AI calls: run_night_gardener(project="default")
```

### Dogfooding script

```bash
# Ingest all docs and run Night Gardener
uv run python scripts/dogfood.py
```

### Scheduled (cron)

Add to your crontab (`crontab -e`):

```cron
# Run HydraMem Night Gardener at 3 AM daily
0 3 * * * cd /path/to/hydramem && uv run python -c "from hydramem.garden.gardener import NightGardener; NightGardener().run()" >> ~/.hydramem/garden.log 2>&1
```

Or with systemd timer (`~/.config/systemd/user/hydramem-garden.timer`):

```ini
[Unit]
Description=HydraMem Night Gardener

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/hydramem-garden.service
[Unit]
Description=HydraMem Night Gardener

[Service]
WorkingDirectory=/path/to/hydramem
ExecStart=uv run python -c "from hydramem.garden.gardener import NightGardener; NightGardener().run()"
```

Enable:
```bash
systemctl --user enable --now hydramem-garden.timer
```

---

## Phase 1: Relation Inference

The Gardener retrieves locally stored sessions captured during real agent interactions. Sessions are grouped by `session_id`, so one interaction can accumulate multiple evidence entries from HydraMem tools.

Each session contains compact snapshots such as the user's query plus grounded context from `priming_context_tool`, `hydra_search_tool`, and `expand_context_tool`, as well as summaries from `trace_path_tool`, `verify_relation_tool`, and `check_conflict_tool`.

Before inference, Night Gardener can filter and prioritize these entries by `repeat_count`. Set `night_gardener.min_repeat_count` above `1` to bias inference toward evidence that has been observed repeatedly across the same session.

HydraMem does **not** have access to the client's private chain-of-thought, so that reasoning is not stored. Only the query and the verified context emitted by the MCP server are persisted for offline analysis.

For each session it sends a structured prompt to the LLM:

```
You are a knowledge-graph curator. Analyse the following Q&A session and
propose up to 5 NEW relations between entities that are NOT yet explicitly stated.

Session: <text>
Known entities: Entity1, Entity2, …

For each proposed relation output one line:
  FROM_ENTITY –[RELATION_TYPE]→ TO_ENTITY  |  CONFIDENCE: <0.0-1.0>
```

The response is parsed with a regex into `Relation` dataclass instances.

**LLM routing**: controlled by `night_gardener.infer_with` in `config.yml`. Defaults to `local` to avoid API costs.

---

## Phase 2: Two-level Verification

### SR-MKG (topological, no LLM)

Each candidate relation is scored based on:

| Factor | Weight |
|--------|--------|
| Jaccard common-neighbour coefficient | 40% |
| Base confidence from inference step | 40% |
| Named relation type boost | +5% |
| Degree penalty (isolated endpoints) | –30% |

```
score = base × 0.4 + jaccard × 0.4 + named_boost – degree_penalty
```

| Score | Action |
|-------|--------|
| ≥ 0.7 | Auto-accept |
| < 0.3 | Auto-reject |
| 0.3–0.7 | Forward to VoG |

### VoG (LLM step-by-step)

VoG sends the candidate relation and both source text fragments to the LLM:

```
Proposed: "HydraMem" –[stores_vectors_in]→ "LanceDB"

Fragment A: "…HydraMem uses LanceDB to index all chunk embeddings…"
Fragment B: "…LanceDB is an embedded, serverless vector database…"

→ GROUNDED  CONFIDENCE: 0.91
```

Result mapping:
- `GROUNDED` → accepted, confidence from LLM
- `PARTIAL` → accepted with reduced confidence (×0.6)
- `REJECTED` → discarded

**LLM routing**: controlled by `verification.vog_use_local_llm` and `night_gardener.verify_with`.

**Cost control**: `vog_max_candidates` (default 30) caps how many borderline relations are sent to VoG per cycle.

---

## Phase 2.4: Temporal invalidation (fact supersession)

Opt-in (`night_gardener.temporal_invalidation.enabled`). When a newly verified
relation has a **functional** type (one you list in
`temporal_invalidation.functional_types`, e.g. `located_in`), older edges with
the same subject + type but a different object have their validity window
**closed** (`valid_to` stamped) instead of being left as a stale contradiction
— the Zep/Graphiti temporal-knowledge-graph pattern, **no LLM, no deletion**.
History is preserved, so `as_of` queries return the old fact before the change
and the new one after it. Count: `relations_invalidated` in `garden-status`.

---

## Phase 2.5: Consolidation (retrieval-success re-weighting)

Between verification and pruning the Gardener re-weights memory by **what gets
reused** across sessions — turning it from a "cron + LLM" into a real
episodic→semantic consolidator. **No LLM call is in this path.**

The reuse signal is derived from telemetry already stored locally
(`entity_reuse()` over the `events` table — the entity ids each `hydra_search`
touched, within `window_days`). For each entity:

- **Boost** (reused across ≥ 2 distinct sessions): the entity's outgoing
  relations gain confidence `tanh(sessions / 5) · boost_per_session`, **divided
  by √degree** so a few hubs don't run away (popularity-bias guard). Such
  entities are also **protected from pruning**, even when otherwise isolated.
- **Decay** (a single-session isolate older than `decay_after_days`):
  confidence drops by up to `decay_per_step`, growing with how overdue it is.

All adjustments are clamped to `[min_confidence, max_confidence]` (no runaway).
The counters `entities_boosted`, `entities_decayed` and `prune_protected` are
exposed in `garden-status` for audit. Configure under
`night_gardener.consolidation.*` (see [configuration.md](configuration.md));
set `enabled: false` to turn it off.

---

## Phase 3: Pruning

### Rule-based

- Remove entities with zero relations (isolated nodes)
- Remove relations with confidence < `srmkg_threshold_reject`
- Remove relations where neither endpoint has any other connections

### LightGNN (optional)

A lightweight Graph Neural Network scores each edge for spuriousness. Edges with a high spuriousness score are added to the prune list.

```bash
# Train the LightGNN pruner from your AI client via the MCP tool:
#   "Train the LightGNN pruner on my default project"
#   → AI calls: train_gnn_tool(project="default")
```

GNN backend auto-detection:
1. `torch` + `torch_geometric` → PyG backend
2. `torch` + `dgl` → DGL backend
3. Heuristic fallback (always available)

---

## Phase 3.5: Prune review (human-in-the-loop, opt-in)

When `night_gardener.review.enabled` is set, the Gardener turns pruning into an
**active-learning loop** that trains the GNN edge scorer from human-verified
labels — no LLM, nothing leaves the machine.

1. **Capture.** A sample of *borderline* spurious-edge candidates (spuriousness
   near the 0.65 threshold — uncertainty sampling) is queued locally with its
   structural features. **Nothing is deleted.** Tuned by `review.sample_rate`,
   `review.uncertainty_band`, `review.max_per_run`.
2. **Label.** `hydramem review` marks each queued edge `prune` / `keep` /
   `skip`; `--status` shows counts and `--export PATH` writes the golden
   dataset as JSONL.
3. **Train.** `hydramem train-pruner` fits a pure-NumPy logistic scorer over the
   labelled features (refusing too-few-samples / single-class, honestly) and
   saves `~/.hydramem/projects/<p>/prune_weights.json`; `GNNPruner` then prefers
   this `learned` backend automatically.
4. **Auto-train (optional).** `review.auto_train` retrains at the end of a cycle
   once enough labels exist.

Counters `prune_reviews_queued` and `pruner_retrained` surface in
`garden-status`. SOTA rationale + design:
[docs/internal/future_work/hitl-prune-review.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/hitl-prune-review.md).

---

## Status and history

```bash
# Check status via CLI
hydramem garden-status --json
```

Status is persisted to `~/.hydramem/garden_status.json`:

```json
{
  "last_run": "2026-05-07T03:00:12+00:00",
  "total_runs": 42,
  "relations_proposed": 317,
  "relations_accepted": 189,
  "relations_rejected": 128,
  "session_entries_filtered_repeat_threshold": 94,
  "nodes_pruned": 14,
  "edges_pruned": 23,
  "is_running": false
}
```

Each `run_night_gardener` execution also returns per-run filtering metrics such as `sessions_considered`, `sessions_used`, `session_entries_considered`, `session_entries_used`, and `session_entries_filtered_repeat_threshold` so you can see how aggressively `night_gardener.min_repeat_count` is narrowing the evidence set.

---

## Configuration reference

```yaml
# config.yml
night_gardener:
  enabled: true
  schedule: "0 3 * * *"   # cron expression
  infer_with: local        # local | openai | anthropic | auto
  verify_with: auto        # local | openai | anthropic | auto

verification:
  srmkg_threshold_accept: 0.7
  srmkg_threshold_reject: 0.3
  vog_max_candidates: 30
  vog_use_local_llm: true  # true → VoG ignores global provider and uses local
```

---

## Design rationale

**Why run it offline?**  
Relation inference requires careful, multi-step LLM reasoning. Running it at low-activity periods (3 AM) avoids competing with real-time query latency.

**Why not infer at query time?**  
SR-MKG + VoG adds 200–2000 ms per relation. For an interactive query returning 20 relations, that would be intolerable.

**Why separate LLM routing?**  
Bulk inference (Phase 1) generates many candidate relations that will mostly be rejected. Running this with a local model (free) and reserving the external API for only the borderline cases (VoG) reduces cost by 70–90 %.
