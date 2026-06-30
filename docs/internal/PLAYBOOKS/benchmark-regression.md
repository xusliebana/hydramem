# Playbook: Benchmark a retrieval / algorithm change

**When you change an algorithm that affects retrieval, prove it made retrieval
better — not worse — with a before/after benchmark.** This is the Feedback gate
for quality regressions (the test suite proves *correctness*; this proves
*quality*).

## When this is required

Run this playbook whenever a change touches a **retrieval-affecting** module
(see [../CODEMAP.md](../CODEMAP.md)):

- `hydramem/search.py` — ranking / hybrid fusion
- `hydramem/ppr.py` — Personalized PageRank retrieval
- `hydramem/verification/` — SR-MKG scorer, VoG groundedness
- `hydramem/garden/pruner.py`, `hydramem/gnn_prune.py` — edge pruning (changes graph structure → changes retrieval)
- `hydramem/ingest/chunker.py` / `embedder.py` / `extractor.py` — what gets indexed
- any `hydramem/storage/**` change to a retrieval path

Examples that trigger it: *"a new pruning algorithm", "a new VoG variant", "a new
re-ranker", "a different chunker"*.

## What is measured

The shipped, **offline, reproducible** retrieval benchmark
([../../scripts/benchmark.py](../../../scripts/benchmark.py) `local`) scores 10
labelled queries over the fixture corpus and reports **Recall@{1,3,5}** and
**MRR** across three ablation conditions (`vector_only`, `hybrid_no_bm25`,
`hybrid_full`). `tests/test_benchmark.py` runs it as an always-on guard. Details
and honest caveats: [../benchmarks.md](../../benchmarks.md).

> **Determinism:** use the hash-based **stub embedder** (`HYDRAMEM_EMBEDDER=stub`)
> for the before/after gate so the comparison isolates *your* change. Do a second
> run with the **real** embedder (and `--judge`) for a quality signal.

## Procedure (before / after)

```bash
# 1. BASELINE — on a clean tree at the base commit (before your change).
HYDRAMEM_EMBEDDER=stub uv run python scripts/benchmark.py local > reports/before.txt
#    (or, equivalently, the convenience wrapper:)  nox -s bench

# 2. Apply your algorithm change, then re-run identically.
HYDRAMEM_EMBEDDER=stub uv run python scripts/benchmark.py local > reports/after.txt

# 3. Compare — every metric, side by side.
diff -u reports/before.txt reports/after.txt || true
```

Archive a machine-readable copy for the PR (and commit it if this is a published
comparison):

```bash
HYDRAMEM_EMBEDDER=stub uv run python scripts/benchmark.py local --json reports/after.json
```

## Decide: better, worse, or neutral?

- **Better / neutral** → proceed. Paste both tables into the PR as evidence.
- **Worse** (Recall@k or MRR drops on a condition) → either:
  - justify the trade-off explicitly (e.g. fewer edges for lower latency / higher
    precision) in the PR and, if it is a permanent design choice, an
    [ADR](../DECISIONS/README.md); **or**
  - revert / iterate until retrieval is not worse.

Do not merge a silent quality regression. State the numbers honestly even when
they are unfavourable — that is the [honesty contract](../../../AGENTS.md).

## Special cases

- **VoG / SR-MKG changes.** The `local` benchmark uses a *passthrough* verifier
  (it measures retrieval, not verification), so it will **not** capture a VoG/
  SR-MKG quality change. Additionally run the verifier audit:
  `uv run pytest tests/test_calibration.py tests/test_verify.py` and the
  precision/recall check described in [../verification.md](../../verification.md).
- **Pruning changes.** These alter graph structure; the `hybrid_*` conditions
  reflect the net effect on retrieval. Watch `hybrid_full` MRR especially.
- **Public dataset-scale benchmark.** The `ingest` / `run` / `report` subcommands
  for LongMemEval / MuSiQue / HotpotQA are **scaffolds today** (see
  [../benchmarks.md](../../benchmarks.md)). When they are implemented, repeat the
  same before/after comparison on the dataset for headline numbers — until then,
  the local benchmark is the gate.

## Record evidence

Attach the before/after tables to the PR, link them from
[../DEFINITION_OF_DONE.md](../DEFINITION_OF_DONE.md), and note the embedder and
(if used) judge model. Commit `reports/*.json` only for runs you intend to
publish.
