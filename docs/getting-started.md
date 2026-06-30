# Getting Started

This guide walks you through installing HydraMem, ingesting your first documents, and running your first query.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python ≥ 3.11 | `python3 --version` |
| [uv](https://github.com/astral-sh/uv) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com/) | Optional but recommended for local LLM |

## Step 1 — Install HydraMem

```bash
# Install the CLI from PyPI (recommended)
uv tool install hydramem
# …or: pip install hydramem
# …or: pipx install hydramem

# Scaffold a workspace (config.yml, kms/, data/ + an MCP snippet)
hydramem init ~/my-memory
cd ~/my-memory
```

> **From source instead?** `git clone https://github.com/xusliebana/hydramem && cd hydramem`,
> then `cp config.yml.example config.yml`, `cp .env.example .env`, `uv sync`, and
> prefix the commands below with `uv run`.

## Step 2 — Pull a local model (optional)

```bash
ollama pull gemma4:e4b
```

If you prefer to use OpenAI or Anthropic instead of a local model, skip this step and edit `config.yml`:

```yaml
llm:
  provider: openai  # or "anthropic"
  external:
    provider: openai
    api_key_env: HYDRAMEM_OPENAI_KEY
    model: gpt-4o-mini
```

Then export the API key:

```bash
export HYDRAMEM_OPENAI_KEY=sk-...
```

## Step 3 — Start the MCP server

```bash
hydramem serve                      # stdio by default — ideal for MCP clients
# hydramem serve --transport http   # HTTP on http://0.0.0.0:3000/mcp
```

## Step 4 — Add it to your AI client

### OpenCode (Ollama)

```json
{
  "provider": { "ollama": { "model": "gemma4:e4b" } },
  "mcp": {
    "hydramem": { "type": "http", "url": "http://localhost:3000/mcp" }
  }
}
```

### OpenCode (Claude)

```json
{
  "provider": {
    "anthropic": {
      "api_key_env": "ANTHROPIC_API_KEY",
      "model": "claude-sonnet-4-20250514"
    }
  },
  "mcp": {
    "hydramem": { "type": "http", "url": "http://localhost:3000/mcp" }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "hydramem": { "command": "hydramem", "args": ["serve", "--transport", "stdio"] }
  }
}
```

## Step 5 — Ingest documents

Place Markdown files in `kms/`, then:

```bash
hydramem ingest ./kms
```

Or from your AI client: *"Ingest all documents in ./kms"* — the agent will use the `hydramem-ingest` skill.

## Step 6 — Query

From your AI client, try:

- *"What does my documentation say about the Night Gardener?"*
- *"How are LadybugDB and LanceDB related?"*

The agent will use `hydramem-query` or `hydramem-reason` skills automatically.

## Step 7 — View stats

```bash
hydramem stats --last-7d
hydramem garden-status
```

`hydramem stats` gives you the token-savings dashboard plus a summary of Night Gardener activity. Use `hydramem garden-status` for the Garden-only view.

## Next steps

- Read [Configuration](configuration.md) for advanced YAML settings
- Read [Night Gardener](night-gardener.md) to understand autonomous learning
- Read [Architecture](architecture.md) for the full system design
- Run `uv run python scripts/dogfood.py` to see HydraMem eat its own docs
