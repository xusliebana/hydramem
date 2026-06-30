# Cursor

Two complementary layers for [Cursor](https://cursor.com/): the **MCP server**
(tools + search) and **hooks** (recall at session start, auto-save on stop).

## 1. MCP server

Add HydraMem to `~/.cursor/mcp.json` (user scope) or `.cursor/mcp.json` (project):

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

Reload Cursor (Settings → MCP) and confirm **hydramem** is connected with its 18
tools.

## 2. Cursor hooks (recall + auto-save)

Cursor fires lifecycle hooks you can use to (a) inject recall guidance at the
start of a chat and (b) re-ingest your notes as you work. Add `~/.cursor/hooks.json`
(user) or `.cursor/hooks.json` (project, version-controlled):

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      { "command": "/absolute/path/to/.hydramem/hooks/wake.sh" }
    ],
    "stop": [
      { "command": "/absolute/path/to/.hydramem/hooks/save.sh", "loop_limit": 1 }
    ],
    "preCompact": [
      { "command": "/absolute/path/to/.hydramem/hooks/save.sh" }
    ]
  }
}
```

- **`save.sh`** — re-ingest your knowledge dir (script in
  [Claude Code retention](claude-code-retention.md#2-auto-save-with-a-stop-hook)).
- **`wake.sh`** — emit recall guidance. Minimal example:

  ```bash
  #!/usr/bin/env bash
  # Tell the agent to search HydraMem before answering, scoped to this workspace.
  wing="$(basename "$PWD")"
  printf '{"additional_context":"Before answering about past work, call hydra_search_tool (project=%s)."}\n' "$wing"
  ```
  ```bash
  chmod +x ~/.hydramem/hooks/wake.sh
  ```

Cursor watches `hooks.json` and reloads on save; start a **new** conversation for
fresh hooks to take effect.

!!! info "Honest note"
    The `save.sh` hook ingests your **Markdown notes**, not Cursor's transcript
    file (its format is undocumented and HydraMem has no parser for it). The
    load-bearing capture path in HydraMem is the agent calling `remember` for
    verified decisions.

## Configuration knobs (for the example scripts)

| Env var | Default | Purpose |
|---|---|---|
| `HYDRAMEM_KMS_DIR` | `$PWD/kms` | Directory the save hook re-ingests |
| `HYDRAMEM_PROJECT` | `default` | Project namespace |

## Verify

```bash
cat ~/.cursor/hooks.json            # wiring present
hydramem search "…" && hydramem stats --last-7d
```

## See also

- [Claude Code retention](claude-code-retention.md) · [MCP tools reference](../mcp-tools-reference.md)
