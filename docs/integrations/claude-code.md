# Claude Code

Connect [Claude Code](https://docs.anthropic.com/en/docs/claude-code) to HydraMem
so Claude can search and grow a local, verified memory of your project.

## Prerequisites

- HydraMem installed and on `$PATH` (`hydramem --version` to verify):
  ```bash
  uv tool install hydramem    # or: pip install hydramem / pipx install hydramem
  hydramem init ~/my-memory && cd ~/my-memory
  ```
- Claude Code installed (`claude --version`).

## Connect (MCP)

The fastest path — register HydraMem's stdio MCP server with one command:

```bash
claude mcp add hydramem -- hydramem serve --transport stdio
```

Restart Claude Code, then run `/mcp` and confirm **hydramem** is `connected`.

??? note "Manual config (alternative)"
    Add to your Claude Code MCP config instead:
    ```json
    {
      "mcpServers": {
        "hydramem": {
          "command": "hydramem",
          "args": ["serve", "--transport", "stdio"]
        }
      }
    }
    ```

## How it works

With HydraMem connected, Claude Code can:

- **Search before answering** — `hydra_search_tool` / `priming_context_tool`
  retrieve verified context from your local graph + vectors.
- **Remember mid-conversation** — the `remember` tool persists a verified fact
  ("we decided to use JWT for auth") into the knowledge graph.
- **Ingest docs** — `ingest_directory_tool` adds Markdown notes on demand.
- **Self-report savings** — `hydramem_stats_tool` shows token savings.

Just ask: *"What did we decide about auth last month?"* — Claude searches the
palace first.

## Keep memory growing

Two complementary options:

1. **Agent-driven (default, zero setup):** tell Claude to *"remember"* key
   decisions; it calls the `remember` tool. Everything is verified before storage.
2. **Hooks (auto-save):** wire a `Stop` hook that re-ingests your notes after each
   turn — see **[Claude Code retention](claude-code-retention.md)**.

## Verify

```bash
# In Claude Code:
/mcp                      # hydramem → connected
# From a terminal:
hydramem search "auth decision" --project myproject
hydramem stats --last-7d
```

## Troubleshooting

- **`hydramem` not found** → it isn't on `$PATH`. Reinstall with `uv tool install`
  / `pipx`, or use the absolute path to the console script in the MCP `command`.
- **No results** → ingest first: `hydramem ingest ./kms --project myproject`.
- **VoG says `n/a`** → no local LLM reachable. Pull one: `ollama pull gemma4:e4b`
  (verification degrades honestly; retrieval still works).

## See also

- [Claude Code retention](claude-code-retention.md) — auto-save hooks + backfill.
- [MCP tools reference](../mcp-tools-reference.md) · [Configuration](../configuration.md)
