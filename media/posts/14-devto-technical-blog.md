# Blog técnico — Dev.to / Hashnode / Medium

**TÍTULO:**
```
Building local-first memory for AI agents: the honest version
```
**TAGS:** `ai`, `opensource`, `python`, `mcp`

**ESTRUCTURA (escribir ~1.000–1.500 palabras):**

```
## The itch
Agents forget between sessions. Cloud memory services fix that — by taking your
codebase context off your machine. I didn't want that trade-off.

## What I built
HydraMem: local-first memory over MCP. Hybrid retrieval (vector + graph + BM25/RRF),
two-stage verification, offline Night Gardener. ~5k LOC, MIT.

## The architecture
(incluye el diagrama ASCII de TECHNICAL_OVERVIEW.md)
- Ingest → chunk → extract entities → embed → store (LanceDB + graph)
- Search → vector + BFS graph expansion + lexical, fused, then verified
- Verify → SR-MKG (topological) + VoG (LLM groundedness)
- Night Gardener → offline inference/pruning

## The honesty contract (la parte que casi nadie escribe)
- Zero relations without evidence
- `stats --raw` audits token savings (~70% vs naive RAG)
- The bundled benchmark is a sanity check, NOT SOTA. Muestra la tabla. Explica el
  caveat del stub embedder. Enlaza el plan del dataset público.

## What it does NOT do (yet)
Sé explícito. Esto construye más confianza que cualquier lista de features.

## Try it
`uv tool install …`, `hydramem init`, snippet de config MCP. Repo + GIF.

## Lessons
1 párrafo honesto sobre una decisión de diseño (p.ej. por qué local-first, por qué
verificar relaciones).
```

**CTA:** ⭐ the repo, tell me where it breaks.
**NOTA:** cross-post en las 3 plataformas con canonical URL a una.
