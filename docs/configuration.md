# Configuration Reference

HydraMem uses a **layered configuration** system:

```
config.yml  →  environment variables  →  built-in defaults
```

Configuration is searched in this order:
1. `config.yml` in the current working directory
2. `config.yaml` in the current working directory
3. `~/.hydramem/config.yml`

Copy the template to get started:

```bash
cp config.yml.example config.yml
```

---

## Full annotated config.yml

```yaml
# ─────────────────────────────────────────────────────────────
# HydraMem – config.yml
# ─────────────────────────────────────────────────────────────
# Place in the project root or ~/.hydramem/config.yml
# ─────────────────────────────────────────────────────────────

llm:
  # Provider strategy:
  #   auto       → tries Ollama first, falls back to external if API key is set
  #   local      → Ollama only (never calls external APIs)
  #   ollama     → explicit Ollama alias for "local"
  #   openai     → OpenAI API only
  #   anthropic  → Anthropic API only
  provider: auto

  local:
    model: gemma4:e4b            # any model pulled via `ollama pull`
    endpoint: http://localhost:11434

  external:
    provider: openai             # openai | anthropic | mistral (future)
    api_key_env: HYDRAMEM_OPENAI_KEY   # env var name — NEVER hardcode
    model: gpt-4o-mini           # cost-effective default

# ─────────────────────────────────────────────────────────────
# Embedding model (local, CPU-friendly)
# ─────────────────────────────────────────────────────────────
embedding:
  model: nomic-ai/nomic-embed-text-v1.5   # downloaded automatically on first use
  dim: 512                       # Nomic v1.5 (768-d) truncated + renormalised; 256 also fine
  backend: auto                  # auto | fastembed | sentence-transformers | stub

# ─────────────────────────────────────────────────────────────
# Storage paths
# ─────────────────────────────────────────────────────────────
storage:
  ladybug_db: ./data/hydramem.graph
  lancedb: ./data/lancedb
  knowledge_dir: ./kms           # default directory scanned by ingest_directory

# ─────────────────────────────────────────────────────────────
# MCP server
# ─────────────────────────────────────────────────────────────
server:
  host: 0.0.0.0
  port: 3000

# ─────────────────────────────────────────────────────────────
# Verification pipeline (SR-MKG + VoG)
# ─────────────────────────────────────────────────────────────
verification:
  srmkg_threshold_accept: 0.7    # score ≥ 0.7 → auto-accept
  srmkg_threshold_reject: 0.3    # score < 0.3 → auto-reject
  vog_max_candidates: 30         # max borderline relations sent to VoG
                                 # (reduce to control API costs)
  vog_use_local_llm: true        # force VoG to use local LLM even if
                                 # external is the default provider
  srmkg_log_decisions: true      # log SR-MKG components for `calibrate-srmkg`

# ─────────────────────────────────────────────────────────────
# Search / retrieval
# ─────────────────────────────────────────────────────────────
search:
  traversal: bfs                 # bfs | ppr | hybrid (PPR = HippoRAG-style)
  ppr:
    alpha: 0.5                   # restart probability
    max_iter: 50
    tol: 1.0e-4
    top_k: 30                    # PPR nodes kept before chunk fetch

# ─────────────────────────────────────────────────────────────
# GNN pruner (Night Gardener edge scorer)
# ─────────────────────────────────────────────────────────────
gnn:
  use_laplacian_pe: true         # spectral positional encodings as features
  lpe_k: 32                      # number of Laplacian eigenvectors

# ─────────────────────────────────────────────────────────────
# Night Gardener (autonomous learning)
# ─────────────────────────────────────────────────────────────
night_gardener:
  enabled: true
  schedule: "0 3 * * *"          # cron expression: 3 AM daily
  infer_with: local              # always infer locally (zero API cost)
  verify_with: auto              # local if available, else external
  min_repeat_count: 1            # only send snapshots seen >= N times to the inferrer
  consolidation:                 # Phase 2.5 — retrieval-success re-weighting (no LLM)
    enabled: true
    window_days: 30
    boost_per_session: 0.02
    decay_after_days: 14
    decay_per_step: 0.05
    min_confidence: 0.05
    max_confidence: 0.99
  review:                        # Phase 3.5 — human-in-the-loop pruner training
    enabled: false               # queue borderline prune candidates for labelling
    sample_rate: 0.2
    uncertainty_band: 0.25
    max_per_run: 50
    auto_train: false            # retrain the learned scorer once enough labels exist
  temporal_invalidation:         # Phase 2.4 — Zep/Graphiti-style fact supersession
    enabled: false
    functional_types: []         # relation types where a new value supersedes the old
```

The review loop is driven by two CLI verbs: `hydramem review` (label queued
spurious-edge candidates → golden dataset) and `hydramem train-pruner` (learn a
supervised edge scorer from the labels). See
[night-gardener.md](night-gardener.md#phase-35-prune-review-human-in-the-loop-opt-in)
and [internal/future_work/hitl-prune-review.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/hitl-prune-review.md).

---

## LLM Provider Reference

### `auto` (recommended default)

HydraMem tries to reach Ollama on `local.endpoint`. If Ollama is unavailable **and** an API key env var is set, it falls back to the external provider.

```yaml
llm:
  provider: auto
  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434
  external:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    model: claude-haiku-20240307
```

### `local` / `ollama`

Forces all LLM calls through Ollama. Errors if Ollama is unreachable.

```yaml
llm:
  provider: local
  local:
    model: qwen2.5:7b
    endpoint: http://localhost:11434
```

Popular local models:

| Model | Size | Notes |
|-------|------|-------|
| `gemma4:e4b` | E4B | Default — efficient on-device (Gemma 4) |
| `llama3.2` | 3B | Fast, balanced quality |
| `qwen2.5:7b` | 7B | Strong reasoning |
| `mistral:7b` | 7B | Fast inference |
| `phi3.5` | 3.8B | Very fast on CPU |
| `deepseek-r1:8b` | 8B | Excellent for reasoning tasks |

### `openai`

```yaml
llm:
  provider: openai
  external:
    provider: openai
    api_key_env: HYDRAMEM_OPENAI_KEY   # set: export HYDRAMEM_OPENAI_KEY=sk-...
    model: gpt-4o-mini
```

Supported models: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1-mini`.

### `anthropic`

```yaml
llm:
  provider: anthropic
  external:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY     # set: export ANTHROPIC_API_KEY=sk-ant-...
    model: claude-sonnet-4-20250514
```

Supported models: `claude-opus-4-5`, `claude-sonnet-4-20250514`, `claude-haiku-20240307`.

---

## Per-subsystem LLM routing

Different subsystems can use different LLM providers. This lets you run cheap/free local inference for bulk operations (Night Gardener) while using a powerful external model for interactive queries.

```yaml
llm:
  provider: openai          # default for queries
  external:
    provider: openai
    api_key_env: HYDRAMEM_OPENAI_KEY
    model: gpt-4o-mini

night_gardener:
  infer_with: local         # bulk inference → free, local
  verify_with: auto         # borderline cases → local first, API as fallback
  min_repeat_count: 2       # bias the inferrer toward repeated evidence

verification:
  vog_use_local_llm: true   # VoG stays local even if global provider is external
```

---

## Environment Variables

All sensitive values (API keys) must be provided via environment variables. Never commit keys to `config.yml`.

| Variable | Description |
|----------|-------------|
| `HYDRAMEM_OPENAI_KEY` | OpenAI API key (used when `api_key_env: HYDRAMEM_OPENAI_KEY`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `HYDRAMEM_ANTHROPIC_KEY` | Alternative Anthropic key env var name |
| `HYDRAMEM_PROJECT` | Default project namespace |
| `HYDRAMEM_LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |

Store secrets in `.env` at the project root (loaded automatically via python-dotenv):

```bash
# .env
HYDRAMEM_OPENAI_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Verification Thresholds

The two-level verification pipeline uses configurable score thresholds.

```
SR-MKG score:  0.0 ──────────────── 1.0
                      ↑           ↑
               reject (0.3)  accept (0.7)
                      └── VoG zone ──┘
```

| Parameter | Default | Effect |
|-----------|---------|--------|
| `srmkg_threshold_accept` | `0.7` | Relations above this are auto-accepted without LLM call |
| `srmkg_threshold_reject` | `0.3` | Relations below this are auto-rejected without LLM call |
| `vog_max_candidates` | `30` | Cap on LLM-verified relations per Night Gardener run |
| `vog_use_local_llm` | `true` | Force VoG on local even when global provider is external |

Tighten `srmkg_threshold_accept` (e.g. `0.85`) for higher-quality but sparser graphs.  
Raise `vog_max_candidates` (e.g. `100`) for more thorough but more expensive verification.

---

## Storage Paths

| Key | Default | Notes |
|-----|---------|-------|
| `storage.ladybug_db` | `./data/hydramem.graph` | Graph store (NetworkX/Grafeo) |
| `storage.lancedb` | `./data/lancedb` | LanceDB vector index directory |
| `storage.knowledge_dir` | `./kms` | Default directory for `ingest_directory` |

> **Deprecation:** the **Kuzu / LadybugDB** graph backend
> (`HYDRAMEM_GRAPH_BACKEND=kuzu`) is deprecated — upstream Kuzu is unmaintained.
> It still loads (emitting a `DeprecationWarning`) but will be removed in a
> future release. Use the default **Grafeo** (Python 3.12+) or **NetworkX**
> backend. The `storage.ladybug_db` key name is retained as the canonical path
> for backward compatibility (alias: `storage.grafeo_db`).

All paths support `~` home expansion and are created automatically on first use.

---

## Night Gardener Schedule

The `schedule` key accepts a standard 5-field cron expression. The scheduler must be activated separately (daemon, cron, or systemd). See [night-gardener.md](night-gardener.md#scheduling) for setup instructions.

```yaml
night_gardener:
  schedule: "0 3 * * *"    # 3 AM daily
  # schedule: "0 */6 * * *"  # every 6 hours
  # schedule: "0 0 * * 0"    # weekly, Sunday midnight
```

---

## Embedding Backends

`embedding.backend` selects how `EmbeddingService` materialises vectors:

| Value | Backend | Install |
|-------|---------|---------|
| `auto` (default) | Prefers `fastembed`, falls back to `sentence-transformers`, then to a deterministic stub | `pip install hydramem[fastembed]` |
| `fastembed` | ONNX runtime (~80 MB, no torch) | `pip install hydramem[fastembed]` |
| `sentence-transformers` | Full PyTorch + ST (~2 GB) | `pip install hydramem[sentence-transformers]` |
| `stub` | Deterministic SHA-256-derived pseudo-embedding (offline tests only) | none |

`embedding.model` accepts any model name supported by the chosen backend. The default is `nomic-ai/nomic-embed-text-v1.5` (768-d Matryoshka, truncated + renormalised to 512-d via `embedding.dim`). Smaller drop-in alternatives:

| Model | Dim | Notes |
|-------|-----|-------|
| `BAAI/bge-small-en-v1.5` | 384 | MIT licence; +3–5 nDCG vs MiniLM on MTEB |
| `thenlper/gte-small` | 384 | Apache-2.0; multilingual |
| `sentence-transformers/all-mpnet-base-v2` | 768 | Stronger retrieval, larger index |

Changing `model` requires re-ingesting the corpus so chunk dimensions match
the LanceDB index. Update `embedding.dim` accordingly.

Override via env var: `HYDRAMEM_EMBEDDER={fastembed,sentence-transformers,stub}`.

---

## Entity Extraction

`extraction.backend` selects how named entities are pulled out during ingest.

| Backend | Notes |
|---------|-------|
| `heuristic` (default) | Regex (capitalised phrases, CamelCase, backtick spans). Zero extra deps, English-leaning. |
| `gliner` | Zero-shot, multilingual NER. Needs the `[gliner]` extra (`pip install 'hydramem[gliner]'`). **Degrades to `heuristic`** if the model is unavailable. |

GLiNER sub-keys: `extraction.gliner.model` (default `urchade/gliner_multi-v2.1`),
`extraction.gliner.threshold` (`0.5`), `extraction.gliner.labels` (the zero-shot
entity types). Override the backend via `HYDRAMEM_EXTRACTOR`.

---

## Search Traversal

`search.traversal` controls how `hydra_search_tool` walks the knowledge graph
from query-derived seeds. Each request can override it via the `traversal`
parameter on the MCP tool.

| Mode | Description | When to use |
|------|-------------|-------------|
| `bfs` (default) | Breadth-first expansion from query entities (original behaviour) | Single-entity look-ups; lowest latency |
| `ppr` | Personalized PageRank seeded at query entities (HippoRAG-style) | Multi-hop questions, fuzzy seeds |
| `hybrid` | Vector + BFS + PPR rankings fused via Reciprocal Rank Fusion | Best quality; ~10–30 ms PPR overhead |

The PPR sub-section tunes the iterative solver:

| Key | Default | Effect |
|-----|---------|--------|
| `search.ppr.alpha` | `0.5` | Restart probability — higher keeps mass closer to seeds |
| `search.ppr.max_iter` | `50` | Hard cap on power iterations |
| `search.ppr.tol` | `1.0e-4` | L1 convergence tolerance |
| `search.ppr.top_k` | `30` | PPR-ranked nodes whose chunks feed the verifier |

Implementation: [`hydramem/ppr.py`](../hydramem/ppr.py) (pure NumPy, no scipy).

### Typed retrieval planner (opt-in)

When `search.planner.enabled` is true and the caller does not pin a `traversal`
(or pass `strategy_override`), a zero-shot classifier picks a strategy from the
query: factoid → cheap BFS + skip-VoG, multi-hop → hybrid, comparative → PPR.

| Key | Default | Effect |
|-----|---------|--------|
| `search.planner.enabled` | `false` | Turn the planner on (env `HYDRAMEM_PLANNER=1`) |
| `search.planner.threshold` | `0.15` | Min cosine confidence; below this it uses the default strategy (no fabricated certainty) |

Implementation: [`hydramem/planner.py`](../hydramem/planner.py). The chosen
strategy + confidence are logged to telemetry for audit.

---

## GNN Pruner Features

The Night Gardener's GNN pruner uses **Laplacian Positional Encodings** as
node features by default. LPE turns the GNN into a real spectral model
instead of a heuristic over random features. Toggle and tune via:

| Key | Default | Effect |
|-----|---------|--------|
| `gnn.use_laplacian_pe` | `true` | When false, falls back to low-rank random features |
| `gnn.lpe_k` | `32` | Number of non-trivial Laplacian eigenvectors used |

The encoding is computed lazily for every prune cycle and concatenated
with normalised node degree. Implementation:
[`hydramem/garden/spectral.py`](../hydramem/garden/spectral.py).

Env overrides for one-off experiments:

```bash
HYDRAMEM_GNN_LAPLACIAN_PE=0 hydramem ...   # disable LPE
HYDRAMEM_GNN_LPE_K=16 hydramem ...         # smaller spectral basis
```

---

## SR-MKG Calibration

When `verification.srmkg_log_decisions` is on (default), every SR-MKG
decision is recorded with its raw component breakdown
(`base`, `jaccard`, `type_boost`, `isolated`) in the `srmkg_decisions`
SQLite table inside `~/.hydramem/metrics.db`. Once enough decisions have
accumulated for a project, run:

```bash
hydramem calibrate-srmkg --project default --min-samples 50
```

The trained logistic-regression weights are written to
`~/.hydramem/projects/<project>/srmkg_weights.json` and picked up
transparently by `SRMKGScorer` on its next instantiation. See
[verification.md#per-project-calibration](verification.md#per-project-calibration)
for the workflow.
