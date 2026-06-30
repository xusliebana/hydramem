# Multi-tenant deployment

> Status: **supported pattern**, not a managed product. HydraMem is local-first
> and single-tenant *per process*. This guide explains how to run several
> processes safely on the same host.

## Why one process per tenant

- All service singletons in [hydramem/server.py](../hydramem/server.py) — `SearchService`,
  `IngestionPipeline`, `NightGardener` — assume exclusive access to one
  knowledge graph.
- LadybugDB / LanceDB on-disk handles are not safe to share across writers.
- Telemetry events are tagged by `project`, which is convenient for
  per-tenant filtering inside a single process — but writes still go through
  the same SQLite file.

## Recommended layout

```
/srv/hydramem/
├── tenants/
│   ├── alice/
│   │   ├── kms/          # ingest source for Alice
│   │   └── data/         # LadybugDB + LanceDB live here
│   └── bob/
│       ├── kms/
│       └── data/
└── shared/
    └── secrets.env       # federation HMAC keys (chmod 600)
```

Each tenant gets:

- `HYDRAMEM_PROJECT=<tenant>`
- `LADYBUG_DB_PATH=/srv/hydramem/tenants/<tenant>/data/hydramem.ladybug`
- `LANCEDB_PATH=/srv/hydramem/tenants/<tenant>/data/lancedb`
- `KNOWLEDGE_DIR=/srv/hydramem/tenants/<tenant>/kms`
- `MCP_PORT=<unique port>` (or stdio when launched per-client)

## systemd template

Save as `/etc/systemd/system/hydramem@.service`:

```ini
[Unit]
Description=HydraMem MCP server (tenant %i)
After=network-online.target

[Service]
Type=simple
User=hydramem
EnvironmentFile=/srv/hydramem/shared/secrets.env
Environment=HYDRAMEM_PROJECT=%i
Environment=LADYBUG_DB_PATH=/srv/hydramem/tenants/%i/data/hydramem.ladybug
Environment=LANCEDB_PATH=/srv/hydramem/tenants/%i/data/lancedb
Environment=KNOWLEDGE_DIR=/srv/hydramem/tenants/%i/kms
Environment=MCP_PORT=3${RANDOM:0:3}
ExecStart=/usr/local/bin/uv run hydramem-server
Restart=on-failure
RestartSec=5
ProtectSystem=strict
ReadWritePaths=/srv/hydramem/tenants/%i

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable --now hydramem@alice hydramem@bob
```

## stdio transport for editor-attached clients

If a tenant only needs HydraMem when their editor (Claude Desktop, Cursor,
etc.) is open, run the server in stdio mode instead of as a long-lived
service. The launcher process is fully isolated per tenant:

```bash
HYDRAMEM_PROJECT=alice \
  HYDRAMEM_TRANSPORT=stdio \
  uv run hydramem-server
```

## Read-only dashboard per tenant

The dashboard ([hydramem/dashboard.py](../hydramem/dashboard.py)) reads the same
local telemetry DB the tenant's server writes to. Bind it to a different
port per tenant:

```bash
HYDRAMEM_PROJECT=alice uv run hydramem dashboard --port 8801
HYDRAMEM_PROJECT=bob   uv run hydramem dashboard --port 8802
```

The dashboard is read-only; you can safely expose it behind an authenticated
reverse proxy such as Caddy or Authelia.

## Federated knowledge between tenants

Use the `hydramem export` / `hydramem import` commands and a shared HMAC
secret stored in the systemd `EnvironmentFile`. Imports are rejected if the
issuer is not whitelisted via `--accept-issuer`.

## What is intentionally not supported

- A single HydraMem process serving multiple tenants concurrently. The graph
  cache, NetworkX projection, and Night Gardener locks all assume one tenant.
- Sharing a LanceDB / LadybugDB directory between processes. Use replication
  (rsync the closed directory) instead.
- Cross-tenant queries inside one process. Run two clients and combine the
  results in the calling agent.
