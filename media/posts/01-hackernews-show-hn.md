# Show HN

**TÍTULO (≤80 chars):**
```
Show HN: HydraMem – Local, private memory for AI coding agents (MCP, ~5k LOC)
```
**URL:** el repo de GitHub.

**PRIMER COMENTARIO (publícalo nada más postear):**
```
Hi HN — I built HydraMem because I wanted long-term memory for my coding agents
(Claude Desktop / Cursor / OpenCode) without shipping my codebase context to a
cloud memory service. It's 100% local by default: hybrid graph + vector search,
two-stage verification (a topological relation scorer + an LLM groundedness check),
and an offline "Night Gardener" that refines the graph overnight.

What I want to be honest about, because HN deserves it:
- It is NOT the first memory system, graph-RAG, or hallucination filter. It's an
  opinionated *local-first* integration of those patterns.
- The Night Gardener emits ZERO relations when there's no real evidence — no fake
  edges to look busy.
- The headline "~70% token savings vs naive RAG" is auditable with
  `hydramem stats --raw`, not a marketing number.
- The shipped benchmark is a small reproducible *sanity* check (hybrid beats
  vector-only on MRR), NOT a SOTA dataset result. The public dataset run
  (MuSiQue/LongMemEval) is in progress and I won't claim numbers I haven't measured.

~5k LOC, MIT, Python 3.11–3.13. 18 MCP tools. Happy to go deep on the SR-MKG/VoG
pipeline, the storage layer (graph + vector), or why I went local-first. Feedback
and teardowns very welcome.
```

**NOTAS:** mar–jue 9–11am ET · responde todos los comentarios el mismo día · no pidas upvotes.
