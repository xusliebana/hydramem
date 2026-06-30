# HydraMem – Technical Overview

## Executive Summary

HydraMem is a local-first knowledge management and autonomous reasoning system designed to maximize evidence reuse, minimize token injection, and prevent hallucinations in LLM-based agents. It combines hybrid search (vector + graph), two-level verification (SR-MKG + VoG), and autonomous offline learning (Night Gardener) to build and refine knowledge graphs incrementally.

**Key metrics:**
- ~70 % token savings vs naive RAG (audit-able with `hydramem stats --raw`; see ``hydramem/telemetry/shadow.py`` for the baseline formula)
- Two-stage verification (topological SR-MKG + semantic VoG) for **relations**
- Vector-similarity prefilter + VoG for **chunks** inside `hydra_search` (the chunk path is *not* SR-MKG)
- Configurable repeat-based prioritisation for inference (default `min_repeat_count = 2`)
- 100 % local storage, zero data exfiltration (opt-in only)

See [docs/verification.md](docs/verification.md) for the honest contract of
each pipeline stage and [docs/benchmarks.md](docs/benchmarks.md) for the
reproducible experiment plan.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Server (FastMCP)                     │
│  18 tools exposed via streaming HTTP (agent-facing API)      │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    ┌────────┐  ┌────────────┐  ┌────────────┐
    │ Ingest │  │   Search   │  │  Gardener  │
    │Pipeline│  │  Service   │  │ (Offline)  │
    └────┬───┘  └─────┬──────┘  └──────┬─────┘
         │            │                │
         └────────────┼────────────────┘
                      ▼
         ┌────────────────────────────┐
         │    Storage Layer (DIP)     │
         ├────────────────────────────┤
         │ • LadybugDB (graph)        │
         │ • LanceDB (vectors)        │
         │ • SQLite (telemetry)       │
         │ • JSON (sessions, status)  │
         └────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Graph DB** | LadybugDB (Kuzu fork) | Entity/relation storage, multi-hop traversal |
| **Vector DB** | LanceDB | Dense embeddings, HNSW indexing, cosine similarity |
| **Embeddings** | nomic-embed-text-v1.5 | 768-d Matryoshka, truncated to 512-d (default) |
| **LLM (local)** | Ollama | Inference, verification, conflict detection |
| **LLM (external)** | OpenAI / Anthropic | Fallback or primary (configurable) |
| **MCP Framework** | FastMCP | Streaming HTTP protocol for agent integration |
| **Storage (local)** | SQLite | Metrics + telemetry (events table) |
| **Config** | YAML + env vars | Cascading: config.yml → env → hardcoded defaults |
| **Language** | Python 3.13 | Standard library + type hints, no async overhead |

---

## Core Modules

### 1. Ingestion Pipeline (`hydramem/ingest/`)

**Responsibility:** Load documents, extract entities, generate embeddings, persist to storage.

**Flow:**
```
Markdown files (recursive)
    ↓
Chunking (overlap)
    ↓
Entity extraction (regex/NER)
    ↓
Embedding (nomic-embed-text-v1.5)
    ↓
Persist:
  • LanceDB: chunks + embeddings
  • LadybugDB: entities, relations, schema
```

**Key class:** `IngestionService`
- `ingest_markdown(path)` – Single file
- `ingest_directory(path, recursive=True)` – Recursive indexing

**Design:** Lazy init of embedder; batch embedding if large corpus.

---

### 2. Search Service (`hydramem/search.py`)

**Responsibility:** Retrieve relevant context via vector + graph hybrid search.

**Core methods:**
1. **`priming_context(query, k=3)`** – Fast, no LLM
   - Top-k vector search
   - Entity term matching from query
   - Returns chunks + entity names for agent expansion

2. **`hydra_search(query, max_hops=3, top_k=10)`** – Full verification
   - Top-k vector search
   - BFS graph expansion (max_hops)
   - SR-MKG filtering (topological)
   - VoG verification (LLM, optional)
   - Returns verified context + metadata

3. **`expand_context(entity_ids, hops=2)`** – Multi-hop from known entities
   - Graph traversal
   - Chunk gathering
   - Context aggregation

4. **`trace_path(from_entity, to_entity)`** – Shortest path
   - NetworkX shortest_path
   - Returns path + length

**Design:** All methods return dicts (JSON-serializable); dependencies injected (store, embedder, pipeline).

---

### 3. Verification Pipeline (`hydramem/verification/`)

**Two-level architecture:**

#### Level 1: SR-MKG (Structured Relation – Mutual Knowledge Graph)
**Topological scoring, no LLM required.**

Score = 40% × Jaccard + 40% × base_confidence + 5% × type_boost − 30% × degree_penalty

```
if score >= 0.7:
    → ACCEPT (auto)
elif score < 0.3:
    → REJECT (auto)
else:
    → BORDERLINE (0.3–0.7) → go to Level 2 (VoG)
```

**File:** `hydramem/verification/srmkg.py`

#### Level 2: VoG (Verification over Groundings)
**LLM-based semantic verification against source text.**

```
Relation(from_entity, to_entity, relation_type, source_text, target_text)
    ↓
LLM prompt:
  "Is [source_text] consistent with [target_text]?
   Output: GROUNDED / PARTIAL / REJECTED
   Confidence: 0.0-1.0"
    ↓
Parse response, reduce confidence on PARTIAL
    ↓
Decision: accepted | rejected
```

**File:** `hydramem/verification/vog.py`

**Key feature:** Cap on VoG calls per cycle (default 30) to control LLM costs.

#### Combined Pipeline
**File:** `hydramem/verification/pipeline.py`

```python
pipeline = VerificationPipeline(config)
result = pipeline.verify(relation)
# → VerificationResult(accepted, score, level, vog_verdict)
```

---

### 4. Night Gardener (`hydramem/garden/`)

**Autonomous offline learning cycle (3 phases):**

#### Phase 1: Relation Inference
```
SessionRepository.last_n(20)
    ├─ Group by session_id
    ├─ Deduplicate by fingerprint (SHA256)
    └─ Collapse repeat_count + last_seen_at
    ↓
NightGardener._prepare_sessions(min_repeat_count)
    ├─ Filter entries: repeat_count >= threshold
    ├─ Sort by repeat DESC
    └─ Aggregate text
    ↓
RelationInferrer.infer()
    ├─ Send text to LLM (local or external)
    ├─ Parse regex: FROM_ENTITY –[TYPE]→ TO_ENTITY | CONFIDENCE: 0.X
    └─ Return [Relation, ...]
```

**Key insight:** Only processes evidence seen >= `min_repeat_count` times. Configurable bias toward repeated patterns.

#### Phase 2: Verification
```
for each candidate in candidates:
    result = pipeline.verify(candidate)
    if result.accepted:
        candidate.confidence = result.score
        store.add_relation(candidate)
```

#### Phase 3: Pruning
```
KnowledgePruner.prune(project)
    ├─ Remove isolated nodes
    ├─ Optional: LightGNN analysis
    └─ Return pruned_entities, pruned_edges
```

#### Metrics Tracking
```
StatusRepository() → ~/.hydramem/garden_status.json
{
  "last_run": "2026-05-07T03:00:12Z",
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

**File:** `hydramem/garden/gardener.py`

---

### 5. Session Repository (`hydramem/garden/repository.py`)

**Responsibility:** Persist, deduplicate, and aggregate query evidence.

**Data model:**
```json
{
  "id": "unique_id",
  "session_id": "from_agent",
  "project": "default",
  "created_at": "2026-05-07T10:00:00Z",
  "updated_at": "2026-05-07T10:05:00Z",
  "query": "original user query",
  "entries": [
    {
      "ts": "2026-05-07T10:00:00Z",
      "tool_name": "priming_context",
      "summary": "Query: ... Grounded context: ...",
      "repeat_count": 3,
      "fingerprint": "abc123def456",
      "last_seen_at": "2026-05-07T10:05:00Z"
    },
    ...
  ],
  "text": "aggregated text for Night Gardener inference"
}
```

**Deduplication logic:**
- Fingerprint = SHA256(summary)[:16]
- Same fingerprint → increment `repeat_count`, update `last_seen_at`
- Text aggregation: only last 12 entries, repeat counts shown as `x3`, `x2`, etc.

**Limits:**
- Max 50 entries per session
- Max 200 sessions global
- Sorted by updated_at, keeps newest

**File:** `hydramem/garden/repository.py`

---

## Query Flow (MCP)

### Scenario 1: Fast RAG (priming_context)

```
Agent: "What is HydraMem?"
    ↓
priming_context_tool(query="What is HydraMem?", k=3)
    ├─ Embed query
    ├─ Vector search (top-3)
    ├─ Entity term matching
    └─ Return: [chunk1, chunk2, chunk3] + entity_names
    ↓
[Agent reads response, may expand]
    ↓
Session persisted: {session_id, tool_name: "priming_context", query, context_snapshot}
```

**Latency:** ~100-200ms (embedding + vector search)

### Scenario 2: Full Hybrid (hydra_search)

```
Agent: "Connect HydraMem and LanceDB reasoning"
    ↓
hydra_search_tool(query, max_hops=3, top_k=10)
    ├─ Embed query
    ├─ Vector search (top-10)
    ├─ Extract entity terms
    ├─ BFS graph expansion (max 3 hops)
    ├─ SR-MKG filter (topological)
    ├─ VoG verify (if borderline, call LLM)
    └─ Return: verified_context + metadata (chunks_total, rejected_vector, rejected_vog, avg_vog_score)
    ↓
Session persisted: {session_id, tool_name: "hydra_search", query, final_context_snapshot}
```

**Latency:** 1-10s (depends on VoG LLM calls)

---

## Configuration

**File:** `config.yml` (or `~/.hydramem/config.yml`)

```yaml
llm:
  provider: auto                    # auto | ollama | openai | anthropic
  local:
    endpoint: http://localhost:11434
    model: gemma4:e4b
  external:
    provider: openai
    model: gpt-4o-mini
    api_key_env: HYDRAMEM_OPENAI_KEY

verification:
  srmkg_threshold_accept: 0.7       # auto-accept if score >= 0.7
  srmkg_threshold_reject: 0.3       # auto-reject if score < 0.3
  vog_max_candidates: 30            # max LLM calls per cycle
  vog_use_local_llm: true           # force local even if external is default

night_gardener:
  enabled: true
  schedule: "0 3 * * *"             # cron: 3 AM daily
  infer_with: local                 # local | external | auto
  verify_with: auto                 # local | external | auto
  min_repeat_count: 1               # only infer from entries seen >= N times
```

---

## CLI & Observability

### Commands

```bash
# Token savings + Night Gardener metrics (combined dashboard)
hydramem stats --last-7d
hydramem stats --days 30 --export md > report.md
hydramem stats --days 30 --export csv > metrics.csv

# Dedicated Garden view
hydramem garden-status
hydramem garden-status --json

# Telemetry management
hydramem telemetry --show
hydramem telemetry --wipe
hydramem telemetry --opt-in     # anonymous aggregates only
hydramem telemetry --opt-out
```

### Metrics Exposed

**`hydramem stats`:**
- Token savings ratio (%) and cost estimate
- Avg VoG score, rejections by SR-MKG and VoG
- Hallucinations blocked
- **Night Gardener section:**
  - Last run, total runs, entries filtered by repeat threshold
  - Nodes/edges pruned

**`hydramem garden-status`:**
- Full Night Gardener state (raw JSON or formatted table)

---

## Testing Strategy

### Unit Tests
- `tests/test_ingest.py` – Chunking, entity extraction, embedding
- `tests/test_search.py` – Hybrid search logic
- `tests/test_verify.py` – SR-MKG scoring, VoG parsing
- `tests/test_garden_repository.py` – Session deduplication, grouping
- `tests/test_gardener.py` – Relation inference, prioritization by repeat_count
- `tests/test_cli.py` – CLI output formatting
- `tests/test_server.py` – MCP tools (with mocked FastMCP)
- `tests/test_telemetry.py` – Metrics logging

### Design Patterns
- **Dependency Injection:** All services accept store, config, providers → testable
- **Single Responsibility:** Each module has one reason to change
- **Mocking:** Tests mock LLM, storage, sessions → no external calls

### Current Coverage
- 10+ test suites, 30+ assertions
- All core paths validated (happy + edge cases)

---

## Deployment & Runtime

### Standalone
```bash
cd /home/jesus/xus/hydroMEm
hydramem serve --transport http  # Starts MCP on 0.0.0.0:3000
```

### Via Systemd Timer (Night Gardener)
```ini
[Service]
ExecStart=uv run python -c "from hydramem.garden.gardener import NightGardener; NightGardener().run()"
```

### With Agent
1. Agent connects to MCP server (http://localhost:3000)
2. Agent calls tools (priming_context, hydra_search, etc.)
3. Sessions persisted automatically
4. Nightly Gardener processes them offline

---

## Design Decisions & Trade-offs

### ✅ Pros
1. **Local-first privacy:** All data stays on-disk unless explicitly shared
2. **Hybrid search:** Vector + graph combo catches more than either alone
3. **Two-phase verification:** SR-MKG is fast, VoG is accurate, split reduces LLM cost
4. **Configurable inference:** `min_repeat_count` bias → learn from robust patterns
5. **Modular architecture:** Easy to swap storage, LLM providers, or verification steps
6. **No async overhead:** Sync I/O for clarity (acceptable for ≤10s queries)

### ⚠️ Trade-offs
1. **Graph query latency:** BFS on large graphs (1000+ entities) may be slow → consider indexing
2. **VoG cost:** Uncontrolled borderline candidates can hit LLM cap → set reasonable thresholds
3. **Cold start:** First inference slower (embedding generation) → cache aggressively
4. **Memory footprint:** Full graph in RAM if using fallback NetworkX → test at scale
5. **No distributed state:** Single process → multi-machine requires external coordination

### 🎯 Mitigations
- LanceDB HNSW indexing for vector efficiency
- VoG cap + configurable thresholds
- Embedding caching (future)
- LanceDB scales to 10M+ vectors
- Stateless MCP allows load balancing

---

## Future Extensions

1. **Multi-language support:** Extend chunking, NER for non-English
2. **Distributed Night Gardener:** Queue-based coordinator for multi-instance
3. **Custom verification strategies:** Plug custom verifiers beyond SR-MKG/VoG
4. **Real-time session indexing:** Index new sessions before full cycle
5. **GraphRAG integration:** Leverage existing graph structures
6. **Streaming MCP responses:** Chunk output for very large contexts

---

## References

- **Graph DB:** LadybugDB (Kuzu fork)
- **Vector DB:** LanceDB documentation
- **MCP:** Model Context Protocol (Anthropic)
- **Verification:** SR-MKG inspired by knowledge graph completion; VoG by retrieval-augmented verification

---

**Questions for review:**

1. Does the two-level verification (SR-MKG + VoG) make sense given your LLM constraints?
2. Is `min_repeat_count` a useful lever for controlling inference data quality?
3. Should we add streaming support to MCP for large contexts?
4. Would you use distributed Night Gardener or is nightly batch sufficient?

**Prepared by:** Code generation system  
**Date:** 2026-05-07
