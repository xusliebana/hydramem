<p align="center">
  <img src="docs/assets/hydramem-logo.svg" alt="HydraMem" width="200">
</p>

<h1 align="center">HydraMem</h1>

<p align="center">
  <strong>Autonomous, private Knowledge Management System with hybrid graph-vector search</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/pkg-uv-blueviolet.svg" alt="uv"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/protocol-MCP-orange.svg" alt="MCP"></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="docs/">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

---

## What is HydraMem?

HydraMem is a **100 % local, privacy-first** memory layer for AI coding
agents (OpenCode, Claude Desktop, Cursor, ...). It builds a hybrid
**graph + vector** knowledge base from your Markdown documents, runs every
candidate relation through a two-stage **SR-MKG topological + VoG groundedness**
check, and quietly refines the graph overnight via the **Night Gardener** —
all on your machine, with zero cloud dependency by default.

> **Honest positioning.** HydraMem is not the first memory system, the first
> graph-RAG, or the first hallucination filter. What it offers is an
> **opinionated local-first integration** of those patterns, with metrics you
> can audit (`hydramem stats --raw`) and a code base small enough to read in
> an afternoon (~5 k LOC). See [docs/verification.md](docs/verification.md)
> for what each component actually does — and does not — do.

```
$ hydramem stats --last-7d

╭─────────────────────────────────────────────────╮
│  HydraMem Stats – last 7 days                   │
├──────────────────────────┬──────────────────────┤
│ Tool calls               │                 142  │
│ Tokens (naive RAG)       │               1.4M   │
│ Tokens injected          │               312K   │
│ Tokens saved             │    1.09M (77.8%)     │
│ Cost saved (est.)        │             $5.45    │
│ Avg VoG score            │              0.887   │
│ Rejected by SR-MKG       │                 89   │
│ Rejected by VoG          │                 12   │
│ Cross-project hits       │                 24   │
│ Hallucinations blocked   │                  5   │
╰──────────────────────────┴──────────────────────╯
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Hybrid search** | LanceDB vector search + LadybugDB/Kuzu graph traversal in a single query, fused through a verification pipeline |
| **Two-stage verification** | SR-MKG (topological scorer over relations) + VoG (LLM groundedness check). The chunk-level prefilter inside `hydra_search` is *vector-similarity*, see [docs/verification.md](docs/verification.md) |
| **Night Gardener** | Autonomous offline relation inference, verification, and pruning. Honest contract: emits **zero** relations when there is no real evidence |
| **LightGNN pruning** | Optional GNN-based spurious-edge detection (heuristic fallback). Auto-skips on graphs > `HYDRAMEM_GNN_MAX_NODES` (default 5 000) |
| **MCP server** | 18 tools via FastMCP, single-tenant by design — see [hydramem/server.py](hydramem/server.py) |
| **Multi-provider LLM** | Local Ollama, OpenAI, Anthropic — configurable per subsystem via `config.yml` |
| **Auditable telemetry** | Local SQLite metrics with `hydramem stats` dashboard and `--raw` mode for per-event audit. Nothing leaves your machine |
| **Lightweight by default** | Auto-detects `fastembed` (ONNX, ~80 MB) before falling back to `sentence-transformers` |
| **Dogfooding** | `uv run python scripts/dogfood.py` |

---

## Quickstart

### Prerequisites

- **Python ≥ 3.11** (3.12 recommended — enables the native Grafeo graph backend)
- **[uv](https://github.com/astral-sh/uv)** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **[Ollama](https://ollama.com/)** *(optional, for a local LLM)* — `curl -fsSL https://ollama.com/install.sh | sh && ollama pull gemma4:e4b`

### Install

The fastest path — install the `hydramem` CLI into an isolated environment with
uv (or [pipx](https://pipx.pypa.io/)), then scaffold a workspace:

```bash
# uv (recommended)
uv tool install git+https://github.com/xusliebana/hydramem
# …or: pipx install git+https://github.com/xusliebana/hydramem

hydramem init ~/my-memory     # writes config.yml, kms/, data/ + an MCP snippet
cd ~/my-memory
```

<details>
<summary><strong>From source (for development)</strong></summary>

```bash
git clone https://github.com/xusliebana/hydramem
cd hydramem
cp config.yml.example config.yml
cp .env.example .env

uv sync                                   # lightweight: ~80 MB ONNX embedder, no torch
# uv sync --extra sentence-transformers   # full stack (~2 GB, includes torch)

uv run hydramem --help                    # prefix any command with `uv run`
```
</details>

### Ingest, search, serve

```bash
# Put Markdown files in ./kms, then ingest them
hydramem ingest ./kms

# Ask a question straight from the terminal
hydramem search "What does my documentation say about the Night Gardener?"

# Start the MCP server (stdio for MCP clients, or --transport http)
hydramem serve --transport stdio
```

### Connect your AI client

<details>
<summary><strong>OpenCode (with Ollama — local)</strong></summary>

```json
// ~/.config/opencode/config.json
{
  "provider": {
    "ollama": {
      "model": "gemma4:e4b"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```
</details>

<details>
<summary><strong>OpenCode (with Claude / Anthropic)</strong></summary>

```json
// ~/.config/opencode/config.json
{
  "provider": {
    "anthropic": {
      "api_key_env": "ANTHROPIC_API_KEY",
      "model": "claude-sonnet-4-20250514"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

Then in `config.yml`:
```yaml
llm:
  provider: anthropic
  external:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-20250514
```
</details>

<details>
<summary><strong>Claude Desktop</strong></summary>

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "hydramem": {
      "command": "hydramem",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

*(Prefer HTTP? Run `hydramem serve --transport http` and use `{ "type": "http", "url": "http://localhost:3000/mcp" }`.)*
</details>

<details>
<summary><strong>Cursor / VS Code Copilot</strong></summary>

Add an MCP server entry pointing to `http://localhost:3000/mcp` in your editor settings.
</details>

### Ingest your documents

```bash
# Put your Markdown files in ./kms, then ingest the directory
cp ~/notes/*.md kms/
hydramem ingest ./kms --project myproject
```

### View stats

```bash
uv run hydramem stats --last-7d
uv run hydramem stats --days 30 --export md > report.md
uv run hydramem stats --days 30 --raw       # per-event baseline + injected tokens (audit mode)
```

## How does it compare?

| Project           | Local-first | Graph + vector | Verifies relations | Autonomous offline learning | MCP-native | License    |
|-------------------|:-----------:|:--------------:|:------------------:|:---------------------------:|:----------:|------------|
| **HydraMem**      | ✅          | ✅              | ✅ (SR-MKG + VoG)   | ✅ (Night Gardener)         | ✅          | MIT        |
| Mem0              | partial     | optional       | ❌                  | partial                     | community  | Apache-2.0 |
| Letta / MemGPT    | ✅          | ❌              | ❌                  | ❌                          | ❌          | Apache-2.0 |
| Cognee            | ✅          | ✅              | partial             | ✅ (cognify)                | community  | Apache-2.0 |
| Microsoft GraphRAG| ✅          | ✅              | indirect            | ❌ (batch only)             | ❌          | MIT        |
| HippoRAG / HippoRAG 2 | research | ✅            | ❌                  | ✅                          | ❌          | Apache-2.0 |

We will replace the qualitative checkmarks with quantitative numbers as soon
as the experiment in [docs/benchmarks.md](docs/benchmarks.md) ships.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1: AI Client (OpenCode / Claude Desktop / Cursor)     │
│           Invokes Skills (.github/skills/hydramem-*)         │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP/MCP
┌──────────────────────▼───────────────────────────────────────┐
│  Layer 2: HydraMem MCP Server (FastMCP)  hydramem/server.py     │
│           18 tools • telemetry logging • multi-provider LLM  │
└──────────┬───────────────────────┬───────────────────────────┘
           │                       │
┌──────────▼────────────┐  ┌───────▼────────────────────────────┐
│  Layer 3a:            │  │  Layer 3b:                         │
│  Verification         │  │  Night Gardener                    │
│  hydramem/verification/  │  │  hydramem/garden/gardener.py        │
│  SR-MKG + VoG         │  │  Infer → Verify → Prune           │
│                       │  │  hydramem/gnn_prune.py (LightGNN)    │
└──────────┬────────────┘  └───────┬────────────────────────────┘
           │                       │
┌──────────▼───────────────────────▼────────────────────────────┐
│  Layer 4: Storage                                             │
│  ┌──────────────────────┐  ┌────────────────────────────────┐ │
│  │ LadybugDB / Kuzu     │  │ LanceDB (vector cache)         │ │
│  │ Graph: entities,     │  │ Embeddings, ANN search         │ │
│  │ relations, chunks    │  │ (in-memory fallback)           │ │
│  └──────────────────────┘  └────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### MCP Tools (18)

| # | Tool | Description |
|---|------|-------------|
| 1 | `priming_context_tool` | Top-k chunks + graph neighbours for quick context |
| 2 | `expand_context_tool` | Expand from entity IDs via graph traversal |
| 3 | `hydra_search_tool` | Full hybrid search + SR-MKG + VoG pipeline |
| 4 | `trace_path_tool` | Shortest path between two entities |
| 5 | `verify_relation_tool` | Two-level relation verification |
| 6 | `ingest_markdown` | Ingest a single Markdown file |
| 7 | `ingest_directory_tool` | Ingest all .md files in a directory |
| 8 | `list_entities_tool` | List all graph entities |
| 9 | `create_relation` | Manually add a verified relation |
| 10 | `delete_relation` | Remove a relation edge |
| 11 | `get_entity_neighbors_tool` | N-hop neighbourhood of an entity (optional `as_of` temporal filter) |
| 12 | `run_night_gardener` | Full autonomous refinement cycle |
| 13 | `get_garden_status_tool` | Night Gardener status and cumulative stats |
| 14 | `train_gnn_tool` | LightGNN spurious-edge detection + pruning |
| 15 | `check_conflict_tool` | Detect contradictions between two passages |
| 16 | `get_full_document_tool` | Retrieve full document text by doc_id |
| 17 | `query_entity_relations` | Temporal KG query: an entity's relations valid at `as_of` |
| 18 | `remember` | Persist a free-text note/fact mid-chat (verified → graph knowledge) |

### Agent Skills (6)

| Skill | Use case |
|-------|----------|
| `hydramem-query` | Direct factual lookup with source citations |
| `hydramem-reason` | Multi-hop causal reasoning over the knowledge graph |
| `hydramem-ingest` | Add new documents to the knowledge base |
| `hydramem-ingest-smart` | Agent-side chunking + entity/relation extraction for higher-quality ingestion |
| `hydramem-link` | Manual graph curation — create, verify, delete relations |
| `hydramem-garden` | Run the Night Gardener maintenance cycle |

---

## Configuration

HydraMem uses a layered configuration system: **`config.yml`** → **environment variables** → **defaults**.

```bash
cp config.yml.example config.yml
```

### Multi-provider LLM

```yaml
# config.yml
llm:
  provider: auto  # auto | local | ollama | openai | anthropic

  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434

  external:
    provider: openai
    api_key_env: HYDRAMEM_OPENAI_KEY
    model: gpt-4o-mini
```

| Provider | Requirements | Cost |
|----------|-------------|------|
| `ollama` / `local` | Ollama running locally | Free |
| `openai` | `HYDRAMEM_OPENAI_KEY` env var | Per-token |
| `anthropic` | `HYDRAMEM_ANTHROPIC_KEY` or `ANTHROPIC_API_KEY` env var | Per-token |
| `auto` | Tries Ollama first, falls back to external if API key found | Depends |

### Per-subsystem LLM routing

The Night Gardener can use a different LLM than queries, saving API costs:

```yaml
night_gardener:
  infer_with: local       # always infer locally (free)
  verify_with: auto       # use local if available, else external
  min_repeat_count: 2     # prefer evidence snapshots seen at least twice

verification:
  vog_use_local_llm: true # force VoG verification on local even if external is the default
```

### Verification thresholds

```yaml
verification:
  srmkg_threshold_accept: 0.7   # score ≥ 0.7 → auto-accept
  srmkg_threshold_reject: 0.3   # score < 0.3 → auto-reject
  vog_max_candidates: 30        # limit VoG calls for cost control
```

See [docs/configuration.md](docs/configuration.md) for the full reference.

---

## Night Gardener

The Night Gardener is HydraMem's autonomous offline learning engine. It runs in three phases:

1. **Relation Inference** — the LLM analyses locally stored query sessions and proposes new edges between entities that co-occur in successful reasoning chains. HydraMem currently stores the user query plus the grounded context returned by MCP search tools; it does **not** capture the client's private chain-of-thought. Repeated evidence snapshots can be prioritized with `night_gardener.min_repeat_count` (default `2`).

   *Honesty contract:* if no real session text is available, the inferrer returns an empty list. It no longer invents `co_mentioned` placeholders (v0.1.x bug).

2. **Two-level Verification**:
   - **SR-MKG** (score ≥ 0.7 → accept, < 0.3 → reject, 0.3–0.7 → VoG)
   - **VoG** — LLM verifies consistency of borderline relations against source texts. Empty LLM responses or missing evidence now reject (was: random optimistic score).

3. **Pruning** — rule-based removal of isolated entities (now actually deleted via `delete_entity`) plus optional LightGNN spurious-edge detection.

```bash
# Run manually
uv run python -c "from hydramem.garden.gardener import NightGardener; print(NightGardener().run())"

# Or via MCP tool (from your AI client):
# "Run the Night Gardener on my default project"
```

See [docs/night-gardener.md](docs/night-gardener.md) for details.

---

## Telemetry

All metrics are stored **locally** in `~/.hydramem/metrics.db` (SQLite). Nothing is sent anywhere unless you explicitly opt in.

```bash
hydramem stats --last-7d              # Rich table
hydramem stats --days 30 --export md  # Markdown export
hydramem stats --days 30 --export csv # CSV export
hydramem stats --days 30 --raw        # Per-event rows (audit mode)
hydramem garden-status                # Night Gardener cumulative status
hydramem garden-status --json         # Raw Night Gardener status JSON
hydramem telemetry --show             # Raw JSON
hydramem telemetry --wipe             # Delete metrics.db
hydramem telemetry --opt-in           # Anonymous aggregates (totals only)
hydramem telemetry --opt-out          # Disable sharing
```

`hydramem stats` includes both period-based telemetry and a compact cumulative Night Gardener section. Use `hydramem garden-status` for the Garden view on its own and `--raw` to audit the savings calculation event-by-event.

The "naive RAG" baseline used to compute savings is documented in
[hydramem/telemetry/shadow.py](hydramem/telemetry/shadow.py) and is intentionally
conservative — reported savings should be read as a **lower bound**.

See [docs/telemetry.md](docs/telemetry.md) for the schema and privacy policy.

---

## Dogfooding

HydraMem eats its own documentation. Run:

```bash
uv run python scripts/dogfood.py
```

This ingests all Markdown in `docs/` and `kms/` into HydraMem's own graph, then runs a Night Gardener cycle. It's the quickest way to verify the full pipeline works end-to-end.

---

## Project structure

```
hydramem/
├── hydramem/
│   ├── server.py               # MCP server (FastMCP, 18 tools, single-tenant)
│   ├── search.py               # Hybrid search + cached entity index
│   ├── cli.py                  # hydramem stats / telemetry / garden-status CLI
│   ├── gnn_prune.py            # Optional GNN spurious-edge pruner
│   ├── core/                   # Config, types, logging, token counting
│   ├── storage/                # GraphRepository + VectorRepository abstractions
│   │   ├── graph/              # LadybugDB / Kuzu / NetworkX backends
│   │   └── vector/             # LanceDB / in-memory backends
│   ├── llm/                    # Ollama / OpenAI / Anthropic providers
│   ├── ingest/                 # Chunker, extractor, embedder, ingest pipeline
│   ├── verification/           # SR-MKG, VoG, conflict checker, pipeline
│   ├── garden/                 # Night Gardener: inferrer, pruner, repository
│   └── telemetry/              # SQLite storage + shadow baseline + aggregator
├── kms/                        # Your knowledge files (.md)
├── docs/
│   ├── getting-started.md
│   ├── configuration.md
│   ├── architecture.md
│   ├── verification.md         # NEW – honest pipeline contract
│   ├── benchmarks.md           # NEW – reproducible experiment recipe
│   ├── roadmap.md              # NEW – living roadmap
│   ├── night-gardener.md
│   ├── telemetry.md
│   ├── mcp-tools-reference.md
│   └── opencode-setup.md
├── scripts/
│   ├── dogfood.py              # Self-ingest pipeline
│   └── benchmark.py            # NEW – benchmark scaffold
├── tests/
│   ├── unit/                   # 60+ unit tests (test_*.py at root)
│   └── integration/            # NEW – end-to-end pipeline tests
├── .github/
│   ├── workflows/              # NEW – ci.yml + release.yml
│   ├── ISSUE_TEMPLATE/         # NEW – bug + feature templates
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── skills/                 # OpenCode agent skills
├── CHANGELOG.md                # NEW – Keep a Changelog
├── CONTRIBUTING.md             # NEW
├── CODE_OF_CONDUCT.md          # NEW – Contributor Covenant 2.1
├── SECURITY.md                 # NEW – vulnerability disclosure
├── .pre-commit-config.yaml     # NEW
├── .editorconfig               # NEW
├── config.yml.example          # Full configuration reference
├── pyproject.toml
├── LICENSE                     # MIT
└── README.md
```

---

## Roadmap and contributing

- **Working with an AI agent?** Start at [AGENTS.md](AGENTS.md) — the harness
  entry point (project map, hard rules, and `nox` verification commands).
- See [docs/roadmap.md](docs/roadmap.md) for what is planned and explicitly
  out of scope.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up a dev environment,
  run the tests, and submit a PR.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting.

---

## License

MIT — see [LICENSE](LICENSE). HydraMem is and will remain open-source.
Anything we ship as a hosted product later will live in a separate repo.

---

## Acknowledgements

HydraMem stands on a lot of shoulders:

- **HippoRAG / HippoRAG 2** — neocortex / hippocampus offline consolidation.
- **Microsoft GraphRAG** — community summary verification at scale.
- **FastMCP** — the protocol glue that makes this useful to agents.
- **LanceDB**, **LadybugDB**, **Kuzu**, **NetworkX**, **fastembed**,
  **sentence-transformers** — the libraries we depend on.

If we are making a claim that conflicts with anyone's prior art, please open
an issue. Honesty is a feature.

---

## Technology stack

| Component | Technology | Notes |
|-----------|------------|-------|
| AI client | OpenCode / Claude Desktop / Cursor | Any MCP-compatible client |
| MCP server | Python + FastMCP | HTTP transport, 18 tools |
| Graph DB | LadybugDB (real-ladybug) | Fork of Kuzu, Cypher, single-file |
| Graph fallback | kuzu → NetworkX | Auto-detected at startup |
| Vector DB | LanceDB | Embedded, serverless |
| LLM (local) | Ollama / llama.cpp | gemma4:e4b, qwen2.5, etc. |
| LLM (external) | OpenAI / Anthropic | Optional, per-subsystem routing |
| Embeddings | fastembed (default) / sentence-transformers | Nomic v1.5, 512-d, CPU-friendly |
| Neural pruning | LightGNN (heuristic fallback) | PyG optional, capped at `HYDRAMEM_GNN_MAX_NODES` |
| Telemetry | SQLite | `~/.hydramem/metrics.db` |
| Config | YAML + .env + defaults | Layered resolution |

---

## Running tests

```bash
uv sync --extra dev
uv run pytest -v
uv run pytest --cov=hydramem

# Tests use mocked databases and a deterministic stub embedder
# (HYDRAMEM_EMBEDDER=stub) — no Ollama, no model download, no GPU required.
```

---

<p align="center">
  <sub>Built with care for honest local-first memory.</sub>
</p>
