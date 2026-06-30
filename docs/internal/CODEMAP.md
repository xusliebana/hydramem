# Code Map

Where things live and where to look **before** changing code. Pair this with the
module responsibilities in [CONTRIBUTING.md](../../CONTRIBUTING.md) and the flows in
[TECHNICAL_OVERVIEW.md](../TECHNICAL_OVERVIEW.md).

## Top level

```
hydramem/            library source (the shipped package)
tests/               pytest suite (asyncio_mode=auto, coverage ≥ 60%)
docs/                permanent project knowledge (this folder)
scripts/             init.sh, benchmark.py, dogfood.py
agents/              persistent agent-facing notes (IMPLEMENTATION, MEMORY)
.agent/              local, gitignored runtime state (current, tasks, handoff, logs)
.github/             skills/, workflows/ (CI), issue/PR templates, copilot-instructions
noxfile.py           task runner (tests matrix, lint, typecheck, api, build, verify)
pyproject.toml       package metadata, deps, entry points, tool config
```

## Package layout (`hydramem/`)

| Path | Responsibility | Entry point? |
|---|---|---|
| `core/` | `config.py`, `types.py`, `logging.py`, `tokens.py` — cross-cutting primitives | — |
| `storage/` | Graph + vector repository **abstractions** and backends (`graph/`, `vector/`, `federation.py`, `factory.py`, `base.py`) | — |
| `llm/` | LLM provider clients behind a base interface (`ollama`, `openai`, `anthropic`, `mistral`, `factory.py`) | — |
| `ingest/` | `chunker.py`, `extractor.py`, `embedder.py`, `pipeline.py`, `async_worker.py`, `registry.py` | — |
| `search.py` | Hybrid retrieval service: `priming_context`, `hydra_search`, `expand_context`, `trace_path` | — |
| `verification/` | Two-stage verifier: SR-MKG topological scorer + VoG groundedness | — |
| `garden/` | Night Gardener: `gardener.py`, `inferrer.py`, `pruner.py`, `repository.py`, `crdt.py`, `spectral.py` | — |
| `telemetry/` | Local SQLite metrics (`storage.py`), aggregation (`aggregate.py`), naive-RAG shadow estimator (`shadow.py`) | — |
| `ppr.py` | Personalized PageRank retrieval helper | — |
| `gnn_prune.py` | Optional LightGNN spurious-edge pruning (heuristic fallback) | — |
| `server.py` | FastMCP server, 18 MCP tools | `hydramem-server` |
| `cli.py` | `hydramem stats` / `telemetry` / `garden-status` / `init` | `hydramem` |
| `dashboard.py` | Telemetry dashboard | `hydramem-dashboard` |

## "I want to change X → start here"

| Goal | Start in | Then read |
|---|---|---|
| Add/modify an MCP tool | `hydramem/server.py` | [CONTRACTS/PUBLIC_API.md](CONTRACTS/PUBLIC_API.md), [mcp-tools-reference.md](../mcp-tools-reference.md), `tests/test_server.py` |
| Change retrieval ranking | `hydramem/search.py` | [architecture-ir-km.md](../architecture-ir-km.md), `tests/test_search.py`, [PLAYBOOKS/benchmark-regression.md](PLAYBOOKS/benchmark-regression.md) |
| Change relation/chunk verification | `hydramem/verification/` | [verification.md](../verification.md), `tests/test_verify.py`, `tests/test_calibration.py`, [PLAYBOOKS/benchmark-regression.md](PLAYBOOKS/benchmark-regression.md) |
| Change ingestion / chunking / extraction | `hydramem/ingest/` | `tests/test_ingest.py`, `tests/test_ingest_prechunked.py`, `tests/test_async_ingest.py` |
| Swap or add a storage backend | `hydramem/storage/` (implement the base class) | [DECISIONS/0002-storage-backends.md](DECISIONS/0002-storage-backends.md), `tests/test_db.py` |
| Add an LLM provider | `hydramem/llm/` (implement the base class) | `hydramem/llm/factory.py` |
| Tune the Night Gardener | `hydramem/garden/` | [night-gardener.md](../night-gardener.md), `tests/test_gardener.py`, `tests/test_garden_repository.py`, [PLAYBOOKS/benchmark-regression.md](PLAYBOOKS/benchmark-regression.md) |
| Add a metric / change the dashboard | `hydramem/telemetry/`, `hydramem/dashboard.py` | [telemetry.md](../telemetry.md), `tests/test_telemetry.py`, `tests/test_dashboard.py` |
| Change config keys | `hydramem/core/config.py` | [configuration.md](../configuration.md), [config.yml.example](../../config.yml.example) |

## Dependency direction

`server.py` / `cli.py` / `dashboard.py` (entry points) → `search.py`, `ingest/`,
`garden/`, `verification/`, `telemetry/` → `storage/`, `llm/` (via injected base
classes) → `core/`. Keep the arrows pointing inward; backends never import the
server.
