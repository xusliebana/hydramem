# Future Work — HydraMem

This folder contains **per-feature design documents** for items on the
extended roadmap (see [../roadmap.md](../../roadmap.md)). Each doc follows the
same structure so a contributor — or an LLM coding agent — can pick one up
and turn it into a PR with minimal additional context.

## How to read these docs

Every feature doc has the same eight sections:

1. **Why it matters** — the problem it solves in HydraMem specifically
2. **State of the art** — relevant papers / systems
3. **Proposed architecture** — how it fits into the current code base,
   with concrete files and class names where possible
4. **Risks** — what can go wrong, both technically and on the privacy /
   honesty contract
5. **Computational cost** — order of magnitude on a local machine
6. **Privacy implications** — explicit, since HydraMem is local-first
7. **Local-first viability** — does it survive the no-cloud constraint?
8. **Suggested implementation strategy** — milestone-style, ordered steps
9. **Concrete code changes** — exact files to add / modify
10. **References** — citations

## Status legend

| Symbol | Meaning |
|--------|---------|
| 🟢     | Immediate win — low cost, high leverage, schedule for next minor |
| 🟡     | Mid-term bet — needs design work and benchmarks |
| 🔵     | Long-term research — branch, no shipping commitment (👍 vote to prioritize) |
| 🔴     | Speculative — listed for completeness, do not start |

## Index

### 0.4.x — Geometric memory

| Status | Doc | Theme |
|--------|-----|-------|
| 🟢 | [modern-embedders.md](modern-embedders.md) | Drop-in upgrade to bge / gte / jina ONNX |
| 🟢 | [gliner-extractor.md](gliner-extractor.md) | Zero-shot multilingual NER backend |
| 🟢 | [laplacian-pe.md](laplacian-pe.md) | Real graph features for the GNN pruner |
| 🟢 | [ppr-retrieval.md](ppr-retrieval.md) | HippoRAG-style Personalized PageRank retrieval |
| 🟢 | [learned-srmkg-weights.md](learned-srmkg-weights.md) | Calibrate SR-MKG locally from real decisions |
| 🟡 | [hyper-relational-schema.md](hyper-relational-schema.md) | Qualifiers as first-class graph citizens |
| 🟡 | [typed-retrieval-planner.md](typed-retrieval-planner.md) | Query classifier → retrieval strategy |
| 🟡 | [client-llm-bridge.md](client-llm-bridge.md) | Explicit provider bridge to a client-hosted LLM adapter |

### 0.5.x — Learned consolidation

| Status | Doc | Theme |
|--------|-----|-------|
| ✅ | [hitl-prune-review.md](hitl-prune-review.md) | Human-in-the-loop golden dataset → learned GNN pruner (shipped 0.2.0) |
| 🟡 | [retrieval-success-consolidation.md](retrieval-success-consolidation.md) | Episodic→semantic consolidation in Night Gardener |

### Research branches (no shipping commitment — 👍 vote to prioritize)

Principled but **unproven**: these add surface area without demonstrated ROI for
a small, local-first project, so they sit off the shipping roadmap. The design
docs stay so the thinking is preserved and demand stays visible. **Vote by
adding a 👍 reaction on the item's tracking issue** — open one on
[GitHub Issues](https://github.com/xusliebana/hydramem/issues) if it doesn't
exist, or start a thread in
[Discussions](https://github.com/xusliebana/hydramem/discussions). An item
graduates back onto a milestone only when it gathers real demand **and** ships
with a benchmark that proves the ROI.

| Status | Doc | Theme |
|--------|-----|-------|
| 🔵 | [rgcn-edge-scorer.md](rgcn-edge-scorer.md) | R-GCN / CompGCN edge scorer replacing heuristic LightGNN |
| 🔵 | [spectral-community-summaries.md](spectral-community-summaries.md) | Local equivalent to GraphRAG community summaries |
| 🔵 | [local-lora-embedder.md](local-lora-embedder.md) | On-device LoRA fine-tuning over verified relations |
| 🔵 | [reasoning-motifs.md](reasoning-motifs.md) | Privacy-safe abstraction of reasoning patterns |
| 🔵 | _no design doc yet_ — active-VoG bandit | Which borderline relations deserve the LLM call |
| 🔵 | _no design doc yet_ — heat-kernel scoring | Heat-kernel implicit-relation candidate scoring |

### Anti-patterns (documented to be explicit)

| Status | Doc | Theme |
|--------|-----|-------|
| 🔴 | [anti-patterns.md](anti-patterns.md) | Things HydraMem deliberately will not do |

## Cross-cutting principles every PR must respect

1. **Honesty contract.** No fake metrics, no random fallbacks dressed up
   as scores, no inventing relations when there is no evidence. See the
   Night Gardener "honesty contract" comment in
   [`hydramem/garden/inferrer.py`](../../../hydramem/garden/inferrer.py).
2. **Local-first.** Optional heavy backends must be guarded behind extras
   in `pyproject.toml` and degrade gracefully (the LightGNN heuristic
   fallback in [`hydramem/gnn_prune.py`](../../../hydramem/gnn_prune.py) is the
   pattern to copy).
3. **No CoT capture.** Sessions store the *user query* and the *grounded
   context returned by HydraMem*. Any new feature that touches sessions
   must preserve this. Reasoning trajectories may be modelled **only as
   sequences of public graph nodes/relations**, never as client text.
4. **Auditability.** Every new metric must show up in
   `hydramem stats --raw` or `hydramem garden-status --json` so users can
   verify claims event-by-event.
