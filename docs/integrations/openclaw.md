# OpenClaw

Give your [OpenClaw](https://github.com/openclaw/openclaw) / ClawHub agents access
to HydraMem's verified local memory and knowledge graph.

## Prerequisites

- HydraMem on `$PATH` (`hydramem --version`).
- OpenClaw installed.

## Connect (MCP)

Add HydraMem as an MCP server via the CLI:

```bash
openclaw mcp set hydramem '{"command":"hydramem","args":["serve","--transport","stdio"]}'
```

??? note "Or edit the config directly"
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

Once connected, OpenClaw agents get all **18 tools** plus HydraMem's memory
protocol. Encourage the agent (via its system prompt / skill) to:

1. **Never guess** — query `hydra_search_tool` or `graph_only_search_tool` before
   confidently answering questions about past work.
2. **Persist decisions** — call `remember` when something is decided, so it
   survives across sessions (verified before storage).
3. **Grow the graph** — `create_relation` / `delete_relation` to curate facts.

This pairs autonomous code execution with persistent, high-recall, **local** memory.

## Verify

```bash
hydramem search "something the agent worked on"
hydramem stats --last-7d
```

## See also

- [MCP tools reference](../mcp-tools-reference.md) · [Night Gardener](../night-gardener.md)
