# Architecture

HydraMem is built around four layers that work together to provide accurate, low-hallucination context to AI agents.

---

## System diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1: AI Clients                                                 │
│  OpenCode · Claude Desktop · Cursor · VS Code Copilot · Custom      │
│  Invokes Agent Skills (.github/skills/hydramem-*)                   │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ HTTP / MCP (Model Context Protocol)
┌─────────────────────────────▼────────────────────────────────────────┐
│  Layer 2: MCP Server  (hydramem/server.py)                              │
│  FastMCP · 18 tools · multi-provider LLM · telemetry logging        │
└──────────────┬──────────────────────────┬────────────────────────────┘
               │                          │
┌──────────────▼──────────────┐  ┌────────▼───────────────────────────┐
│  Layer 3a: Retrieval        │  │  Layer 3b: Autonomous Learning      │
│  hydramem/search.py            │  │  hydramem/garden/gardener.py        │
│  · priming_context (fast)   │  │  · Phase 1: Relation Inference     │
│  · hydra_search (full)      │  │  · Phase 2: SR-MKG + VoG verify   │
│  · expand_context           │  │  · Phase 3: Graph Pruning          │
│  · trace_path               │  │  hydramem/gnn_prune.py (LightGNN)    │
│                             │  │                                    │
│  hydramem/verification/        │  │                                    │
│  · SR-MKG scoring           │  │                                    │
│  · VoG LLM verification     │  │                                    │
└──────────────┬──────────────┘  └────────┬───────────────────────────┘
               │                          │
┌──────────────▼──────────────────────────▼───────────────────────────┐
│  Layer 4: Storage  (hydramem/storage/)                                  │
│  ┌──────────────────────────────┐  ┌────────────────────────────┐   │
│  │  LadybugDB / Kuzu            │  │  LanceDB                   │   │
│  │  Graph: entities, relations, │  │  Vector index: embeddings, │   │
│  │  chunks, sessions            │  │  ANN search (HNSW)         │   │
│  │  Cypher queries              │  │  In-memory fallback        │   │
│  └──────────────────────────────┘  └────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Telemetry: ~/.hydramem/metrics.db (SQLite)                  │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1 – AI Clients

HydraMem integrates with any MCP-compatible AI client. The five bundled **Agent Skills** (`.github/skills/`) provide structured workflows for the most common operations:

| Skill | Triggered when agent needs to… |
|-------|-------------------------------|
| `hydramem-query` | Answer a factual question from the knowledge base |
| `hydramem-reason` | Multi-hop causal reasoning over the graph |
| `hydramem-ingest` | Add new documents to the knowledge base |
| `hydramem-link` | Curate relations manually |
| `hydramem-garden` | Run the Night Gardener maintenance cycle |

Skills are YAML-frontmatter Markdown files that describe tool sequences to the AI client. They work with any client that supports MCP + agent skills (OpenCode, Cursor, Claude Desktop with plugins).

---

## Layer 2 – MCP Server

`hydramem/server.py` runs a [FastMCP](https://github.com/jlowin/fastmcp) HTTP server exposing 18 tools.

Key design decisions:
- **Every tool logs telemetry** atomically before returning — no silent failures.
- **Project namespacing** — all storage is keyed by `project` to support multiple independent knowledge bases on one instance.
- **Session IDs** — each server boot gets a UUID; tools accept an optional `session_id` override for grouping agent interactions.
- **Multi-provider LLM** — resolved at startup from `config.yml`; each tool inherits the global preset unless overridden.

---

## Layer 3a – Retrieval Pipeline

### `priming_context` (fast path)

Used when the agent needs quick context before a conversational turn.

```
Query → embed (nomic-embed-text-v1.5)
      → LanceDB ANN top-k chunks
      → entity extraction from query (regex + heuristics)
      → graph neighbour expansion (1 hop)
      → deduplicate + rank
      → return context string + chunk list
```

Average latency: **< 100 ms** on a modern laptop (no LLM call required).

### `hydra_search` (full path)

Used for deep research questions where accuracy matters more than speed.

```
Query → embed
      → LanceDB ANN top-k
      → entity expansion (BFS / PPR / hybrid)
      → candidate relation retrieval
      → SR-MKG scoring (topological, no LLM; optionally calibrated)
      → borderline relations → VoG (LLM step-by-step)
      → ranked, verified context
```

The graph-walk strategy is selectable per request via the `traversal`
parameter (`bfs` | `ppr` | `hybrid`). `ppr` runs Personalized PageRank
seeded at query entities (HippoRAG-style); `hybrid` fuses the vector,
BFS and PPR rankings via Reciprocal Rank Fusion. See
[configuration.md#search-traversal](configuration.md#search-traversal).

### `trace_path`

Shortest-path query between two entity IDs using graph BFS/Dijkstra. Returns the chain of relations connecting them.

---

## Layer 3b – Two-Level Verification

### SR-MKG (Scalable Relation Mining with Knowledge Graphs)

A fast, **LLM-free** topological scorer. Computes a confidence score for a relation based on:
- Jaccard coefficient of common graph neighbours
- Degree penalty for isolated/orphan nodes
- Named-relation type boost

Score ≥ 0.7 → **auto-accept**  
Score < 0.3 → **auto-reject**  
0.3 – 0.7   → forwarded to **VoG**

The four component weights can be replaced per-project by a learned
logistic calibration (`hydramem calibrate-srmkg`); when a weights file
exists at `~/.hydramem/projects/<p>/srmkg_weights.json` the scorer loads
it transparently. See
[verification.md#per-project-calibration](verification.md#per-project-calibration).

### VoG (Verification of Groundedness)

An LLM step-by-step check. Given the proposed relation and the two source text fragments:

```
Proposed: "HydraMem" –[uses]→ "LanceDB"

Fragment A: "HydraMem stores embeddings in LanceDB…"
Fragment B: "LanceDB provides serverless vector search…"

→ GROUNDED  CONFIDENCE: 0.94
```

VoG is only called for borderline relations (`vog_max_candidates` cap prevents runaway API costs).

---

## Layer 3c – Night Gardener

See [night-gardener.md](night-gardener.md) for full details.

Three phases:
1. **Inference** — LLM analyses stored Q&A sessions and proposes new graph edges.
2. **Verification** — every candidate passes SR-MKG + VoG.
3. **Pruning** — isolated nodes and spurious edges are removed (rule-based + optional LightGNN).

### LightGNN Pruning

A lightweight Graph Neural Network that learns to distinguish genuine knowledge edges from co-occurrence noise.

| Backend | Condition |
|---------|-----------|
| PyTorch Geometric | `pip install torch torch_geometric` |
| DGL | `pip install torch dgl` |
| Heuristic (default) | No PyTorch — uses betweenness centrality + degree thresholds |

The heuristic approximates GNN results acceptably for most corpora.

When the PyG backend is available, node features default to **Laplacian
Positional Encodings** (`hydramem/garden/spectral.py`) concatenated with
normalised degree, instead of the previous random low-rank features. LPE
gives the GNN a real spectral signal at near-zero compute cost. Toggle
via `gnn.use_laplacian_pe` (default on) and `gnn.lpe_k` (default 32).

---

## Layer 4 – Storage

### LadybugDB / Kuzu (graph)

The graph store (`hydramem/storage/factory.py`) wraps LadybugDB (a fork of Kuzu). Schema:

```
Entity { id, name, type, project }
Relation { from_id, to_id, relation_type, confidence, source_doc_id, project }
Chunk { id, text, source, project, embedding_id }
Session { id, session_id, project, created_at, updated_at, text, entries[] }
```

Fallback: if LadybugDB is unavailable, the store switches to a **NetworkX in-memory graph** with JSON persistence.

### LanceDB (vectors)

Stores chunk embeddings as a LanceDB table with HNSW indexing. Queries return the top-k nearest chunks by cosine similarity.

The embedding model (`nomic-ai/nomic-embed-text-v1.5`, truncated to 512-d) runs 100 % locally on CPU via fastembed or `sentence-transformers`.

### Telemetry (SQLite)

`~/.hydramem/metrics.db` stores a `events` table with per-tool-call metrics. See [telemetry.md](telemetry.md).

---

## Module Map

The codebase is organised around **SOLID principles** and a strict **dependency hierarchy** — arrows show allowed import direction (lower layers never import from higher ones).

```
hydramem/core/          ← zero dependencies (types, config, logging, tokens)
hydramem/llm/           ← depends on core/
hydramem/storage/       ← depends on core/
hydramem/ingest/        ← depends on core/, llm/, storage/
hydramem/verification/  ← depends on core/, llm/
hydramem/garden/        ← depends on core/, llm/, storage/, verification/
hydramem/search.py      ← depends on core/, ingest/, storage/, verification/
hydramem/server.py      ← depends on all of the above
```

### Sub-package detail

#### `hydramem/core/` — Domain primitives (SRP)
| Module | Responsibility |
|--------|---------------|
| `types.py` | Pure dataclasses: `Chunk`, `Entity`, `Relation` |
| `config.py` | `Config` class + YAML/env resolution |
| `logging.py` | `get_logger()` factory |
| `tokens.py` | `count_tokens()` via tiktoken |

#### `hydramem/llm/` — LLM provider abstraction (OCP + DIP)
| Module | Responsibility |
|--------|---------------|
| `base.py` | `LLMProvider` Protocol — the DIP boundary |
| `ollama.py` | `OllamaProvider` — local inference |
| `openai.py` | `OpenAIProvider` — OpenAI API |
| `anthropic.py` | `AnthropicProvider` — Anthropic Claude API |
| `factory.py` | `create_provider()`, `call_llm()` — registry + singleton |

Adding a new LLM backend: create one file + add one entry to the registry. **Zero other files change.**

#### `hydramem/storage/` — Repository pattern (OCP + DIP + ISP)
| Module | Responsibility |
|--------|---------------|
| `base.py` | `GraphRepository` + `VectorRepository` Protocols |
| `graph/networkx_repo.py` | NetworkX in-memory graph (always available) |
| `graph/ladybug_repo.py` | LadybugDB / Kuzu persistent graph |
| `vector/lancedb_repo.py` | LanceDB persistent vector index |
| `vector/memory_repo.py` | In-memory cosine-similarity fallback |
| `factory.py` | `KnowledgeStore` facade + `create_store()` / `get_store()` |

`KnowledgeStore` composes one `GraphRepository` and one `VectorRepository`. Callers depend only on `KnowledgeStore` — never on concrete backends (DIP + ISP).

#### `hydramem/ingest/` — Ingestion pipeline (SRP)
| Module | Responsibility |
|--------|---------------|
| `chunker.py` | `MarkdownChunker` — split text into token-sized pieces |
| `embedder.py` | `EmbeddingService` — generate dense vectors |
| `extractor.py` | `EntityExtractor` — heuristic named-entity recognition |
| `pipeline.py` | `IngestionPipeline` — orchestrate the above (only coordination, no logic) |

#### `hydramem/verification/` — Two-level verification (OCP + LSP)
| Module | Responsibility |
|--------|---------------|
| `base.py` | `VerificationStep` Protocol + `VerificationResult` dataclass |
| `srmkg.py` | `SRMKGScorer` — topological confidence, no LLM |
| `vog.py` | `VoGVerifier` — LLM groundedness check, injected `LLMProvider` |
| `pipeline.py` | `VerificationPipeline` — SR-MKG → VoG with VoG cap |

New verification stages (e.g. neural) implement `VerificationStep` and slot in without touching callers (OCP).

#### `hydramem/garden/` — Night Gardener (SRP per phase)
| Module | Responsibility |
|--------|---------------|
| `repository.py` | `SessionRepository`, `StatusRepository` — JSON persistence only |
| `inferrer.py` | `RelationInferrer` — Phase 1: propose candidates via LLM |
| `pruner.py` | `KnowledgePruner` — Phase 3: remove stale/isolated elements |
| `gardener.py` | `NightGardener` — orchestrate phases 1→2→3, inject all deps |

---

## Data flow: end-to-end query

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
