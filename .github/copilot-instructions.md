# GitHub Copilot Instructions — HydraMem

This repository uses a **portable agent harness**. **[AGENTS.md](../AGENTS.md) is
the single source of truth** for project rules, the documentation map, and
verification commands. The notes below are Copilot-specific reminders.

## Hard rules (summary — full list in AGENTS.md)

- **The public API is a contract.** `hydramem` is published on PyPI. Do not break the
  console entry points (`hydramem`, `hydramem-server`, `hydramem-dashboard`), the documented
  Python surface, or MCP tool signatures without a deprecation cycle + a `CHANGELOG.md`
  entry. See [docs/internal/CONTRACTS/PUBLIC_API.md](../docs/internal/CONTRACTS/PUBLIC_API.md).
- **Honesty contract.** Never present a feature or metric as working unless it measurably works.
- **Local-first.** No cloud calls by default; secrets come from environment variables only.
- **Python 3.11–3.13.** Use `from __future__ import annotations`, type hints on public
  signatures, dependency injection (DIP), and no `except Exception: pass`.

## Before you finish

Run `nox -s verify` (or at minimum `uv run pytest` + `uv run ruff check .`).
Update `.agent/current.md` for non-trivial work. Use Conventional Commits.

Details and the full doc map: [AGENTS.md](../AGENTS.md),
[CONTRIBUTING.md](../CONTRIBUTING.md), [docs/internal/DEFINITION_OF_DONE.md](../docs/internal/DEFINITION_OF_DONE.md).
