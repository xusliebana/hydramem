# Benchmark results (measured)

> Real, locally-measured numbers. This file is updated by re-runs; the raw
> machine-readable artifacts live in [`reports/`](../../reports/). Honesty
> contract: every number here is measured, never hand-wavy — caveats included.

## LongMemEval (`s`) — local retrieval

- **Dataset:** [LongMemEval](https://github.com/xiaowu0162/LongMemEval) `longmemeval_s`
  (HuggingFace `xiaowu0162/longmemeval`), run **100% locally**.
- **Setting:** *faithful per-question haystack* — each question is evaluated
  against **its own** session haystack (the native LongMemEval setting), with
  real distractors (median **52** sessions/question).
- **Embedder:** `fastembed:all-MiniLM-L6-v2` (default, ONNX, CPU).
- **Metric:** session-level **Recall@k** over the top-5 distinct sessions of the
  retrieved ranking, plus **MRR**. **No LLM judge** (retrieval metrics only).
- **Raw artifact:** [reports/longmemeval-local.json](../../reports/longmemeval-local.json).

### Run: 30 questions (2026-06-30)

| Condition | R@1 | R@3 | R@5 | MRR | p50 ms | p95 ms |
|-----------|-----|-----|-----|-----|--------|--------|
| `naive_topk` (dense vector top-k) | 0.767 | 0.900 | 0.933 | 0.834 | 15 | 24 |
| `hydra_search_no_garden` (vector + graph BFS + BM25, RRF) | **0.833** | **0.967** | **0.967** | **0.894** | 140 | 161 |

**Reading.** HydraMem's hybrid retrieval beats naive dense top-k on every
metric: **R@1 +0.066, R@3 +0.067, R@5 +0.034, MRR +0.060** — the lexical (BM25)
and graph arms recover gold sessions the dense embedder alone misses, on a
multi-session memory task.

**Honest caveats.**
- 30/500 questions — a small sample with variance; treat as a signal, not a
  leaderboard claim. (A larger run supersedes this table.)
- This measures **retrieval recall of the gold session**, *not* answer accuracy
  (LongMemEval's QA-accuracy leaderboard needs an LLM judge over the full
  pipeline — different metric).
- VoG verification was effectively off (no local Ollama model). It does not
  affect recall (measured pre-verification) but inflated wall-clock time.

### Reproduce

```bash
uv run python scripts/longmemeval_local.py --n 30 --k 20 \
    --output reports/longmemeval-local.json
```
