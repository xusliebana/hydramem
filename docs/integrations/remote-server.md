# Remote / Team server

Run **one** HydraMem instance over HTTP that several clients (or teammates)
connect to, instead of a palace on each laptop.

!!! warning "This is a deliberate step away from single-machine local-first"
    HydraMem is **single-tenant by design** and has **no built-in authentication
    or TLS**. A networked deployment is still *your* infrastructure (no
    third-party API, nothing phones home) — but you are responsible for putting
    it behind a private network/VPN, a TLS-terminating reverse proxy, and an auth
    layer. Treat the security notes below as mandatory, not optional.

## Architecture

```text
  Teammate A ─┐
  Teammate B ─┤  MCP over HTTP        ┌─ reverse proxy (TLS + auth)
  Teammate C ─┴──(behind your proxy)─▶│        │
                                      └────────▼─────────────
                                        hydramem serve --transport http
                                        (one host: embedder + store)
                                               │
                                               ▼
                                        LanceDB / Grafeo (local to the host)
```

## 1. Serve over HTTP

```bash
hydramem serve --transport http --host 0.0.0.0 --port 3000
# MCP endpoint: http://<host>:3000/mcp
```

Equivalent env vars: `HYDRAMEM_TRANSPORT=http`, `MCP_HOST=0.0.0.0`, `MCP_PORT=3000`.

## 2. Put it behind a reverse proxy (required for remote access)

HydraMem speaks **plaintext HTTP** with **no auth**. Never expose `/mcp` directly
beyond a trusted private network. Front it with nginx / Caddy / Traefik to add
TLS and authentication. Minimal Caddy example:

```caddyfile
memory.example.com {
    @mcp path /mcp*
    basic_auth @mcp {
        teammate $2a$14$...bcrypt-hash...
    }
    reverse_proxy @mcp 127.0.0.1:3000
}
```

(Use bearer-token auth at the proxy if your clients support an `Authorization`
header; otherwise basic auth + TLS + IP allow-listing.)

## 3. Connect a client

Point each client's MCP config at the proxied URL. For example, OpenCode / VS Code:

```json
{ "servers": { "hydramem": { "type": "http", "url": "https://memory.example.com/mcp" } } }
```

For tools that support custom headers, add your proxy's auth header there.

## Teams: one tenant per process

HydraMem is single-tenant; do **not** point two server processes at the same
store directory. For multi-project / multi-user setups, run **one process per
tenant** (each with its own `HYDRAMEM_DATA_DIR` / `HYDRAMEM_PROJECT`) behind the
proxy. See the [multi-tenant guide](../multi-tenant.md) for the shared-store
layout and isolation rules.

## Docker

A slim stdio/HTTP image ships with the repo; a single mounted `/data` volume
captures the graph, vectors, metrics and session log:

```bash
docker run -d --name hydramem -p 3000:3000 \
  -e HYDRAMEM_TRANSPORT=http -e MCP_HOST=0.0.0.0 \
  -v "$HOME/hydramem-data:/data" -e HYDRAMEM_DATA_DIR=/data \
  hydramem:latest
```

Then front the container with your TLS/auth proxy as above.

## Operating notes

- **Ingestion** runs via the CLI on the host (`hydramem ingest …`) against the
  same store, so the shared palace stays populated.
- **Backups** become your store directory's responsibility (snapshot the mounted
  volume / `HYDRAMEM_DATA_DIR`).
- **Embeddings stay local** to the host — only your own store ever receives the
  vectors and text.

## See also

- [Multi-tenant](../multi-tenant.md) · [Configuration](../configuration.md) · [MCP tools reference](../mcp-tools-reference.md)
