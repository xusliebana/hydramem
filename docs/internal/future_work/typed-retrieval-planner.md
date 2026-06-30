# Typed Retrieval Planner 🟡

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Mid-term bet — small classifier, big retrieval quality lift

## Why it matters

Every query in `hydra_search` follows the same pipeline regardless of
its information need: vector top-k → BFS → SR-MKG → VoG. But a *factoid
lookup* ("what does X mean?") and a *multi-hop causal* question ("how
does X cause Y?") need very different retrieval strategies.
A small **query classifier** that picks the strategy can:

- skip VoG for simple definitions (cost saving)
- favour PPR over BFS for multi-hop
- engage community summaries (see
  [spectral-community-summaries.md](spectral-community-summaries.md))
  for global "what does the corpus know about X" queries

Even a coarse 4-class classifier yields measurable wins.

## State of the art

- **Self-RAG / Adaptive-RAG** (Asai et al., 2023; Jeong et al., 2024) —
  decide when to retrieve and at what depth
- **Plan-and-Solve** prompting (Wang et al., 2023) — query decomposition
- **Question Type Taxonomies** — Trec QA, MS-MARCO labels
- **GLiNER-style zero-shot classifiers** — applicable as a tiny encoder
  for query intent

## Proposed architecture

Classes (configurable):

| Class | Strategy |
|-------|----------|
| `factoid` | vector top-k=3, no BFS, optional VoG only on contradiction signal |
| `multi_hop` | PPR + BFS hybrid, max_hops=3, full VoG |
| `global_overview` | Hit community summaries first, then PPR for drill-down |
| `comparative` | Two-seed PPR (one per entity), shortest-path |
| `temporal` | Filter by `valid_from`/`valid_to` qualifiers (depends on hyper-relational schema) |

Classifier options:

1. **Zero-shot via small encoder**: `bge-small` + cosine to class prompts.
   Cheap, no training data required.
2. **Few-shot via local LLM**: 1-shot prompt to Ollama; cached per query
   prefix.

Default to (1) for latency.

```yaml
search:
  planner:
    enabled: true
    backend: zero_shot       # zero_shot | llm
    overrides:
      always_use_strategy: null  # debug knob
```

## Risks

- **Misclassification** sending complex queries to a cheap path. Mitigate
  by adding a `confidence` threshold below which the planner falls
  through to the current default pipeline.
- **Hidden cost** of always running the classifier — keep it < 5 ms.
- **Telemetry noise**: log the chosen strategy for every query so users
  can audit.

## Computational cost

- Zero-shot encoder path: 5–15 ms per query
- LLM path: 100–300 ms (Ollama small model)

## Privacy implications

None.

## Local-first viability

Excellent.

## Suggested implementation strategy

1. Add `hydramem/search/planner.py` with `QueryPlanner` ABC and a
   `ZeroShotPlanner` impl using the existing embedder.
2. Define `RetrievalStrategy` dataclass (params for traversal, top_k,
   skip_vog, etc.).
3. Wire planner into `hydra_search` upstream of retrieval.
4. Telemetry: `planner_strategy`, `planner_confidence`.
5. Benchmark on dogfood corpus + MuSiQue subset.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/search/planner.py` | **NEW** — `QueryPlanner`, `ZeroShotPlanner`, `LLMPlanner` |
| [`hydramem/search.py`](../../../hydramem/search.py) | Hook planner before retrieval |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `SearchConfig.planner` |
| [`hydramem/server.py`](../../../hydramem/server.py) | Optional `strategy_override` arg |
| `tests/test_search.py` | Strategy dispatch tests |

## References

- Asai et al., *Self-RAG: Learning to Retrieve, Generate and Critique*,
  ICLR 2024
- Jeong et al., *Adaptive-RAG: Learning to Adapt Retrieval-Augmented LLMs
  through Question Complexity*, NAACL 2024
- Wang et al., *Plan-and-Solve Prompting*, ACL 2023
