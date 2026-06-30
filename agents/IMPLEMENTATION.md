# Implementation Notes (agent-facing)

The mental model an agent needs *before* touching code. Pairs with
[docs/internal/CODEMAP.md](../docs/internal/CODEMAP.md) (where things live) and
[TECHNICAL_OVERVIEW.md](../TECHNICAL_OVERVIEW.md) (deep dive).

## The one rule that shapes everything: dependency injection

Storage, LLM, and embedder are **constructor-injected** through abstract base
classes (`hydramem/storage/`, `hydramem/llm/`, the embedder in `hydramem/ingest/`).
Services (`search`, `ingest`, `garden`, `verification`) never instantiate a
concrete backend directly — a `factory` wires them from config. Consequence:
write tests with in-memory/fake backends; never monkeypatch globals.

## Main flows

### Ingestion (`hydramem/ingest/`)
`Markdown → chunk (overlap) → extract entities (regex/NER) → embed
(nomic-embed-text-v1.5, ONNX) → persist`. Persist = chunks+embeddings to the vector
store and entities + `MENTIONS` edges to the graph. `IngestionService` exposes
`ingest_markdown(path)` and `ingest_directory(path, recursive=True)`. Agents can
bypass extraction via the BYO-extraction tools (ADR-0005); HydraMem still embeds,
stores, and **verifies**.

### Retrieval (`hydramem/search.py`)
- **Fast path** `priming_context(query, k=3)` — vector ANN + entity term match +
  1-hop; **no LLM**.
- **Full path** `hydra_search(query, max_hops=3, top_k=10)` — vector ANN + BFS
  expansion + **SR-MKG** (relations) + **VoG** (optional) + a **vector-similarity**
  prefilter for chunks. The chunk path is *not* SR-MKG (common confusion).
- `expand_context(entity_ids, hops=2)` and `trace_path(from, to)` for graph ops.
All methods return JSON-serializable `dict`s.

### Verification (`hydramem/verification/`)
Stage 1 SR-MKG (pure-Python topological scorer, heuristic weights, no LLM) →
Stage 2 VoG (LLM groundedness) for borderline candidates. Honest contract: emit
**zero** relations without real evidence. See ADR-0003.

### Night Gardener (`hydramem/garden/`)
Offline `infer → verify → prune`. Reads deduplicated session snapshots
(`~/.hydramem/sessions.json`, grouped by `session_id`, deduped by context
fingerprint with `repeat_count`/`last_seen_at`), gated by
`night_gardener.min_repeat_count` (default 2). Optional LightGNN pruning
(`hydramem/gnn_prune.py`) auto-skips above `HYDRAMEM_GNN_MAX_NODES` (5000).

### MCP server (`hydramem/server.py`)
FastMCP, **18 tools**, single-tenant, per-`project` namespacing, per-call
telemetry. Session persistence is wired through the retrieval/verify tools
(`priming_context`, `hydra_search`, `expand_context`, `trace_path`,
`verify_relation`, `check_conflict`).

### Telemetry (`hydramem/telemetry/`)
Local SQLite events table; `shadow.py` computes the **naive-RAG baseline** that
produces the headline "tokens saved" number — change it carefully, it is
user-facing and must stay honest.

## Caveats / gotchas

- **3.11 has no Grafeo** → persistent NetworkX fallback. Keep it working.
- **Backends are pluggable** via `HYDRAMEM_GRAPH_BACKEND` / `HYDRAMEM_VECTOR_BACKEND`.
- **Public contract**: tool names/params/return keys and the console entry points
  are frozen without deprecation — see [docs/internal/CONTRACTS/PUBLIC_API.md](../docs/internal/CONTRACTS/PUBLIC_API.md).
- Tests are async-aware (`asyncio_mode=auto`); integration tests live in
  `tests/integration/`.
