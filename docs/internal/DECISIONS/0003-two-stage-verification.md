# 3. Two-stage relation verification (SR-MKG + VoG)

- **Status:** Accepted (retroactively documented)
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

Candidate relations come from regex/NER extraction, agent submissions, and offline
inference. Writing unverified relations into the graph causes hallucinated edges
to compound over time. We need a filter that is cheap enough to run on every
candidate but precise enough to block bad edges — without making an LLM call
mandatory.

## Decision

We will verify **relations** in two stages:

1. **SR-MKG** — a pure-Python, topological scorer using graph structure and
   heuristic weights. No LLM. Cheap, deterministic, runs on every candidate.
2. **VoG** — an LLM groundedness check, applied to borderline candidates.

The **chunk** path inside `hydra_search` uses a **vector-similarity** prefilter
(+ VoG), *not* SR-MKG. The honest contract: when there is no real evidence, the
pipeline emits **zero** relations rather than guessing.

## Consequences

- Positive: most bad edges are rejected without an LLM call; the system degrades
  gracefully when no LLM is configured; behaviour is auditable.
- Trade-off: SR-MKG weights are heuristic and can silently regress quality —
  changes here are a designated risky area and require calibration tests.
- Obligation: keep the SR-MKG-vs-chunk distinction documented to avoid the common
  misconception that chunks go through SR-MKG.

## References

- [../verification.md](../../verification.md), [../CONSTRAINTS.md](../CONSTRAINTS.md),
  `tests/test_verify.py`, `tests/test_calibration.py`
