# Reddit — r/mcp

**TÍTULO:**
```
HydraMem — an MCP server (18 tools) that gives your agent local, verified long-term memory
```

**CUERPO:**
```
Sharing an MCP server I built: HydraMem exposes 18 tools (ingest, hybrid search,
remember, graph queries, stats…) over FastMCP, so any MCP client gets persistent,
local memory.

Why it might be interesting to this sub:
- Local-first: no cloud calls by default, secrets from env only.
- Two-stage verification on relations (topological + LLM groundedness) so the graph
  doesn't fill up with junk edges.
- Auditable: `hydramem stats --raw` shows exactly what was injected/saved.
- Single-tenant by design; stdio + HTTP transport (Claude Desktop friendly).

Honest scope: it's an opinionated integration of known patterns (graph-RAG +
verification + offline learning), not a brand-new algorithm. MIT, ~5k LOC.

Config snippet for Claude Desktop / Cursor / OpenCode + 30s demo in the README: <link>
Feedback on the tool surface welcome — happy to adjust signatures before more people
depend on them.
```
