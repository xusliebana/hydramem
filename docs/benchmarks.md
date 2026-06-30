# Benchmarks

> Status: a small **local retrieval benchmark is implemented and runs offline**
> (see below), now with an **optional LLM judge** (`--judge`). The
> **dataset-scale** harness (`ingest` / `run` / `report`) is now **implemented**
> too: HotpotQA downloads directly, and any dataset (LongMemEval / MuSiQue) can
> be supplied via `--from-file` in the normalized schema. Headline numbers still
> require running it on a networked machine with a corpus + a judge LLM. This
> page is intentionally honest about what is, and is not, currently measured.

## Goals

A reproducible benchmark must answer three questions:

1. **Does the Night Gardener actually improve answer quality** over a session
   window, or is it churn?
2. **Does the SR-MKG + VoG pipeline lower hallucination rate** vs a vanilla
   top-k vector RAG?
3. **What does HydraMem cost** in tokens, latency, and disk vs the same
   vanilla baseline?

## Local retrieval benchmark (offline, reproducible)

A small, self-contained benchmark ships in the repository so anyone can measure
retrieval quality **with zero downloads and no LLM judge**. It ingests a fixture
corpus (`scripts/bench_data/corpus/`) and scores ten labelled queries
(`scripts/bench_data/queries.json`) under three ablation conditions, reporting
Recall@{1,3,5} and MRR.

```bash
# Real embedder (downloads ~80 MB ONNX model on first run)
uv run python scripts/benchmark.py local

# Fully offline + deterministic (hash-based stub embedder)
HYDRAMEM_EMBEDDER=stub uv run python scripts/benchmark.py local --json reports/local.json
```

Add `--judge` to layer an **LLM-judged answerability** metric on top — for each
condition it asks the configured LLM whether the retrieved context answers the
question. It follows the same honesty contract as VoG: with no LLM available it
reports `n/a (no LLM)` (coverage 0), never a fabricated score.

```bash
uv run python scripts/benchmark.py local --judge        # needs Ollama or an API key
```

Example run with the **offline stub embedder** — dense vectors are near-random
here, so the numbers isolate the lexical + graph contribution rather than make a
quality claim about the dense model:

| Condition | R@1 | R@3 | R@5 | MRR |
|-----------|-----|-----|-----|-----|
| `vector_only` | 0.00 | 0.30 | 0.50 | 0.16 |
| `hybrid_no_bm25` | 0.00 | 0.30 | 0.50 | 0.17 |
| `hybrid_full` | 0.30 | 0.70 | 0.80 | 0.52 |

The full hybrid (vector + graph + BM25) more than triples MRR over dense-only on
this keyword-aligned set — an honest, reproducible demonstration that the BM25
arm earns its place, especially when embeddings are weak.
[`tests/test_benchmark.py`](../tests/test_benchmark.py) runs this offline as a
regression guard.

This is a **sanity benchmark**, not a SOTA dataset result. The dataset-scale
experiment below remains the goal for headline numbers.

## Local LongMemEval results (measured)

A real, locally-run slice of **LongMemEval (`s`)** — faithful per-question
haystack, `all-MiniLM-L6-v2`, no LLM judge. HydraMem's hybrid retrieval (vector
+ graph + BM25) beats naive dense top-k across Recall@{1,3,5} and MRR. Full
table, caveats and reproduce command: **[internal/benchmark-results.md](https://github.com/xusliebana/hydramem/blob/main/docs/internal/benchmark-results.md)**;
raw artifact: [reports/longmemeval-local.json](../reports/longmemeval-local.json).
Driver: [`scripts/longmemeval_local.py`](../scripts/longmemeval_local.py).

## Datasets

| Dataset                                                                | Why it fits                                                 |
|------------------------------------------------------------------------|-------------------------------------------------------------|
| [LongMemEval](https://github.com/xiaowu0162/LongMemEval)               | Long-horizon memory, multi-session reasoning                |
| [MuSiQue](https://github.com/StonyBrookNLP/musique)                    | Multi-hop QA with annotated reasoning chains                |
| [HotpotQA](https://hotpotqa.github.io/) (distractor split)             | Classic multi-hop, gives a familiar reference point         |

Datasets are downloaded by `scripts/benchmark.py` on demand; nothing is
shipped in the repository.

## Conditions

| Condition                | Description                                                                |
|--------------------------|----------------------------------------------------------------------------|
| `naive_topk`             | Plain vector top-k, no graph, no verification                              |
| `hydra_search_no_garden` | Full hybrid + verification, no Night Gardener                              |
| `hydra_search_garden`    | Full hybrid + verification + 3 Night Gardener cycles on the train split    |

## Metrics reported

- **Recall@5** against gold support passages (when available).
- **Factual accuracy**: GPT-4o-judge with the rubric from
  [Patronus Lynx](https://www.patronus.ai/blog/lynx-state-of-the-art-open-source-hallucination-detection-model).
- **Hallucination rate**: 1 − accuracy on questions whose gold answer is
  expressible from the corpus.
- **Tokens injected**: actual prompt token count of the assembled context.
- **Latency** p50 / p95.
- **VoG / SR-MKG audit**: precision and recall of the filter on a hand-coded
  100-relation sample.

## Reproducing the run

```bash
# HotpotQA downloads directly; MuSiQue / LongMemEval are supplied via --from-file
# (normalized schema: {"corpus": {doc_id: text},
#  "items": [{id, question, answer, gold_doc_ids}]}).

# 1. (optional) pre-download + cache the dataset
uv run python scripts/benchmark.py ingest --dataset hotpotqa

# 2. Run all three conditions (add --judge for LLM-judged faithfulness)
uv run python scripts/benchmark.py run --dataset hotpotqa --limit 200 \
    --conditions naive_topk hydra_search_no_garden hydra_search_garden \
    --output reports/hotpotqa-2026-XX.json

# 3. Render the Markdown summary
uv run python scripts/benchmark.py report reports/hotpotqa-2026-XX.json \
    > docs/internal/benchmark-results.md
```

The `local`, `ingest`, `run` and `report` subcommands are all implemented.
Publishing headline dataset numbers still requires a networked machine (corpus
download) and, for faithfulness, an LLM judge — run it and report honestly.

## What we will publish

For each dataset we plan to include:

- A table comparing the three conditions on every metric above.
- A short narrative paragraph explaining where HydraMem **wins** and where it
  **loses** (we expect to lose on questions answered by a single literal
  chunk).
- The exact commit hash, dataset version, LLM model and judge model used.
- The raw `reports/*.json` files committed to the repo for re-analysis.

We will resist the temptation to cherry-pick metrics that look good. If the
Night Gardener does not move the needle, the README will say so.
