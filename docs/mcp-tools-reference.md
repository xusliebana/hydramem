# MCP Tools Reference

HydraMem exposes **18 tools** via the Model Context Protocol (MCP). All tools are available on the HTTP endpoint `http://localhost:3000/mcp`.

Every tool accepts an optional `project` parameter (defaults to `HYDRAMEM_PROJECT` env var or `"default"`) and an optional `session_id` for telemetry grouping.

---

## Retrieval

### 1. `priming_context_tool`

Fast context seeding for conversational turns. Returns top-k chunks + immediate graph neighbours. No LLM call required.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | string | required | Natural-language query |
| `k` | int | 3 | Number of top chunks to return |
| `project` | string | "default" | Project namespace |
| `session_id` | string | auto | Telemetry session UUID |

**Returns**

```json
{
  "chunks": [{ "id": "…", "text": "…", "source": "…" }],
  "context": "[1] Source: docs/architecture.md\nHydraMem is…",
  "entities": ["HydraMem", "LanceDB"]
}
```

**When to use**: At the start of every agent turn for lightweight context.

---

### 2. `expand_context_tool`

Expand a set of entity IDs via multi-hop graph traversal. Use after `priming_context_tool` to follow references.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity_ids` | list[string] | required | Entity IDs to expand from |
| `hops` | int | 2 | Traversal depth |
| `project` | string | "default" | |

**Returns** same structure as `priming_context_tool`.

---

### 3. `hydra_search_tool`

Full hybrid search pipeline: vector ANN + graph traversal + SR-MKG + VoG. Highest accuracy but slower (~200–2000 ms depending on LLM).

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | string | required | |
| `k` | int | 5 | |
| `hops` | int | 2 | Graph traversal depth |
| `project` | string | "default" | |
| `session_id` | string | auto | |
| `traversal` | string | `""` | `bfs` (default), `ppr` (Personalized PageRank, HippoRAG-style), or `hybrid` (RRF fusion of vector + BFS + PPR). Empty string falls back to `search.traversal` from `config.yml`. |

**Returns**

```json
{
  "chunks": […],
  "context": "…",
  "verified_relations": [
    { "from": "HydraMem", "relation": "uses", "to": "LanceDB", "confidence": 0.94 }
  ],
  "entities": […]
}
```

The response also carries `"traversal"` (the mode actually used) and a
`"ppr"` block with `iterations`, `converged`, `n_seeds` and `n_scored`
when PPR ran. See [configuration.md#search-traversal](configuration.md#search-traversal)
for the tuning knobs.

---

### 4. `trace_path_tool`

Find the shortest path between two entities in the knowledge graph. Useful for explaining how two concepts are connected.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `from_entity` | string | required | Entity name or ID |
| `to_entity` | string | required | Entity name or ID |
| `project` | string | "default" | |

**Returns**

```json
{
  "path": ["HydraMem", "LanceDB", "vector embeddings"],
  "relations": ["uses", "stores"],
  "length": 2
}
```

---

### 5. `get_entity_neighbors_tool`

Return N-hop neighbourhood of an entity.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity_id` | string | required | |
| `hops` | int | 2 | |
| `as_of` | string | "" | ISO-8601; when set, only neighbours via relations valid then |
| `project` | string | "default" | |

---

### 6. `get_full_document_tool`

Retrieve the full text of a document by its doc_id.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `doc_id` | string | required | Document identifier |
| `project` | string | "default" | |

---

## Verification

### 7. `verify_relation_tool`

Run the two-level SR-MKG + VoG verification on a proposed relation.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `from_entity` | string | required | |
| `relation_type` | string | required | e.g. `"uses"`, `"implements"` |
| `to_entity` | string | required | |
| `source_text` | string | "" | Supporting text for VoG |
| `project` | string | "default" | |

**Returns**

```json
{
  "accepted": true,
  "srmkg_score": 0.72,
  "vog_result": "GROUNDED",
  "confidence": 0.91
}
```

---

### 8. `check_conflict_tool`

Detect contradictions between two text passages.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `text_a` | string | required | |
| `text_b` | string | required | |
| `project` | string | "default" | |

**Returns**

```json
{
  "conflict_detected": false,
  "explanation": "Both passages agree that LanceDB uses HNSW indexing."
}
```

---

## Ingestion

### 9. `ingest_markdown`

Ingest a single Markdown file into the knowledge base.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `file_path` | string | required | Absolute or relative path to .md file |
| `project` | string | "default" | |

**Returns**

```json
{
  "chunks_added": 14,
  "entities_added": 7,
  "file": "docs/architecture.md"
}
```

---

### 10. `ingest_directory_tool`

Ingest all `.md` files in a directory tree.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `directory` | string | required | |
| `project` | string | "default" | |
| `recursive` | bool | true | |

---

### 10a. `ingest_prechunked`

Ingest a document **already chunked and entity/relation-extracted by the
calling agent** (Copilot, opencode, Claude Desktop, …). Higher quality than
the regex fallback and avoids spinning up a separate LLM inside HydraMem.
See the [`hydramem-ingest-smart`](../.github/skills/hydramem-ingest-smart/SKILL.md)
skill for the agent-facing instructions.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `source` | string | required | Path or logical URI of the doc |
| `chunks` | list  | required | Pre-extracted payload (see schema below) |
| `doc_id` | string | "" | Stable id; auto-hashed from `source` when empty |
| `project` | string | "default" | |
| `session_id` | string | "" | Propagated to every persisted relation |

**Chunk schema**

```json
{
  "text":     "raw chunk text",
  "idx":      0,
  "entities": [{"name": "HydraMem", "type": "tool"}],
  "relations": [{"from": "HydraMem", "to": "LanceDB",
                 "type": "USES", "confidence": 0.9}]
}
```

**Behaviour**

- Embeds locally (`nomic-ai/nomic-embed-text-v1.5`, no network call).
- Persists chunks + entities + `MENTIONS` edges.
- Every relation passes through **SR-MKG (+ VoG when borderline)** — agent
  hallucinations are rejected, accepted edges are written with
  `verified=true` and `origin_tool="ingest_prechunked"`.
- Hard caps (configurable): 200 chunks, 1000 entities, 500 relations
  per call. Excess is dropped; counters reported.

**Returns**

```json
{
  "source": "docs/architecture.md",
  "doc_id": "ab12…",
  "project": "default",
  "chunks_added": 14,
  "entities_added": 23,
  "relations_proposed": 11,
  "relations_accepted": 8,
  "relations_rejected": 3,
  "truncated_chunks": 0,
  "truncated_entities": 0,
  "truncated_relations": 0,
  "verified": true
}
```

---

### 10b. `submit_session_extraction`

Graph-only knowledge contribution at session close: the agent submits the
entities and relations it discovered while working, without storing any
chunks. Same verifier filter as `ingest_prechunked`.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entities` | list | required | `[{"name": "...", "type": "..."}]` |
| `relations` | list | required | `[{"from": "...", "to": "...", "type": "...", "confidence": 0.x}]` |
| `session_id` | string | "" | |
| `project` | string | "default" | |

**Returns**

```json
{
  "project": "default",
  "session_id": "…",
  "entities_added": 6,
  "relations_proposed": 4,
  "relations_accepted": 3,
  "relations_rejected": 1,
  "truncated_relations": 0,
  "verified": true
}
```

---

## Graph Curation

### 11. `list_entities_tool`

List all entities in the knowledge graph for a project.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | "default" | |
| `limit` | int | 100 | |

---

### 12. `create_relation`

Manually add a verified relation edge.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `from_entity` | string | required | |
| `relation_type` | string | required | |
| `to_entity` | string | required | |
| `confidence` | float | 1.0 | |
| `project` | string | "default" | |

---

### 13. `delete_relation`

Remove a relation edge from the graph.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `from_entity` | string | required | |
| `relation_type` | string | required | |
| `to_entity` | string | required | |
| `project` | string | "default" | |

---

## Autonomous Learning

### 14. `run_night_gardener`

Trigger a full Night Gardener cycle (infer → verify → prune).

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | "default" | |

**Returns**

```json
{
  "project": "default",
  "candidates_proposed": 18,
  "relations_accepted": 11,
  "relations_rejected": 7,
  "sessions_considered": 10,
  "sessions_used": 6,
  "session_entries_considered": 42,
  "session_entries_used": 27,
  "session_entries_filtered_repeat_threshold": 15,
  "nodes_pruned": 2,
  "edges_pruned": 4,
  "last_run": "2026-05-07T03:00:12Z"
}
```

---

### 15. `get_garden_status_tool`

Return Night Gardener status and cumulative statistics.

**Returns**

```json
{
  "last_run": "2026-05-07T03:00:12Z",
  "total_runs": 42,
  "relations_proposed": 317,
  "relations_accepted": 189,
  "session_entries_filtered_repeat_threshold": 94,
  "is_running": false
}
```

---

### 16. `train_gnn_tool`

Run LightGNN training and spurious-edge detection. Returns a list of edges suggested for pruning.

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `project` | string | "default" | |
| `threshold` | float | 0.6 | Spuriousness score above which to suggest pruning |

**Returns**

```json
{
  "method": "heuristic",
  "suggested_edges": [["entity_id_a", "entity_id_b"]],
  "scores": { "entity_id_a|entity_id_b": 0.78 }
}
```

---

## Knowledge Graph

### 17. `query_entity_relations`

Temporal knowledge-graph query: return an entity's relationship facts, optionally filtered to those valid at a point in time — the qualifier-based equivalent of a bi-temporal `query_entity`. Backend-agnostic (reads the qualifier-carrying relation list, so it behaves identically on NetworkX, Grafeo and Ladybug).

**Parameters**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity_id` | string | required | Entity to query |
| `as_of` | string | "" | ISO-8601 date/datetime; only facts valid then (empty = all) |
| `direction` | string | "both" | `outgoing` \| `incoming` \| `both` |
| `project` | string | "default" | |

**Returns**

```json
{
  "entity": "e_1a2b",
  "as_of": "2026-03-01",
  "facts": [
    { "from": "e_1a2b", "to": "e_9f0c", "relation_type": "worked_on",
      "valid_from": "2026-01-01", "valid_to": "2026-06-01", "current": false }
  ],
  "count": 1
}
```

---

## Tool Quick Reference

| # | Tool | LLM call? | Typical latency |
|---|------|-----------|----------------|
| 1 | `priming_context_tool` | No | < 100 ms |
| 2 | `expand_context_tool` | No | < 50 ms |
| 3 | `hydra_search_tool` | Sometimes (VoG) | 100–2000 ms |
| 4 | `trace_path_tool` | No | < 30 ms |
| 5 | `get_entity_neighbors_tool` | No | < 20 ms |
| 6 | `get_full_document_tool` | No | < 10 ms |
| 7 | `verify_relation_tool` | Sometimes (VoG) | 50–1000 ms |
| 8 | `check_conflict_tool` | Yes | 500–3000 ms |
| 9 | `ingest_markdown` | No | 1–10 s |
| 10 | `ingest_directory_tool` | No | varies |
| 10a | `ingest_prechunked` | Sometimes (VoG on borderline relations) | < 500 ms (embeds + verify) |
| 10b | `submit_session_extraction` | Sometimes (VoG) | < 200 ms |
| 11 | `list_entities_tool` | No | < 20 ms |
| 12 | `create_relation` | No | < 10 ms |
| 13 | `delete_relation` | No | < 10 ms |
| 14 | `run_night_gardener` | Yes | 10–300 s |
| 15 | `get_garden_status_tool` | No | < 10 ms |
| 16 | `train_gnn_tool` | No | 1–30 s |
| 17 | `query_entity_relations` | No | < 20 ms |
| 18 | `remember` | No | < 500 ms (embeds + extracts) |
