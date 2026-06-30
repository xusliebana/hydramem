# Roadmap

> This is a living document. PRs to add or strike items are welcome.

## Recently shipped (this development cycle)

- **MemPalace-style install** — `uv tool install` / `pipx`, `hydramem init`,
  CLI verbs (`ingest` / `search` / `serve`), slim stdio Docker, single `/data`
  volume.
- **Boundary-aware overlapping chunker** + **hybrid BM25** lexical arm fused
  with vector + graph via RRF.
- **Hyper-relational qualifiers** on relations (temporal `valid_from` /
  `valid_to`, `verifier` provenance) with collision-safe merge, plus `as_of`
  temporal queries (`query_entity_relations` MCP tool, `as_of` on
  `get_entity_neighbors`).
- **Entity disambiguation registry** — collapses surface-form variants into one
  canonical node (collision avoidance), conservative + auditable.
- **`remember` MCP tool** — accumulate verified knowledge mid-conversation.
- **Reproducible local retrieval benchmark** (`scripts/benchmark.py local`) with
  an optional **LLM judge** (`--judge`) and honest "no LLM" fallback.

## Pruning recommendation (honest triage)

To stay a small, sharp, local-first project, these speculative items now live on
**research branches** (no shipping commitment), not the shipping roadmap:
R-GCN edge scorer, spectral community summaries, local LoRA embedder,
reasoning-motif miner, active-VoG bandit, heat-kernel scoring — see
[Research branches](#research-branches-no-shipping-commitment) below, and add a
👍 on an item's tracking issue if you want it prioritized. The single
highest-leverage shipping item is the **public dataset benchmark** (MuSiQue /
LongMemEval) — without it the verification / Night-Gardener value claims stay
unproven. The next quality lever is the **GLiNER extractor** (the regex
extractor is the weakest link). The Kuzu / LadybugDB backend should be
**deprecated** (upstream Kuzu is unmaintained; Graphiti dropped it too) in
favour of Grafeo (3.12+) / NetworkX.

## Now (0.2.x)

- [x] Honest verification pipeline (no random fallbacks, no false SR-MKG label)
- [x] Pruner actually deletes orphans
- [x] LightGNN scalability cap + low-rank features
- [x] Per-project entity index + graph cache in `SearchService`
- [x] CI, coverage, pre-commit, contributor docs
- [ ] First public benchmark run on MuSiQue + LongMemEval
       ([docs/benchmarks.md](benchmarks.md))
- [x] `hydramem-stats` MCP skill so agents can self-report savings
       (exposed as the `hydramem_stats_tool` MCP tool)
- [x] stdio transport for FastMCP (Claude Desktop friendly) — set
       `HYDRAMEM_TRANSPORT=stdio`

## Next (0.3.x)

- [x] Persistent MENTIONS edges in the NetworkX fallback so the pruner is
      safe in offline mode too
- [x] Async ingest worker with checkpointing for >50 k document corpora
       (`hydramem ingest-async` / [hydramem/ingest/async_worker.py](../hydramem/ingest/async_worker.py))
- [x] Pluggable extractor (factory + Protocol; NER / LLM-assisted backends
       can register without modifying the pipeline)
- [x] Per-relation provenance: keep the originating session id and timestamp
- [x] CRDT-style merge for sessions saved across multiple machines
       (`hydramem sessions-merge`)

## Later (≥ 1.0)

- [x] Multi-tenant deployment guide (one process per tenant + shared LanceDB)
       — see [docs/multi-tenant.md](multi-tenant.md)
- [x] Native Cypher planner so `hydra_search` can run a graph-only path
      without depending on vector results — exposed as `graph_only_search_tool`
- [x] Optional dashboard (read-only) served from `hydramem-dashboard`
- [x] Federated knowledge: signed exports / imports between trusted peers
       (`hydramem export` / `hydramem import`, HMAC-SHA256 envelope)

## 0.4.x — "Geometric memory"

Theme: replace heuristic retrieval/scoring with principled geometry and
modern local backends, without breaking the local-first contract.

- [x] Modern embedder backends (bge-small, gte-small, jina-v3) via ONNX —
      see [docs/internal/future_work/modern-embedders.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/modern-embedders.md).
      Config-driven backend/model selection in `embedding:` (auto |
      fastembed | sentence-transformers | stub); change `model:` and
      `dim:` to swap to BGE/GTE without code changes.
- [ ] GLiNER extractor backend (zero-shot, multilingual, CPU) —
      see [docs/internal/future_work/gliner-extractor.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/gliner-extractor.md)
- [x] Laplacian Positional Encodings as default features for `gnn_prune` —
      see [docs/internal/future_work/laplacian-pe.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/laplacian-pe.md).
      Implemented in [`hydramem/garden/spectral.py`](../hydramem/garden/spectral.py),
      wired into [`hydramem/gnn_prune.py`](../hydramem/gnn_prune.py); toggle via
      `gnn.use_laplacian_pe` (default on).
- [x] Personalized PageRank retrieval mode in `hydra_search`
      (`traversal: bfs | ppr | hybrid`) —
      see [docs/internal/future_work/ppr-retrieval.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/ppr-retrieval.md).
      Implemented in [`hydramem/ppr.py`](../hydramem/ppr.py) with RRF fusion; the
      `hydra_search_tool` MCP tool accepts a `traversal` argument.
- [x] Learned SR-MKG weights via local logistic calibration
      (`hydramem calibrate-srmkg`) —
      see [docs/internal/future_work/learned-srmkg-weights.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/learned-srmkg-weights.md).
      Decisions are logged to the `srmkg_decisions` SQLite table; training
      lives in [`hydramem/verification/calibration.py`](../hydramem/verification/calibration.py)
      and writes weights to `~/.hydramem/projects/<p>/srmkg_weights.json`.
- [x] Hyper-relational schema (qualifiers as first-class) — **shipped**:
      `Relation.qualifiers` with canonical keys (`valid_from` / `valid_to` /
      `verifier` / `evidence_chunk_id` / …), collision-safe merge, and `as_of`
      temporal queries. See
      [docs/internal/future_work/hyper-relational-schema.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/hyper-relational-schema.md)
- [ ] Typed retrieval planner (query classifier → strategy) —
      see [docs/internal/future_work/typed-retrieval-planner.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/typed-retrieval-planner.md)
- [~] Client LLM bridge/provider (delegate VoG / inference to an explicitly
      configured client-side LLM adapter) —
      see [docs/internal/future_work/client-llm-bridge.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/client-llm-bridge.md).
      **Ingestion path landed in 0.2.x**: agents call
      `ingest_prechunked` / `submit_session_extraction` to push
      chunks + entities + relations extracted with their own model;
      HydraMem only embeds and verifies (SR-MKG + VoG). VoG-side
      bridge (HydraMem asking the client for a verification completion)
      remains pending.
- [x] Unified embedded store: Grafeo as both graph **and** vector backend
      (HNSW index on `(:Chunk {embedding})`, shared ACID DB). LanceDB
      remains available via `HYDRAMEM_VECTOR_BACKEND=lancedb`.
- [ ] Retrieval-success telemetry (entity reuse cross-session) —
      foundation for 0.5.x consolidation
- [ ] First public benchmark on MuSiQue + LongMemEval (carried from 0.2)

## 0.5.x — "Learned consolidation"

Theme: the Night Gardener stops being a cron + LLM and starts behaving as
a real episodic→semantic consolidator.

- [ ] PPR-based consolidation phase in the Night Gardener —
      see [docs/internal/future_work/retrieval-success-consolidation.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/retrieval-success-consolidation.md)

> The learned-graph-scorer items that used to sit here — R-GCN edge scorer,
> spectral community summaries, local LoRA embedder, reasoning-motif miner,
> active-VoG bandit, heat-kernel scoring — moved to
> [Research branches](#research-branches-no-shipping-commitment): documented,
> votable, but with **no shipping commitment** until a benchmark proves the ROI.

## 1.x — "Self-refining memory"

- [ ] Bottom-up ontology induction (relation-type embeddings + hierarchical
      clustering with LLM probing for naming)
- [ ] Multi-modal ingest (PDF, AST-aware code chunking)
- [ ] Distributed Night Gardener with optional job queue (still local
      cluster, no cloud)
- [ ] Read-only graph dashboard with motifs / community view

## Research branches (no shipping commitment)

Documented but deliberately **off the shipping roadmap** — principled yet
unproven, they add surface area without demonstrated ROI for a small,
local-first project. The design thinking is preserved so nothing is lost and so
demand stays visible.

**How to vote.** Add a 👍 reaction on the item's tracking issue
([GitHub Issues](https://github.com/hydramem/hydramem/issues)) or open a thread
in [Discussions](https://github.com/hydramem/hydramem/discussions). An item
graduates back onto a milestone only when it gathers real demand **and** ships
with a benchmark that proves the ROI.

### Pruned from the roadmap (full design docs, votable)

- **R-GCN edge scorer** replacing heuristic LightGNN —
  [docs/internal/future_work/rgcn-edge-scorer.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/rgcn-edge-scorer.md)
- **Spectral community summaries** (local GraphRAG-style community cache) —
  [docs/internal/future_work/spectral-community-summaries.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/spectral-community-summaries.md)
- **Local LoRA embedder** fine-tuned on verified relations —
  [docs/internal/future_work/local-lora-embedder.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/local-lora-embedder.md)
- **Privacy-safe reasoning-motif miner** —
  [docs/internal/future_work/reasoning-motifs.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/reasoning-motifs.md)
- **Active-VoG bandit** — which borderline relations deserve the LLM call
  _(no design doc yet)_
- **Heat-kernel scoring** of implicit-relation candidates _(no design doc yet)_

### Exploratory spikes (no design doc, may never ship)

- `research/sheaf-memory` — contradictions as non-trivial sheaf cohomology
  over the typed knowledge graph
- `research/hyperbolic-kg` — Poincaré / κ-mixed-curvature embeddings for
  hierarchical relations
- `research/reasoning-motifs-v2` — subgraph contrastive learning over the
  motif corpus

## Won't do (intentionally)

- No hosted SaaS in this repository. A separate `hydramem-cloud` repo can
  exist later; the open-source core stays local-first.
- No telemetry that leaves the machine without explicit, per-event opt-in.
- No "agent that answers for you". HydraMem is **memory**, not a chat product.
- **No CoT capture from the client.** Sessions store the user query plus
  the *grounded context returned by HydraMem*; the agent's internal
  chain-of-thought is never stored. Any future "reasoning trace" feature
  must abstract over public graph nodes only (see
  [docs/internal/future_work/reasoning-motifs.md](https://github.com/hydramem/hydramem/blob/main/docs/internal/future_work/reasoning-motifs.md)).
- **No federated gradient sharing across tenants.** Federated *knowledge*
  via signed export/import (already shipped) is the supported model.
  Cross-tenant FedAvg / LoRA aggregation is rejected on privacy grounds.
- No full-attention Graph Transformers in the default install — RAM/CPU
  cost incompatible with local-first.
