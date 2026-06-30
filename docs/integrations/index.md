# Integrations

HydraMem is **MCP-native**: it speaks the [Model Context Protocol](https://modelcontextprotocol.io/),
so any MCP-capable AI coding tool can use HydraMem as its long-term memory — 100 %
locally, with zero cloud calls by default.

Every integration below boils down to two ingredients:

1. **Run the server** — `hydramem serve` (stdio for desktop/CLI clients, or HTTP for shared/remote use).
2. **Point your tool at it** — add HydraMem to the tool's MCP config.

Once connected, your agent gets all **18 MCP tools** (search, graph traversal,
verification, the `remember` tool, ingestion, stats…). See the
[MCP tools reference](../mcp-tools-reference.md).

## Pick your tool

<div class="grid cards" markdown>

-   :material-robot-happy:{ .lg .middle } &nbsp;__[Claude Code](claude-code.md)__

    ---
    Native MCP via `claude mcp add`. Plus a [retention guide](claude-code-retention.md).

-   :material-google:{ .lg .middle } &nbsp;__[Gemini CLI](gemini-cli.md)__

    ---
    `gemini mcp add` + an optional save hook.

-   :material-rocket-launch:{ .lg .middle } &nbsp;__[Antigravity](antigravity.md)__

    ---
    Google's agentic IDE — MCP store + lifecycle hooks.

-   :material-cat:{ .lg .middle } &nbsp;__[OpenClaw](openclaw.md)__

    ---
    `openclaw mcp set` — memory for ClawHub agents.

-   :material-cursor-default-click:{ .lg .middle } &nbsp;__[Cursor](cursor.md)__

    ---
    MCP server + Cursor hooks (sessionStart / stop / preCompact).

-   :material-console:{ .lg .middle } &nbsp;__[OpenCode](../opencode-setup.md)__

    ---
    Local or Anthropic provider + HTTP MCP.

-   :material-microsoft-visual-studio-code:{ .lg .middle } &nbsp;__[GitHub Copilot](copilot.md)__

    ---
    VS Code agent mode via `.vscode/mcp.json`.

-   :material-server-network:{ .lg .middle } &nbsp;__[Remote / Team server](remote-server.md)__

    ---
    One shared HydraMem over HTTP for a whole team.

</div>

## How "remembering" works in HydraMem (honest contract)

HydraMem's memory model is **agent-driven** (see
[ADR-0005](https://github.com/xusliebana/hydramem/blob/main/docs/internal/DECISIONS/0005-agent-driven-ingestion.md)):
the agent decides what is worth keeping and calls the **`remember`** tool to
persist a verified fact mid-conversation, or ingests your Markdown notes with
`hydramem ingest`.

What this means, stated plainly:

- ✅ HydraMem ingests **Markdown documents** and **agent-submitted knowledge**
  (`remember`, `ingest_directory_tool`, `submit_session_extraction`).
- ✅ Every relation is verified (SR-MKG + VoG) before it enters the graph.
- ❌ HydraMem does **not** ship a raw transcript-miner that parses each tool's
  proprietary JSONL session files. "Auto-save" hooks below re-ingest your
  knowledge directory and nudge the agent to `remember` — they do not scrape the
  chat log. If a tool-native transcript miner matters to you, it's tracked as
  potential future work, not a shipped feature.
