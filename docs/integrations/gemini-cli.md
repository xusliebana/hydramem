# Gemini CLI

Connect [Gemini CLI](https://github.com/google-gemini/gemini-cli) to HydraMem for
local, verified memory.

## Prerequisites

- HydraMem on `$PATH` (`hydramem --version`).
- Gemini CLI installed and configured.

## Connect (MCP)

Register HydraMem as a user-scoped MCP server:

```bash
gemini mcp add --scope user hydramem -- hydramem serve --transport stdio
```

!!! warning "Use the console script"
    `hydramem` resolves to the installed console script (isolated environment).
    If Gemini launches from a context without your `$PATH`, use the absolute path
    to the `hydramem` binary (`which hydramem`).

??? note "Manual config — `~/.gemini/settings.json`"
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

## Optional: auto-save hook

Gemini CLI can run a command before context compression. Use it to re-ingest your
knowledge directory (see the script in
[Claude Code retention](claude-code-retention.md#2-auto-save-with-a-stop-hook)):

```json
{
  "hooks": {
    "PreCompress": [{
      "matcher": "*",
      "hooks": [{ "type": "command", "command": "/absolute/path/to/.hydramem/hooks/save.sh" }]
    }]
  }
}
```

## Usage

Once connected, Gemini CLI will:

- Start the HydraMem MCP server on launch.
- Use `hydra_search_tool` to find relevant past context.
- Call `remember` to persist decisions (when prompted to).

### Verify

In a Gemini CLI session:

- `/mcp list` — confirm `hydramem` is **CONNECTED**.
- From a terminal: `hydramem search "…"` and `hydramem stats --last-7d`.

## See also

- [MCP tools reference](../mcp-tools-reference.md) · [Antigravity](antigravity.md) · [Configuration](../configuration.md)
