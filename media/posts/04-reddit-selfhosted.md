# Reddit — r/selfhosted

**TÍTULO:**
```
Self-hosted memory for AI agents — graph+vector, runs entirely on your box (MIT)
```

**CUERPO:**
```
If you self-host LLMs/agents and want them to *remember* across sessions without a
SaaS, HydraMem might fit. It's a local knowledge base (graph + vector) for AI agents
with a single mounted /data volume, Docker image, and an MCP server.

- 100% local, zero exfiltration by default.
- Hybrid search + two-stage verification (keeps the graph clean).
- Offline "Night Gardener" refines things overnight.
- `hydramem stats` dashboard so you can see token savings (auditable, ~70% vs naive RAG).

MIT, Python 3.11–3.13, ~5k LOC (small enough to actually read/audit). Docker compose
included.
Repo + screenshots: <link>
Curious what storage layouts people here would want for backups.
```
