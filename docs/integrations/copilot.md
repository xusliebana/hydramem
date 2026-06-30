# GitHub Copilot (VS Code)

Use HydraMem as a memory tool for **GitHub Copilot agent mode** in VS Code via MCP.

## Prerequisites

- HydraMem on `$PATH` (`hydramem --version`).
- VS Code with GitHub Copilot (agent mode / tools enabled).

## Connect (MCP)

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "hydramem": {
      "type": "stdio",
      "command": "hydramem",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

??? note "User-level (all workspaces)"
    Add the same `servers` entry to your VS Code user `mcp.json`
    (Command Palette → **MCP: Open User Configuration**).

??? note "HTTP transport (shared server)"
    If you run HydraMem over HTTP (`hydramem serve --transport http`), point VS Code at it:
    ```json
    {
      "servers": {
        "hydramem": { "type": "http", "url": "http://localhost:3000/mcp" }
      }
    }
    ```

Open the Copilot Chat **Agent** mode, click the tools picker, and enable the
**hydramem** tools.

## Built-in HydraMem skills for Copilot

This repository includes six Copilot skills for common memory workflows:

- `hydramem-ingest`
- `hydramem-ingest-smart`
- `hydramem-query`
- `hydramem-reason`
- `hydramem-link`
- `hydramem-garden`

See the full guide for when to use each one and how they handle context
injection/retrieval:
[GitHub Copilot Agent Skills](copilot-skills.md).

## Use it

Ask Copilot agent mode things like *"search our HydraMem memory for the auth
decision"* or *"remember that we switched to Postgres"*. It will call
`hydra_search_tool` / `remember` against your local palace.

## Verify

- VS Code → **MCP: List Servers** → `hydramem` is running.
- Terminal: `hydramem search "…"` · `hydramem stats --last-7d`.

## Troubleshooting

- **Server not starting** → check `hydramem --version` resolves; use the absolute
  path to the console script in `command` if VS Code's `PATH` differs.
- **No tools shown** → ensure agent mode is on and the server is enabled in the
  tools picker.

## See also

- [GitHub Copilot Agent Skills](copilot-skills.md) · [OpenCode](../opencode-setup.md) · [MCP tools reference](../mcp-tools-reference.md)
