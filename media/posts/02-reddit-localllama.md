# Reddit — r/LocalLLaMA

**TÍTULO:**
```
I built a 100% local memory layer for my AI agents — didn't want my codebase
context living in someone's cloud
```

**CUERPO:**
```
Like a lot of you, I run local models (Ollama) and I got tired of "agent memory"
products that quietly send everything to a hosted service. So I built HydraMem: a
local-first memory layer that plugs into any MCP client (Claude Desktop, Cursor,
OpenCode).

How it works:
- Hybrid retrieval: vector (LanceDB) + graph traversal + a BM25 lexical arm, fused
  with RRF.
- Two-stage verification before anything is trusted: a topological relation scorer
  (SR-MKG) + an optional LLM groundedness check (VoG). With no LLM available it says
  "n/a", never a fabricated score.
- A "Night Gardener" that refines the graph offline and emits zero relations when
  there's no evidence.

Honest part (this sub will call out hype, so): the bundled benchmark is a small
reproducible sanity check — hybrid more than triples MRR over dense-only on a
keyword-aligned set with a stub embedder. That isolates the lexical+graph
contribution; it's NOT a SOTA claim. Public dataset run is in progress.

Local by default, zero exfiltration, MIT, ~5k LOC. Works with Ollama out of the box.
Repo + 30s demo: <link>

Would love feedback from people running bigger local corpora.
```

**NOTAS:** lee las reglas del sub (self-promo) · primera persona · responde como humano.
