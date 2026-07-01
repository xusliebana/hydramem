# Changelog

All notable changes to HydraMem are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] – 2026-07-01

### Added

- **Comprehensive CLI & Skills usage guide (Spanish)** — new `docs/guia-uso-completa.md`
  documenting all CLI commands, Agent Skills setup, conversation compaction
  (token savings mechanism), and MCP server startup flow.

## [0.2.0] – Unreleased

### Changed — Default local models (Gemma 4 + Nomic Embed v1.5)

- **Default local LLM** is now `gemma4:e4b` (Gemma 4 E4B) instead of `llama3.2`.
  Pull it with `ollama pull gemma4:e4b`. Override via `llm.local.model` /
  `OLLAMA_MODEL`.
- **Default embedder** is now `nomic-ai/nomic-embed-text-v1.5` (Matryoshka, native
  768-d) **truncated + renormalised to 512-d** (`embedding.dim`), replacing
  `all-MiniLM-L6-v2` (384-d). Set `embedding.dim: 256` for smaller/faster indexes.
  `EmbeddingService` now performs the Matryoshka truncation; the
  sentence-transformers backend loads Nomic with `trust_remote_code=True`.
- **Nomic task prefixes** are now applied automatically: search queries are
  encoded with `search_query:` and indexed chunks/documents with
  `search_document:` (the asymmetric encoding Nomic is trained for). Skipped for
  non-Nomic models and the offline stub embedder.
- **Migration:** existing vector stores were built at 384-d and are incompatible
  with the new 512-d default — re-ingest your corpus, or pin the previous values in
  `config.yml` (`embedding.model: all-MiniLM-L6-v2`, `embedding.dim: 384`).

### Added — Human-in-the-loop pruner training (active learning)

An opt-in loop that turns the heuristic GNN pruner into a **learned, supervised**
spurious-edge scorer using a human-curated golden dataset — uncertainty sampling
+ weak supervision → graph denoising (cf. NRGNN, Confident Learning/Cleanlab).

- **Capture (Night Gardener Phase 3.5)** — when `night_gardener.review.enabled`,
  the Gardener samples borderline spurious-edge candidates (those near the GNN
  decision threshold) into a local review queue with their structural features.
  **Nothing is deleted**; the sample size is `review.sample_rate` /
  `review.max_per_run`.
- **Label** — `hydramem review` is an interactive CLI to mark each queued edge
  `prune` / `keep` / `skip`; `--status` prints queue counts and `--export PATH`
  writes the golden dataset as JSONL. Storage:
  [hydramem/garden/review.py](hydramem/garden/review.py) (`PruneReviewStore`,
  SQLite under the HydraMem home dir).
- **Train** — `hydramem train-pruner` fits a pure-NumPy logistic edge scorer over
  the labelled features (mirrors the SR-MKG calibrator; no scikit-learn/torch)
  and writes `~/.hydramem/projects/<p>/prune_weights.json`. Refuses to fit with
  too few samples or a single class (honesty contract).
- **Use** — `GNNPruner` automatically prefers the `learned` backend when those
  weights exist (else PyG / heuristic). Shared edge features keep capture,
  training, and scoring consistent.
- **Auto-train (step 2, opt-in)** — `night_gardener.review.auto_train` retrains
  the scorer at the end of a cycle once enough labels exist.
- **Audit** — `prune_reviews_queued` and `pruner_retrained` surface in
  `garden-status`. Config: `night_gardener.review.*`. See
  [docs/internal/future_work/hitl-prune-review.md](docs/internal/future_work/hitl-prune-review.md).

### Added — Dataset benchmark, GLiNER, consolidation, retrieval planner

- **Dataset-scale benchmark** ([scripts/benchmark.py](scripts/benchmark.py)):
  `ingest` / `run` / `report` are now implemented (previously stubs). Loaders
  normalise HotpotQA (direct download) and accept any dataset via `--from-file`
  (MuSiQue / LongMemEval print an honest "no stable URL" message). `run`
  evaluates three conditions — `naive_topk`, `hydra_search_no_garden`,
  `hydra_search_garden` (the last after N `NightGardener` cycles) — reporting
  Recall@5, optional LLM-judged faithfulness (`--judge`, honest "no LLM"
  fallback), avg tokens, and p50/p95 latency, with full provenance (commit,
  embedder, judge). `report` renders Markdown with an honest win/lose narrative.
- **GLiNER extractor backend** (`extraction.backend: gliner`): zero-shot,
  multilingual NER gated behind the new optional **`[gliner]`** extra. Lazy-
  loads the model and **degrades gracefully to the heuristic extractor** when
  the extra/model is unavailable. Surface forms are canonicalised through the
  disambiguation registry. Config: `extraction.backend`, `extraction.gliner.*`.
- **Retrieval-success consolidation** in the Night Gardener (Phase 2.5,
  **no LLM in the path**): re-weights memory by what gets reused across
  sessions. New `entity_reuse()` telemetry query (derived from data already on
  disk), `KnowledgeStore.adjust_confidences()`, degree-normalised + tanh-
  saturated boosts, aged-isolate decay with hard confidence clamps, and
  **prune protection** for entities reused across ≥2 sessions. New counters
  `entities_boosted` / `entities_decayed` / `prune_protected` surface in
  `garden-status`. Config: `night_gardener.consolidation.*`.
- **Typed retrieval planner** (`search.planner.enabled`, opt-in): a zero-shot
  query classifier (`hydramem/planner.py`) picks a strategy (factoid → cheap
  BFS + skip-VoG; multi-hop → hybrid; comparative → PPR) and **falls through to
  the default below a confidence threshold** (no fabricated certainty). Wired
  into `hydra_search`; the `hydra_search_tool` MCP tool gains an optional
  `strategy_override` argument; `planner` strategy/confidence is logged for
  audit. Config: `search.planner.*`.

### Deprecated

- **Kuzu / LadybugDB graph backend** (`HYDRAMEM_GRAPH_BACKEND=kuzu`, the
  `[kuzu]` extra): upstream Kuzu is unmaintained. It still loads but now emits a
  `DeprecationWarning` and will be removed in a future release — use the default
  **Grafeo** (Python 3.12+) or **NetworkX** backend.

### Added — Agent-driven ingestion (BYO-extraction)

Two new MCP tools let agents (Copilot, opencode, Claude Desktop) submit
documents and session knowledge already chunked + entity/relation-extracted
by **their own** LLM, instead of relying on HydraMem's regex heuristic or
spinning up a separate provider. The agent's model already has context
loaded; HydraMem just embeds, stores, and verifies.

- **`ingest_prechunked(source, chunks=[…], doc_id?, project, session_id)`**
  — chunks carry `{text, idx?, entities, relations?}`. HydraMem embeds
  locally (`all-MiniLM-L6-v2`), persists chunks + entities + `MENTIONS`
  edges, and runs **SR-MKG (+ VoG when borderline)** on every relation so
  agent hallucinations are filtered before they hit the graph.
- **`submit_session_extraction(entities, relations, session_id, project)`**
  — graph-only contribution at session close (no chunks). Same verifier
  filter. Lets a session deposit its findings without waiting for the
  offline Night Gardener cycle.
- New skill **[`.github/skills/hydramem-ingest-smart/`](.github/skills/hydramem-ingest-smart/SKILL.md)**
  instructs the agent on chunking, entity typing, relation extraction with
  honest confidences, and fallback rules to plain `ingest_markdown`.
- Hard caps (defence-in-depth) configurable via
  `ingest.max_chunks` / `max_entities` / `max_relations` (200 / 1000 / 500
  by default) or env vars `HYDRAMEM_INGEST_MAX_*`.
- `ingest.verify_agent_relations` (default `true`, env
  `HYDRAMEM_VERIFY_AGENT_RELATIONS`) toggles the verifier pass; off means
  "trust the agent" (not recommended).
- `ingest.mode` ∈ `auto|agent|heuristic` (env `HYDRAMEM_INGEST_MODE`) is
  informational — both tools always coexist; the value guides which skill
  the agent prefers.
- Provenance: every agent-submitted relation carries
  `origin_tool="ingest_prechunked"` (or `"submit_session_extraction"`) and
  the `session_id`, so the graph remains auditable / revertible.
- Telemetry: the MCP layer logs `relations_proposed`, `relations_accepted`,
  `relations_rejected`, and `truncated_*` counters per call.
- New unit tests: [`tests/test_ingest_prechunked.py`](tests/test_ingest_prechunked.py)
  (9 cases) covering happy path, unknown endpoints, verifier rejection,
  caps, and payload validation. Full suite: 109/109 pass.

### Added — Grafeo vector backend (unified store)

The same Grafeo database that holds the graph can now hold the HNSW
vector index too, so a single embedded directory is enough for full
hybrid search. LanceDB is no longer required by default.

- **`GrafeoVectorRepository`** ([`hydramem/storage/vector/grafeo_repo.py`](hydramem/storage/vector/grafeo_repo.py))
  — HNSW index on `(:Chunk {embedding})`, attaches the embedding to the
  same node the graph repo already created. Defensive parsing of
  Grafeo's `vector_search` row shapes for forward compatibility.
- **Shared `GrafeoDB` handle**: the storage factory keeps one
  `GrafeoDB` per process per path, passed to both the graph and the
  vector repositories — so chunk + embedding + edges write to the same
  ACID database, no dual-directory drift.
- New env switch **`HYDRAMEM_VECTOR_BACKEND`** ∈ `grafeo` (default) |
  `lancedb` (opt-in) | `memory`. Auto-fallback chain: Grafeo → LanceDB
  → in-memory.
- New config alias `storage.grafeo_db` / `GRAFEO_DB_PATH` (the legacy
  `storage.ladybug_db` / `LADYBUG_DB_PATH` still works).
- `GrafeoGraphRepository.__init__` now accepts a pre-opened `db=`
  instance so the factory can share the handle.

### Changed — Graph backend & install simplification

- **Graph backend swapped from Kuzu to [Grafeo](https://pypi.org/project/grafeo/)**
  (Rust core via PyO3, Apache-2.0). Single ~5 MB precompiled wheel, native
  Cypher with parameters, ACID transactions, HNSW vector indexes available
  if we ever want to consolidate vector storage. New repository in
  [`hydramem/storage/graph/grafeo_repo.py`](hydramem/storage/graph/grafeo_repo.py).
  Kuzu and LadybugDB remain available as **opt-in** via
  `HYDRAMEM_GRAPH_BACKEND=kuzu|ladybug` (Kuzu now lives in the
  `[kuzu]` extra, install with `pip install hydramem[kuzu]`).
- **NetworkX backend is now persistent** (pickle, atomic write +
  `os.replace`, autoflush on every mutation + `atexit` safety net). Acts
  as the automatic fallback when Grafeo is unavailable (e.g. on
  Python 3.11). Before this release the NetworkX backend silently lost
  the graph on every restart.
- **Minimum recommended Python is now 3.12** (Grafeo's wheels target 3.12+).
  The package still installs on 3.11 — it just falls back to the NetworkX
  pickle backend automatically.

### Fixed — Broken / stale dependencies

- Replaced unresolvable pin `real-ladybug>=0.16,<0.17` (the published
  version is 0.15.3) — `pip install hydramem` now works without
  `--no-deps` hacks.
- Bumped `fastmcp` from the obsolete `>=0.4,<0.5` pin to `>=2.14,<3.0`;
  the server code already used the 2.x `streamable-http` API.
- Bumped `ollama` to `>=0.4.0` to resolve the `httpx` version conflict
  with `fastmcp` 2.14.
- Removed the unused `pandas` dependency (~50 MB) — no `import pandas`
  anywhere in `hydramem/` or `tests/`.
- Promoted `fastembed` from the `[fastembed]` extra to a core
  dependency; the default config asks for it and the install was
  effectively broken without it.
- [`hydramem/core/config.py`](hydramem/core/config.py): storage paths and
  MCP host/port now actually honour `config.yml` (the YAML lookup was
  missing — only env vars and hardcoded defaults were applied).

### Changed — Dockerfile

- Simplified [`Dockerfile`](Dockerfile) — single `pip install .` instead
  of a hand-curated `uv pip install` list that drifted from
  `pyproject.toml`.

### Migration notes

- Existing Kuzu databases are not auto-migrated. Either reingest your
  documents (recommended), or `pip install hydramem[kuzu]` and set
  `HYDRAMEM_GRAPH_BACKEND=kuzu` to keep using the old store.
- The default storage path moved from `hydramem.ladybug` to
  `hydramem.graph` in the example config; existing deployments using
  the old name keep working (Grafeo just creates the directory as-is).

### Highlights

This release is an **honesty / hardening pass** before public launch. Several
metrics in v0.1.x silently inflated themselves; they now reflect reality.
A handful of features marketed as "revolutionary" have been clarified to
match what the code actually does.

It also lands the first batch of the **0.4.x "Geometric memory"** roadmap:
Personalized PageRank retrieval, Laplacian Positional Encodings for the
GNN pruner, per-project SR-MKG calibration, and config-driven embedder
backend selection — all pure-NumPy, no new runtime dependencies.

### Added — Geometric memory (0.4.x roadmap)

- **Personalized PageRank retrieval** in `hydra_search`. The MCP tool
  `hydra_search_tool` accepts a new `traversal` argument
  (`bfs` | `ppr` | `hybrid`); `hybrid` fuses vector, BFS and PPR rankings
  via Reciprocal Rank Fusion. Implementation in
  [`hydramem/ppr.py`](hydramem/ppr.py); knobs under `search.ppr.*` in
  `config.yml`. See
  [docs/configuration.md#search-traversal](docs/configuration.md#search-traversal)
  and
  [docs/internal/future_work/ppr-retrieval.md](docs/internal/future_work/ppr-retrieval.md).
- **Laplacian Positional Encodings as default GNN-pruner features**.
  Replaces random low-rank features with a real spectral signal computed
  in [`hydramem/garden/spectral.py`](hydramem/garden/spectral.py). Toggle with
  `gnn.use_laplacian_pe` / `gnn.lpe_k` (defaults: on, k=32). See
  [docs/internal/future_work/laplacian-pe.md](docs/internal/future_work/laplacian-pe.md).
- **Learned SR-MKG weights** via per-project logistic calibration.
  `VerificationPipeline` now logs every SR-MKG decision with its raw
  component breakdown to a new `srmkg_decisions` SQLite table; the
  `hydramem calibrate-srmkg --project X` CLI subcommand fits an
  L2-regularised logistic regression and writes the trained weights to
  `~/.hydramem/projects/<p>/srmkg_weights.json`, where `SRMKGScorer`
  picks them up transparently. Implementation in
  [`hydramem/verification/calibration.py`](hydramem/verification/calibration.py).
  See
  [docs/verification.md#per-project-calibration](docs/verification.md#per-project-calibration).
- **Config-driven embedder backend selection**. New `embedding.backend`
  key (`auto` | `fastembed` | `sentence-transformers` | `stub`) plus
  YAML-overridable `embedding.model` / `embedding.dim`. Drop-in upgrades
  to BGE-small / GTE-small / MPNet via config alone — no code changes.
  See
  [docs/configuration.md#embedding-backends](docs/configuration.md#embedding-backends).

### Added

- **stdio MCP transport** so HydraMem can be launched directly by Claude
  Desktop / Cursor / Continue. Set `HYDRAMEM_TRANSPORT=stdio`.
- **`hydramem_stats_tool` MCP tool** so agents can self-report token savings
  and Night Gardener metrics without shelling out to the CLI.
- **`graph_only_search_tool` MCP tool + `SearchService.graph_only_search`** —
  pure graph-only retrieval that does not depend on vector embeddings.
- **Persistent MENTIONS edges in the NetworkX backend**, making the offline
  pruner safe and giving `graph_only_search` real data to walk.
- **Per-relation provenance** (`session_id`, `origin_tool`, `created_at`) on
  the `Relation` dataclass and the LadybugDB schema.
- **Pluggable extractor** — `EntityExtractorProtocol` + `create_extractor()`
  factory selectable via `HYDRAMEM_EXTRACTOR`.
- **Async resumable ingest** (`hydramem/ingest/async_worker.py`,
  `hydramem ingest-async`) with per-file BLAKE2b checkpointing for corpora
  that exceed a synchronous walk.
- **CRDT-style session merge** (`hydramem/garden/crdt.py`,
  `hydramem sessions-merge`) so Night Gardener observations from multiple
  machines can be combined deterministically.
- **Federated signed exports / imports** (`hydramem/storage/federation.py`,
  `hydramem export` / `hydramem import`) using HMAC-SHA256 envelopes.
  Imports verify signature + optional issuer whitelist before merging.
- **Read-only HTML dashboard** (`hydramem/dashboard.py`,
  `hydramem dashboard`) — stdlib-only, binds to localhost by default.
- **Multi-tenant deployment guide** at `docs/multi-tenant.md` with a
  systemd template.

- **Embedding backend auto-detection.** `EmbeddingService` now prefers
  `fastembed` (ONNX, ~80 MB, no torch) when installed, falls back to
  `sentence-transformers`, then to a deterministic stub for offline tests.
  Override with `HYDRAMEM_EMBEDDER={fastembed,st,stub}`.
- **Per-project entity index + graph cache** in `SearchService` (TTL 30 s).
  Eliminates the O(N · terms) entity scan that ran on every query.
- **`hydramem stats --raw`** flag for auditing per-event baseline / injected
  token counts.
- **GraphRepository.delete_entity** added to the protocol; implemented for
  NetworkX and LadybugDB/Kuzu backends.
- **End-to-end integration tests** under `tests/integration/`.
- **Coverage, mypy, pre-commit, GitHub Actions CI** wired up.
- **`.github/`**: issue templates, PR template, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`.

### Changed (honesty)

- **VoG no-evidence path is no longer optimistic.** A `Relation` without
  `source_text` / `target_text` is now rejected with `score=0.0` and level
  `vog_no_evidence` instead of the previous `random.uniform(0.75, 0.95)` which
  silently inflated the average VoG score. Empty LLM responses also reject
  (level `vog_unavailable`).
- **`VerificationPipeline.verify_chunks` renamed honestly** in docs/CLI.
  This path is a *vector-similarity prefilter + VoG*, not SR-MKG. Output keys
  now include `rejected_vector`; the legacy `rejected_srmkg` key is kept as a
  deprecated alias. CLI label is now "Rejected (vector prefilter)".
- **`KnowledgePruner.prune` actually deletes** isolated entities through the
  new `delete_entity` API and reports `pruned_entities` only when deletion
  succeeds. Previously it counted candidates without removing them.
- **`night_gardener.min_repeat_count` default is now 2** (was 1). The
  "only-learn-from-repeated-evidence" feature is now active by default.
- **`RelationInferrer._synthetic_fallback` removed.** Without real session
  text, `infer()` returns an empty list; it no longer invents random
  `co_mentioned` placeholders that polluted `relations_proposed/accepted`.
- **SR-MKG weights moved to Config** (`verification.srmkg_weight_*`) so
  experiments and benchmarks can tune them without forking.

### Fixed

- **NightGardener status race.** The `finally` branch in `run()` reloaded
  status before clearing `is_running`, so cycle increments
  (`total_runs`, `relations_*`) are no longer overwritten by the stale
  in-flight copy.
- **Telemetry no longer swallows exceptions silently.** `log_event` now logs
  failures at `debug` level via the `logging` module.
- **LightGNN scalability.** Auto-falls back to the heuristic backend when the
  graph exceeds `HYDRAMEM_GNN_MAX_NODES` (default 5 000). Replaced the
  identity feature matrix with a low-rank random one and reduced the training
  loop, cutting memory and time by an order of magnitude on small KGs.
- **`IngestionPipeline.ingest_file` batch-embeds chunks** (~10× faster than
  the previous chunk-by-chunk loop).

### Documentation

- README now ships with an honest comparative table and clarified positioning
  language.
- New `docs/verification.md` explains what SR-MKG and VoG actually do, and
  what the chunk prefilter is (and is *not*).
- New `docs/benchmarks.md` placeholder with a reproducible recipe.
- Server module documents its single-tenant concurrency model.
- Telemetry shadow estimator now documents the baseline formula.

## [0.1.0] – initial public preview

- First public version. See git history for details.
