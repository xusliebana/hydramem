# Reddit — r/ChatGPTCoding

**TÍTULO:**
```
Gave my coding agent long-term memory that's local + verified (works with Cursor/Claude Desktop)
```

**CUERPO:**
```
My agent kept "forgetting" project context between sessions, and the cloud memory
options meant shipping my codebase context off-machine. So I built HydraMem: local
memory over MCP that any client can use.

Practical wins for coding agents:
- Recall decisions/patterns across sessions (a `remember` tool to accumulate verified
  knowledge mid-conversation).
- ~70% fewer tokens vs naive RAG (auditable with `hydramem stats --raw`).
- Verification step so it doesn't "remember" hallucinated facts.

Setup is a config snippet for Cursor/Claude Desktop/OpenCode. Local, MIT, ~5k LOC.
30s demo + setup: <link>
Honest note: it's an integration of known patterns, not magic — and the bundled
benchmark is a sanity check, not a SOTA claim.
```
