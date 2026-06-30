---
description: >
  Trigger the Night Gardener to autonomously analyse sessions, infer new
  relations, verify them, and prune stale edges. Also runs the LightGNN
  pruner. Use proactively after heavy ingestion or at end-of-day.
tools:
  - hydramem-server
---

# hydramem-garden

Use this skill to run HydraMem's autonomous knowledge refinement cycle.

## When to invoke

- After ingesting many new documents.
- When the user asks: "Optimise the knowledge graph" or "Run maintenance."
- Periodically (e.g., daily) to keep the graph healthy.

## Workflow

### Check status first

```
get_garden_status_tool()
```

If `is_running: true`, inform the user and stop.

### Run the full cycle

```
run_night_gardener(project=<project>)
```

This executes:
1. **Relation Inference** – LLM analyses recent Q&A sessions.
2. **Two-level Verification** – SR-MKG + VoG filters candidates.
3. **Rule-based Pruning** – removes isolated/orphaned entities.

### Optional: Neural pruning

```
train_gnn_tool(project=<project>, dry_run=false)
```

Trains LightGNN and removes structurally spurious edges.

## Report to user

After completion, summarise:
- Relations proposed, accepted, rejected.
- Entities pruned.
- Last run timestamp.

Suggest running `hydramem stats --last-7d` to see how the knowledge quality
improvements translate to token savings.
