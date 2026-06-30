# HydraMem — Architecture for IR & Knowledge Management

## 1. System Identity

HydraMem is a **local-first hybrid retrieval and knowledge management system** designed to serve as persistent memory for LLM-based agents. It combines dense vector retrieval with structured knowledge graph traversal, applies a two-level verification pipeline to filter hallucinated or spurious evidence, and autonomously refines its knowledge base through an offline learning cycle (Night Gardener).

**Design thesis:** Naive top-k vector RAG injects too many tokens and too little structure. HydraMem reduces token injection by ~70% while improving factual grounding through graph-aware context assembly and multi-stage verification.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Agent Layer (MCP Clients)                                              │
│  OpenCode · Claude Desktop · Cursor · VS Code Copilot · Custom          │
└────────────────────────────┬────────────────────────────────────────────┘
                             │  Model Context Protocol (HTTP/stdio)
┌────────────────────────────▼────────────────────────────────────────────┐
│  MCP Server (FastMCP)                                                    │
│  18 tools · multi-provider LLM routing · per-call telemetry              │
└────────┬────────────────────────────┬──────────────────────┬────────────┘
         │                            │                      │
┌────────▼─────────────┐   ┌─────────▼──────────┐  ┌────────▼────────────┐
│  Retrieval Service   │   │  Ingestion Pipeline │  │  Night Gardener     │
│  (online, sync)      │   │  (online, batch)    │  │  (offline, async)   │
└────────┬─────────────┘   └─────────┬──────────┘  └────────┬────────────┘
         │                            │                      │
┌────────▼────────────────────────────▼──────────────────────▼────────────┐
│  Storage Layer (Dependency-Inverted)                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌────────────────┐  │
│  │ LadybugDB (Kuzu)    │  │ LanceDB             │  │ SQLite         │  │
│  │ Knowledge Graph      │  │ Vector Index (HNSW) │  │ Telemetry      │  │
│  └─────────────────────┘  └─────────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Retrieval Architecture

### 3.1 Retrieval Paths

| Path | Use Case | Latency | LLM Cost |
|------|----------|---------|----------|
| `priming_context` | Quick RAG before a turn | < 100 ms | Zero |
| `hydra_search` | Deep research with verification | 1–10 s | 0–30 VoG calls |
| `expand_context` | Neighbour expansion from known entities | < 200 ms | Zero |
| `trace_path` | Shortest graph path between two entities | < 50 ms | Zero |

### 3.2 Fast Path: `priming_context`

```
Query
  │
  ├─ Encode → nomic-embed-text-v1.5 (512-d, CPU, local)
  │
  ├─ Vector ANN → LanceDB HNSW, top-k chunks (cosine similarity)
  │
  ├─ Entity term extraction (regex + heuristics from query surface)
  │
  ├─ 1-hop graph expansion (neighbours of matched entities)
  │
  ├─ Deduplication + interleave ranking
  │
  └─ Return: chunks[] + entity_names[] + metadata
```

**No LLM call. No verification overhead.** Ideal for conversational priming where latency ≤ 200 ms is hard constraint.

### 3.3 Full Path: `hydra_search`

```
Query
  │
  ├─ Encode → dense embedding (384-dim)
  │
  ├─ Vector ANN → top-k candidate chunks
  │
  ├─ Entity extraction from query
  │
  ├─ Graph traversal (configurable strategy):
  │   ├─ BFS (breadth-first, max_hops)
  │   ├─ PPR (Personalized PageRank, HippoRAG-style)
  │   └─ Hybrid (Reciprocal Rank Fusion of vector + BFS + PPR)
  │
  ├─ Candidate relation pool assembly
  │
  ├─ SR-MKG scoring (topological, LLM-free)
  │   ├─ score ≥ 0.7 → accept
  │   ├─ score < 0.3 → reject
  │   └─ 0.3–0.7 → borderline → VoG
  │
  ├─ VoG verification (LLM step-by-step groundedness, capped)
  │
  ├─ Chunk prefilter (cosine threshold + VoG on borderlines)
  │
  └─ Return: verified_context + audit metadata
       {chunks_total, rejected_vector, rejected_vog, avg_vog_score}
```

### 3.4 Graph Traversal Strategies

| Strategy | Mechanism | Best For |
|----------|-----------|----------|
| `bfs` | Breadth-first from seed entities, bounded by `max_hops` | Small, dense graphs; precise local context |
| `ppr` | Personalized PageRank seeded at query entities | Large graphs; captures global relevance decay |
| `hybrid` | Reciprocal Rank Fusion of vector, BFS, and PPR scores | General-purpose; highest recall on multi-hop questions |

Selection per request via the `traversal` parameter. Default: `hybrid`.

---

## 4. Knowledge Graph Schema

```
Entity { id: UUID, name: str, type: str, project: str }
Relation { from_id, to_id, relation_type: str, confidence: float,
           source_doc_id: str, project: str }
Chunk { id: UUID, text: str, source: str, project: str, embedding_id: str }
Session { id, session_id, project, created_at, updated_at, text, entries[] }
```

- **Project namespacing**: all storage is keyed by `project` for multi-knowledge-base isolation on a single instance.
- **Graph backend**: LadybugDB (Kuzu fork) for persistent Cypher-queryable graphs. Falls back to NetworkX in-memory + JSON persistence when Kuzu is unavailable.
- **Vector backend**: LanceDB with HNSW indexing (scales to 10M+ vectors). Falls back to in-memory cosine similarity.

---

## 5. Two-Level Verification Pipeline

The verification pipeline exists to answer: **"Is this retrieved relation actually grounded in source evidence?"**

### 5.1 Layer 1 — SR-MKG (Topological Scorer)

**Zero LLM cost. Millisecond latency.**

```
score = w_base       × base_confidence
      + w_jaccard    × jaccard(common_neighbours, |N(a)| + |N(b)| − common)
      + w_type_boost × named_relation_bonus
      − penalty      × isolated_endpoint_flag
```

Defaults: `w_base = 0.4`, `w_jaccard = 0.4`, `w_type_boost = 0.05`, `penalty = 0.3`.

| Score Range | Decision |
|-------------|----------|
| ≥ 0.7 | **Auto-accept** — structurally well-connected |
| < 0.3 | **Auto-reject** — isolated or poorly supported |
| 0.3 – 0.7 | **Borderline** — escalate to VoG |

Weights are replaceable per-project via learned logistic calibration (`hydramem calibrate-srmkg`).

### 5.2 Layer 2 — VoG (Verification of Groundedness)

**LLM-based semantic verification. Applied only to borderline cases.**

```
Input:  Relation(from_entity, to_entity, type) + source_text + target_text
Prompt: "Is [source_text] consistent with [target_text] for relation [type]?"
Output: GROUNDED | PARTIAL | REJECTED + confidence: 0.0–1.0
```

Honest contract:
- No source/target text available → **auto-reject** (level: `vog_no_evidence`)
- LLM unavailable → **auto-reject** (level: `vog_unavailable`)
- Call cap per cycle: `vog_max_candidates` (default 30) — borderline beyond cap accepted at SR-MKG score

### 5.3 Pipeline Composition

```python
pipeline = VerificationPipeline(config)
result = pipeline.verify(relation)
# → VerificationResult(accepted: bool, score: float, level: str, vog_verdict: str | None)
```

New verification stages implement the `VerificationStep` Protocol and slot in without touching existing callers (Open/Closed Principle).

---

## 6. Ingestion Pipeline

```
Markdown sources (files or pre-chunked payloads)
    │
    ├─ Chunking (token-bounded with overlap, MarkdownChunker)
    │
    ├─ Entity extraction (regex + heuristic NER)
    │
    ├─ Embedding generation (nomic-embed-text-v1.5, batched)
    │
    └─ Persist:
         • LanceDB: chunks + dense embeddings
         • LadybugDB: entities, relations, chunk references
```

Two ingestion modes:
1. **`ingest_markdown`** — system performs chunking + extraction internally
2. **`ingest_prechunked`** — client (e.g., an AI agent via skill) supplies structured chunks + entities + relations directly for higher extraction quality

---

## 7. Night Gardener (Autonomous Knowledge Refinement)

The offline learning engine that distinguishes HydraMem from static RAG systems.

### 7.1 Three-Phase Cycle

```
Phase 1: Relation Inference
  │  LLM analyses aggregated Q&A session texts
  │  Proposes candidate edges: ENTITY_A –[type]→ ENTITY_B | confidence
  │  Filter: only sessions with entries seen ≥ min_repeat_count times
  │
Phase 2: Verification
  │  Every candidate passes SR-MKG + VoG (same pipeline as online)
  │  Accepted → persisted with confidence score
  │  Rejected → discarded, logged
  │
Phase 3: Pruning
     Rule-based: remove isolated nodes, zero-confidence edges
     LightGNN (optional): neural spurious-edge scoring
       ├─ PyTorch Geometric backend (if installed)
       ├─ DGL backend (if installed)
       └─ Heuristic fallback: betweenness centrality + degree thresholds
     Features: Laplacian Positional Encodings (spectral) + normalised degree
```

### 7.2 Session Evidence Model

```json
{
  "session_id": "uuid",
  "entries": [
    {
      "tool_name": "hydra_search",
      "summary": "Query: ... Grounded context: ...",
      "repeat_count": 3,
      "fingerprint": "sha256[:16]",
      "last_seen_at": "2026-05-20T10:05:00Z"
    }
  ]
}
```

- Deduplication: SHA-256 fingerprint → same content increments `repeat_count`
- Prioritisation: `min_repeat_count` threshold (default 2) biases inference toward robust, repeated patterns
- Limits: max 50 entries/session, max 200 sessions global

### 7.3 Observability

```json
{
  "last_run": "2026-05-20T03:00:12Z",
  "total_runs": 42,
  "relations_proposed": 317,
  "relations_accepted": 189,
  "relations_rejected": 128,
  "session_entries_filtered_repeat_threshold": 94,
  "nodes_pruned": 14,
  "edges_pruned": 23
}
```

---

## 8. Token Economics

| Metric | Naive top-k RAG | HydraMem |
|--------|-----------------|----------|
| Tokens injected (avg) | ~18,400 | ~2,140 |
| Savings | — | **~70%** |
| Context relevance | Low (no filtering) | High (verified, graph-ranked) |

Computed by shadow baseline in `hydramem/telemetry/shadow.py`: for every verified query, HydraMem also computes what a naive top-k would have injected and logs the delta.

---

## 9. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Graph DB | LadybugDB (Kuzu fork) | Cypher queries, multi-hop traversal, columnar storage |
| Vector DB | LanceDB | Serverless, HNSW, scales to 10M+, zero config |
| Embeddings | nomic-embed-text-v1.5 (512-d) | CPU-friendly, local, no API cost |
| LLM (local) | Ollama | Zero-cost inference, privacy, any GGUF model |
| LLM (external) | OpenAI / Anthropic / Mistral | Fallback or primary (configurable) |
| Protocol | FastMCP (Model Context Protocol) | Standard agent-tool interface |
| Telemetry | SQLite | Lightweight, local, per-event audit trail |
| Language | Python 3.13 | Sync I/O (acceptable for ≤10s retrieval paths) |

---

## 10. Module Dependency Hierarchy

```
hydramem/core/           ← Zero dependencies (types, config, logging, tokens)
hydramem/llm/            ← core/
hydramem/storage/        ← core/
hydramem/ingest/         ← core/, llm/, storage/
hydramem/verification/   ← core/, llm/
hydramem/garden/         ← core/, llm/, storage/, verification/
hydramem/search.py       ← core/, ingest/, storage/, verification/
hydramem/server.py       ← all of the above (composition root)
```

Strict **Dependency Inversion**: all modules depend on Protocols/interfaces, not concrete implementations. Storage backends, LLM providers, and verification steps are swappable without touching callers.

---

## 11. Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│  Single-process, single-tenant (per project namespace)       │
│                                                              │
│  MCP Server ─────── Online Retrieval + Ingestion             │
│       │                                                      │
│       └── Nightly ── Night Gardener (offline refinement)     │
│                                                              │
│  Storage: local filesystem (~/.hydramem/ or ./data)          │
└─────────────────────────────────────────────────────────────┘
```

- **Multi-tenant**: one process per tenant with isolated storage paths
- **Scaling**: stateless MCP allows load balancing; storage is per-instance
- **Federation**: HMAC-signed cross-instance sharing (optional)

---

## 12. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Two-level verification (topological + semantic) | SR-MKG eliminates 60–80% of candidates without LLM cost; VoG only verifies borderline |
| Repeat-count prioritisation for inference | Only learns from evidence observed multiple times → reduces noise, favours robust patterns |
| Graph + vector hybrid (not pure vector RAG) | Graph captures structural/relational knowledge that cosine similarity misses |
| Local-first, zero exfiltration default | Privacy; all embeddings, graphs, and telemetry on-disk unless explicitly shared |
| PPR traversal option (HippoRAG-style) | Global relevance propagation on large graphs without full BFS explosion |
| Calibratable SR-MKG weights | Per-project logistic regression on labelled data replaces heuristic thresholds |
| VoG cap per cycle | Predictable LLM cost; fail-safe against borderline explosion |
| LightGNN with Laplacian PE | Spectral positional features give real structural signal vs random init; optional — heuristic fallback always available |

---

## 13. Comparison with Standard RAG Architectures

| Dimension | Naive Vector RAG | GraphRAG (Microsoft) | HydraMem |
|-----------|-----------------|---------------------|----------|
| Retrieval | Top-k ANN | Community summaries | Hybrid (vector + BFS/PPR + graph expansion) |
| Verification | None | None | SR-MKG + VoG (two-level) |
| Knowledge evolution | Static index | Static index | Night Gardener (autonomous, cyclical) |
| Token efficiency | Low | Medium (community summaries) | High (~70% reduction) |
| Graph construction | N/A | LLM-driven upfront | Incremental (ingest + offline inference) |
| Privacy | Depends on embedding API | Cloud LLM required | 100% local by default |
| Multi-hop reasoning | Absent | Community-level | Entity-level BFS/PPR with verification |

---

## 14. Metrics & Observability

```bash
hydramem stats --last-7d          # Token savings + verification metrics
hydramem garden-status            # Night Gardener state
hydramem telemetry --show         # Raw event stream
```

Per-tool-call telemetry logged atomically:
- `tokens_injected`, `tokens_baseline` (shadow), `tokens_saved`
- `vog_calls`, `avg_vog_score`, `rejections_srmkg`, `rejections_vog`
- `latency_ms`, `traversal_strategy`, `chunks_returned`

---

## 15. Planned Benchmarks

| Dataset | Purpose |
|---------|---------|
| LongMemEval | Long-horizon multi-session memory |
| MuSiQue | Multi-hop QA with annotated reasoning chains |
| HotpotQA (distractor) | Classic multi-hop baseline |

Conditions: `naive_topk` vs `hydra_search_no_garden` vs `hydra_search_garden` (3 Night Gardener cycles).

Target metrics: Recall@5, factual accuracy (GPT-4o judge), hallucination rate, tokens injected, latency p50/p95.

---

## 16. End-to-End Query Flow

```
User: "How does the Night Gardener prune stale edges?"
  │
  ▼
[AI client] invokes hydramem-reason skill
  │
  ▼
[MCP] → hydra_search_tool(query=..., project="default")
  │
  ▼
[search.py]
  ├── embed query → [0.12, -0.34, …]  (384 dims, CPU)
  ├── LanceDB ANN → top-5 chunks
  ├── extract entities: ["Night Gardener", "LightGNN"]
  ├── graph expand → 2-hop neighbours → +3 chunks
  ├── SR-MKG score each relation
  └── VoG on 2 borderline relations → GROUNDED (0.89), GROUNDED (0.76)
  │
  ▼
[telemetry] log: tokens_injected=2140, tokens_baseline=18400, saved=88%
  │
  ▼
[AI client] receives verified context → generates grounded answer
```

---

## 17. Configuration Overview

```yaml
llm:
  provider: auto              # auto | local | ollama | openai | anthropic
  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434
  external:
    provider: openai
    model: gpt-4o-mini
    api_key_env: HYDRAMEM_OPENAI_KEY

embedding:
  model: nomic-ai/nomic-embed-text-v1.5
  dim: 512
  backend: auto               # auto | fastembed | sentence-transformers | stub

storage:
  ladybug_db: ./data/hydramem.graph
  lancedb: ./data/lancedb
  knowledge_dir: ./kms

verification:
  srmkg_threshold_accept: 0.7
  srmkg_threshold_reject: 0.3
  vog_max_candidates: 30
  vog_use_local_llm: true

night_gardener:
  enabled: true
  schedule: "0 3 * * *"
  infer_with: local
  verify_with: auto
  min_repeat_count: 2

server:
  host: 0.0.0.0
  port: 3000
```

Layered resolution: `config.yml` → environment variables → built-in defaults.

---

## 18. Future Extensions

| Extension | Impact |
|-----------|--------|
| Multi-language chunking + NER | Non-English corpus support |
| Distributed Night Gardener | Queue-based coordinator for multi-instance |
| Custom verification strategies | Plug neural verifiers beyond SR-MKG/VoG |
| Real-time session indexing | Index new sessions before full cycle |
| Streaming MCP responses | Chunk output for very large contexts |
| Learned SR-MKG weights | Per-project logistic calibration from labelled data |
| PPR with edge-type weighting | Typed PageRank for heterogeneous graphs |
