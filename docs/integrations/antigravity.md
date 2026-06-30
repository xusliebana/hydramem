# Antigravity

Connect Google's [Antigravity IDE](https://antigravity.google/) to HydraMem so the
agent reads a local, verified memory before acting.

## Prerequisites

- HydraMem on `$PATH` (`hydramem --version`).
- Antigravity installed (`~/.gemini/` exists).

## Connect (MCP)

Antigravity reads MCP servers from its config under `~/.gemini/`. Add HydraMem:

```json
// ~/.gemini/config/mcp_config.json  (or the IDE's MCP store "add server" dialog)
{
  "mcpServers": {
    "hydramem": {
      "command": "hydramem",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

Restart Antigravity — **hydramem** should appear in the MCP store with its 18
tools.

## Optional: lifecycle hooks

Antigravity exposes a **Stop** hook (after the agent loop ends) and a
**PreInvocation** hook (before the first model call). You can mirror the
HydraMem pattern:

- **Save (Stop):** re-ingest your knowledge dir — reuse `~/.hydramem/hooks/save.sh`
  from [Claude Code retention](claude-code-retention.md#2-auto-save-with-a-stop-hook).
- **Wake (PreInvocation):** prime the agent once per conversation, e.g. run
  `hydramem search "<workspace topic>"` and inject the result as context.

```json
// ~/.gemini/config/plugins/hydramem/hooks.json (illustrative)
{
  "hooks": {
    "Stop":          [{ "command": "/absolute/path/to/.hydramem/hooks/save.sh" }],
    "PreInvocation": [{ "command": "/absolute/path/to/.hydramem/hooks/wake.sh" }]
  }
}
```

A minimal `wake.sh` can call `hydramem search "$(basename "$PWD")" --project "$(basename "$PWD")"`
and echo the result.

!!! info "Honest note"
    HydraMem ships the MCP server and skills; it does **not** ship a packaged
    Antigravity plugin/installer today. The hooks above are example wiring around
    HydraMem's real CLI — adapt paths to your install.

## Verify

After restarting Antigravity:

1. The MCP store lists `hydramem` as a registered server.
2. `hydramem search "…"` returns your ingested context from a terminal.

## See also

- [Gemini CLI](gemini-cli.md) · [MCP tools reference](../mcp-tools-reference.md)
