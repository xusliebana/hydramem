# OpenCode Setup

This guide covers connecting HydraMem to [OpenCode](https://opencode.ai/) using either a **local Ollama model** or **Anthropic Claude** as the AI provider.

HydraMem acts as an MCP server — your AI client connects to it over HTTP and gains access to 16 knowledge-management tools.

---

## Prerequisites

1. HydraMem running: `uv run hydramem-server`
2. OpenCode installed: see [opencode.ai](https://opencode.ai/)

---

## Option A — OpenCode + Ollama (fully local, free)

Best for: privacy, offline use, zero API costs.

### 1. Pull a local model

```bash
ollama pull gemma4:e4b      # Gemma 4 E4B, efficient on-device default
# or
ollama pull qwen2.5:7b      # 7B, stronger reasoning
# or
ollama pull deepseek-r1:8b  # 8B, excellent for analysis
```

### 2. Configure HydraMem

`config.yml`:
```yaml
llm:
  provider: local
  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434

night_gardener:
  infer_with: local
  verify_with: local
```

### 3. Configure OpenCode

`~/.config/opencode/config.json`:

```json
{
  "provider": {
    "ollama": {
      "model": "gemma4:e4b"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

### 4. Start both services

```bash
# Terminal 1: HydraMem MCP server
uv run hydramem-server

# Terminal 2: OpenCode
opencode
```

---

## Option B — OpenCode + Anthropic Claude

Best for: highest reasoning quality, complex multi-hop queries.

### 1. Get an Anthropic API key

Sign up at [console.anthropic.com](https://console.anthropic.com/). Store the key in your environment — **never** hardcode it.

```bash
# Add to ~/.bashrc or ~/.zshrc
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or put it in the project `.env` file (automatically loaded by HydraMem):

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Configure HydraMem

`config.yml`:

```yaml
llm:
  provider: anthropic
  external:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-20250514

verification:
  vog_use_local_llm: false  # allow VoG to use Claude for higher accuracy
  vog_max_candidates: 20    # keep cost under control

night_gardener:
  infer_with: local         # bulk inference stays local
  verify_with: anthropic    # borderline cases use Claude
```

### 3. Configure OpenCode

`~/.config/opencode/config.json`:

```json
{
  "provider": {
    "anthropic": {
      "api_key_env": "ANTHROPIC_API_KEY",
      "model": "claude-sonnet-4-20250514"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

### 4. Available Claude models

| Model | Notes |
|-------|-------|
| `claude-opus-4-5` | Highest capability, highest cost |
| `claude-sonnet-4-20250514` | Best balance of capability and cost |
| `claude-haiku-20240307` | Fastest, lowest cost |

---

## Option C — OpenCode + OpenAI

```json
{
  "provider": {
    "openai": {
      "api_key_env": "HYDRAMEM_OPENAI_KEY",
      "model": "gpt-4o-mini"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

`config.yml`:

```yaml
llm:
  provider: openai
  external:
    provider: openai
    api_key_env: HYDRAMEM_OPENAI_KEY
    model: gpt-4o-mini
```

---

## Option D — Hybrid (recommended for production)

Use Ollama locally for bulk operations and Claude for interactive queries.

`config.yml`:

```yaml
llm:
  provider: auto           # tries Ollama first, falls back to Anthropic
  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434
  external:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    model: claude-haiku-20240307   # cheap external fallback

night_gardener:
  infer_with: local        # always free for bulk
  verify_with: auto        # local if Ollama is up, else Claude
```

OpenCode config:

```json
{
  "provider": {
    "anthropic": {
      "api_key_env": "ANTHROPIC_API_KEY",
      "model": "claude-sonnet-4-20250514"
    }
  },
  "mcp": {
    "hydramem": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

---

## Verifying the connection

Once HydraMem is running and OpenCode is configured, test from within OpenCode:

```
> What tools does HydraMem provide?
```

OpenCode will call `priming_context_tool` automatically if any hydramem-* skill is active, or you can invoke skills explicitly:

```
> @hydramem-query What is the Night Gardener?
```

---

## Troubleshooting

### HydraMem server not reachable

```bash
curl http://localhost:3000/health
# Should return: {"status": "ok"}
```

Check the server is running:

```bash
uv run hydramem-server
```

### Ollama not responding

```bash
ollama list          # Check pulled models
ollama serve         # Start Ollama daemon if not running
```

### API key not found

```bash
echo $ANTHROPIC_API_KEY   # Should print your key
# If empty, source your shell config:
source ~/.bashrc
```

Or add it to `.env` in the project root (loaded automatically).

---

## Other supported clients

| Client | Config location | Notes |
|--------|----------------|-------|
| Claude Desktop | `claude_desktop_config.json` | MCP type: `http` |
| Cursor | `.cursor/mcp.json` | Same URL |
| VS Code Copilot | `.vscode/mcp.json` | Same URL |
| Any MCP client | varies | HTTP endpoint: `http://localhost:3000/mcp` |
