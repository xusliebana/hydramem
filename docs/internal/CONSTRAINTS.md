# Constraints

Hard limits, non-goals, and risky areas. Treat these as invariants unless an ADR
in [DECISIONS/](DECISIONS/) supersedes them. Exact tunable values live in
[config.yml.example](../../config.yml.example) and [configuration.md](../configuration.md);
this file states the *rules*, not every number.

## Compatibility & API

- **Public API is a contract.** See [CONTRACTS/PUBLIC_API.md](CONTRACTS/PUBLIC_API.md).
  No breaking change to entry points, MCP tool signatures, or the documented
  Python surface without a deprecation cycle + `CHANGELOG.md` entry.
- **SemVer, pre-1.0.** Minor (`0.x`) bumps may break APIs but must be announced.
- **Supported Python: 3.11, 3.12, 3.13.** Match the CI matrix. On **3.11** the
  native Grafeo graph backend is unavailable and the code falls back to NetworkX —
  changes must keep that fallback working.

## Privacy & security (non-negotiable)

- **Local-first.** No cloud network calls by default. External LLM providers are
  used **only** when the user explicitly configures them.
- **Telemetry is opt-in** and stored locally (SQLite). No content, queries, or
  chain-of-thought ever leave the machine.
- **No client chain-of-thought capture.** Only observable snapshots are persisted.
- **Secrets via environment variables only** — never hardcoded, never logged.
  See [SECURITY.md](../../SECURITY.md).

## Architecture & resource limits

- **Single-tenant MCP server by design.** Run one process per tenant; see
  [multi-tenant.md](../multi-tenant.md).
- **GNN pruning auto-skips** on graphs larger than `HYDRAMEM_GNN_MAX_NODES`
  (default `5000`) and falls back to a heuristic.
- **VoG / LLM calls are bounded** (candidate caps + optional judge) — see
  [verification.md](../verification.md) and `config.yml`. Do not issue unbounded LLM calls.
- **Dependency injection (DIP).** Storage, LLM, and embedder are constructor-injected
  so components are unit-testable without monk-patching. Do not reach for globals.

## Dependencies

- **Minimal runtime footprint.** The default install avoids torch. Heavy backends
  live behind extras: `gnn` (torch + torch-geometric), `sentence-transformers`,
  `kuzu`. New heavy dependencies belong in an extra, justified in an ADR.
- **Lower bounds are intentional.** Keep version pins consistent with
  [pyproject.toml](../../pyproject.toml); the graph backend is gated by
  `python_version >= '3.12'`.

## Non-goals

- Not a cloud service, not a hosted multi-tenant SaaS.
- Not a general-purpose vector database or graph database — it *orchestrates* them.
- Not claiming to be the first memory system, graph-RAG, or hallucination filter.
  HydraMem is an **opinionated local-first integration** with auditable metrics.

## Risky areas (change with extra care + tests)

- `hydramem/verification/` and SR-MKG weights — silent quality regressions are easy.
- `hydramem/server.py` tool signatures — public contract.
- `hydramem/storage/` backend swaps and on-disk formats — data migration risk.
- The naive-RAG **shadow estimator** — drives the headline "tokens saved" metric;
  changes here change a user-facing number and must stay honest.
