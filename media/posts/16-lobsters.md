# Lobsters (lobste.rs)

> Requiere invitación. Audiencia técnica senior — valora rigor y honestidad, sin marketing.

**TAGS:** `ai`, `programming`, `privacy`, `show`

**TÍTULO:**
```
HydraMem: local-first memory for AI agents with two-stage relation verification
```

**TEXTO:**
```
Local-first memory layer for LLM agents over MCP. Hybrid retrieval (vector + graph +
BM25/RRF) followed by a topological relation scorer (SR-MKG) and an optional LLM
groundedness check (VoG) that reports "n/a" rather than fabricating a score. Offline
"Night Gardener" for inference/pruning. ~5k LOC, MIT, Python 3.11–3.13.

The bundled benchmark is an offline, reproducible sanity check (full hybrid > dense-only
on MRR), explicitly NOT a SOTA dataset result; a public MuSiQue/LongMemEval run is the
stated next step. Repo + architecture/verification docs: <link>. Teardowns welcome.
```
