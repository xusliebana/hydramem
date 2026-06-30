# Public API Contract

`hydramem` is published on **PyPI**. Everything listed here is a **stable
surface**: it may not change in a backward-incompatible way without a
deprecation cycle and a [CHANGELOG.md](../../../CHANGELOG.md) entry. Anything not
listed here is **internal** and may change at any time.

> **Versioning:** [Semantic Versioning](https://semver.org/). HydraMem is pre-1.0
> (`0.x`), so per [CONTRIBUTING.md](../../../CONTRIBUTING.md) **minor** bumps may break
> APIs — but every break is announced in `CHANGELOG.md`. After `1.0.0`, breaking
> changes require a **major** bump and a one-minor deprecation window.

## 1. Console entry points (the primary contract)

Declared in [pyproject.toml](../../../pyproject.toml) `[project.scripts]`:

| Command | Target | Guarantee |
|---|---|---|
| `hydramem` | `hydramem.cli:main` | CLI subcommands and their documented flags |
| `hydramem-server` | `hydramem.server:main` | MCP server bootstrap |
| `hydramem-dashboard` | `hydramem.dashboard:main` | Telemetry dashboard |

Documented CLI subcommands: `hydramem init`, `hydramem stats`,
`hydramem telemetry`, `hydramem garden-status`. Flags may be **added**; existing
flags and their semantics may not be removed or repurposed without deprecation.

> Additive in 0.2.0: `hydramem review` and `hydramem train-pruner` (the
> human-in-the-loop pruner-training loop).

## 2. MCP tool signatures

The 18 tools exposed by [hydramem/server.py](../../../hydramem/server.py) are a
public contract: **tool names, parameters, and return-shape keys** are stable.
The authoritative list is [docs/mcp-tools-reference.md](../../mcp-tools-reference.md).
Adding a tool or an optional parameter is backward-compatible; renaming a tool,
removing a parameter, or changing a return key is a breaking change.

> Recent additive changes (backward-compatible): `hydra_search_tool` gained an
> optional `strategy_override` argument, and the `hydra_search` return dict
> gained `entities` and `planner` keys.

## 3. Documented Python surface

These classes/methods are intended for direct import and are covered by the
contract (see [docs/architecture.md](../../architecture.md) and
[agents/IMPLEMENTATION.md](../../../agents/IMPLEMENTATION.md)):

- `hydramem.search` — search service: `priming_context`, `hydra_search`,
  `expand_context`, `trace_path` (all return JSON-serializable `dict`s).
- `hydramem.ingest` — `IngestionService`: `ingest_markdown`, `ingest_directory`.
- Storage / LLM / embedder **abstract base classes** in `hydramem.storage` and
  `hydramem.llm` (the dependency-injection seams). Concrete backends are internal.

> The top-level `hydramem/__init__.py` is intentionally minimal: HydraMem is
> consumed mainly through its **CLI + MCP server**, not as an `import hydramem`
> SDK. New top-level re-exports are additive and must be reflected in
> [tests/test_public_api.py](../../../tests/test_public_api.py).

## 4. Configuration schema

The keys in [config.yml.example](../../../config.yml.example) and the documented
`HYDRAMEM_*` environment variables are stable. See
[docs/configuration.md](../../configuration.md). Adding keys with safe defaults is
backward-compatible; removing or renaming keys is breaking.

> Additive in 0.2.0: `extraction.*` (GLiNER backend), `night_gardener.consolidation.*`
> (retrieval-success consolidation), and `search.planner.*` (typed retrieval
> planner). **Deprecated:** the `[kuzu]` extra and `HYDRAMEM_GRAPH_BACKEND=kuzu`
> (unmaintained upstream) — prefer Grafeo / NetworkX.

## 5. Typing

The package ships a `py.typed` marker (PEP 561) — downstream users get the
public type hints. Public signatures use `from __future__ import annotations`
and explicit type hints.

## Explicitly NOT public

- Any `_`-prefixed module, class, function, or attribute.
- On-disk formats of the graph store, LanceDB tables, the telemetry SQLite
  schema, and `sessions.json` (may change between minor versions).
- Internal backend classes (Grafeo/LadybugDB/Kuzu/NetworkX adapters, concrete
  embedders and LLM clients) — depend on the abstract base classes instead.
- Benchmark scripts and their output format under `scripts/`.

## Changing the public API — checklist

1. Is there a backward-compatible path (new optional arg, new tool)? Prefer it.
2. If breaking: add a `DeprecationWarning`, keep the old behavior for one minor
   cycle (post-1.0), and document the migration in `CHANGELOG.md`.
3. Update this file, [docs/mcp-tools-reference.md](../../mcp-tools-reference.md) (if
   tools changed), and [tests/test_public_api.py](../../../tests/test_public_api.py).
4. Run `nox -s api` and `nox -s verify`.
