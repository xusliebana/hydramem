# X/Twitter — Hilo de lanzamiento

> Publícalo el día del Show HN. El **GIF va en el tweet 1**.

```
1/ I built HydraMem: 100% local, private long-term memory for your AI coding agent.
Graph + vector search, runs on your machine, zero cloud by default.
MIT, ~5k LOC. 🧵
[ADJUNTA EL GIF DE 30s AQUÍ]

2/ The problem: "agent memory" tools are great… until you realize your codebase
context is now living in someone else's cloud. I wanted memory that never leaves my
machine.

3/ How it works:
• Hybrid retrieval: vector + graph + BM25 (RRF fusion)
• Two-stage verification before trusting anything
• A "Night Gardener" that refines the graph overnight
All local. Works with Claude Desktop, Cursor, OpenCode via MCP.

4/ The part I'm proud of: it's HONEST.
• Emits ZERO relations when there's no evidence
• `hydramem stats --raw` audits every token saved (~70% vs naive RAG)
• The shipped benchmark is a sanity check, not a fake SOTA number

5/ It's small enough to actually read in an afternoon (~5k LOC). Not a black box.
Two-stage verification (topological + groundedness), 18 MCP tools, Python 3.11–3.13.

6/ It's open source (MIT) and local-first by design. If you run local models with
Ollama, it plugs right in.
⭐ + teardown welcome: <repo>
(Show HN in comments 👇)
```

**NOTAS:** etiqueta con moderación a Ollama/FastMCP/MCP.
