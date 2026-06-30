# Reddit — r/MachineLearning

**FLAIR:** `[P] Project`

**TÍTULO:**
```
[P] HydraMem: local-first agent memory with two-stage relation verification (SR-MKG + VoG)
```

**CUERPO:**
```
Open-sourcing HydraMem, a local-first memory system for LLM agents that combines
hybrid retrieval (vector + graph + BM25/RRF) with a two-stage verification pipeline:

1) SR-MKG — a topological scorer over candidate relations (Jaccard neighborhood
   overlap, type boosts, isolation penalty; weights configurable/loggable for
   calibration).
2) VoG — an optional LLM groundedness check. Honesty contract: with no LLM it reports
   "n/a", never a fabricated score.

Plus an offline "Night Gardener" for relation inference/pruning (LightGNN spurious-edge
detection with a heuristic fallback), and per-relation provenance.

Reproducible sanity benchmark (offline, stub embedder): full hybrid > dense-only on
Recall@k/MRR — included as a regression test. This isolates the lexical+graph
contribution; it is NOT a SOTA dataset result. A public MuSiQue/LongMemEval run is
the next step and I'm deliberately not reporting numbers I haven't measured yet.

MIT, ~5k LOC, Python 3.11–3.13. Repo + docs (architecture, verification contract,
benchmark plan): <link>
Happy to discuss the scorer design and failure modes.
```
