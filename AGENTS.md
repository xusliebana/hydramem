# Agent Guide — HydraMem

> **HydraMem** is a 100% local, privacy-first knowledge-management library and
> MCP server for AI agents (hybrid graph + vector search, two-stage verification,
> and an autonomous "Night Gardener"). It ships to **PyPI** as the `hydramem`
> package with three console entry points and an 18-tool MCP server.

This file is a **map, not a manual**. Read the linked docs on demand and keep
this file short — public docs live in `docs/` (the GitHub Pages site) and
internal/harness knowledge lives in `docs/internal/`.

## Always read first

- [docs/internal/CODEMAP.md](docs/internal/CODEMAP.md) — where everything lives and where to look before changing code.
- `.agent/current.md` — the active task's state, **if it exists** (see [.agent/README.md](.agent/README.md)).

## First run (Environment subsystem)

```bash
bash scripts/init.sh          # uv sync (dev), pre-commit install, baseline verify, prints next steps
```

- **Package manager:** [uv](https://github.com/astral-sh/uv). Prefix ad-hoc commands with `uv run`.
- **Supported Python:** 3.11, 3.12, 3.13. The dev pin in [.python-version](.python-version) is **3.12**
  (matches the Docker image and enables the native Grafeo graph backend; on 3.11 the graph falls back to NetworkX).
- **Task runner:** [nox](https://nox.thea.codes/) — see [noxfile.py](noxfile.py).

## Verify your work (Feedback subsystem — highest ROI)

```bash
nox -s verify                 # full gate: lint + format-check + typecheck + tests + build + public-API
# Granular sessions:
nox -s tests                  # pytest across the supported Python matrix
nox -s lint                   # ruff check + ruff format --check
nox -s typecheck              # mypy hydramem/ (advisory — baseline is not yet clean)
nox -s api                    # public-API surface test (the import/entry-point contract)
nox -s build                  # uv build + twine check (sdist + wheel, incl. py.typed)
```

Never mark work "done" until the relevant `nox` session passes. Use evidence,
not vibes — see [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md).

## Non-negotiable constraints (Instructions subsystem)

1. **The public API is a contract.** `hydramem` is published on PyPI. Do not break the
   console entry points (`hydramem`, `hydramem-server`, `hydramem-dashboard`), the documented
   Python surface, or MCP tool signatures without a deprecation cycle and a `CHANGELOG.md`
   entry. SemVer applies — see [docs/internal/CONTRACTS/PUBLIC_API.md](docs/internal/CONTRACTS/PUBLIC_API.md).
2. **Honesty contract.** Never describe a feature, metric, or component as working if it does
   not measurably work. The dashboard and docs must reflect reality.
3. **Local-first, zero exfiltration by default.** No network calls to cloud services unless the
   user explicitly configured an external LLM. Telemetry is opt-in and stored locally.
4. **No client chain-of-thought capture.** HydraMem persists only observable snapshots.
5. **Security boundaries.** See [SECURITY.md](SECURITY.md). Secrets come from environment variables only.

Full list: [docs/internal/CONSTRAINTS.md](docs/internal/CONSTRAINTS.md).

## Load only when relevant (progressive disclosure)

| Before you change… | Read |
|---|---|
| Public API / entry points / MCP tool signatures | [docs/internal/CONTRACTS/PUBLIC_API.md](docs/internal/CONTRACTS/PUBLIC_API.md), [docs/mcp-tools-reference.md](docs/mcp-tools-reference.md), [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md) |
| Architecture / module boundaries | [docs/architecture.md](docs/architecture.md), [docs/internal/DECISIONS/](docs/internal/DECISIONS/), [docs/internal/CONSTRAINTS.md](docs/internal/CONSTRAINTS.md) |
| Retrieval / search / verification | [docs/architecture-ir-km.md](docs/architecture-ir-km.md), [docs/verification.md](docs/verification.md) |
| A retrieval / ranking / pruning / verification **algorithm** | [docs/internal/PLAYBOOKS/benchmark-regression.md](docs/internal/PLAYBOOKS/benchmark-regression.md), [docs/benchmarks.md](docs/benchmarks.md) |
| Ingestion pipeline | [docs/mcp-tools-reference.md](docs/mcp-tools-reference.md), [agents/IMPLEMENTATION.md](agents/IMPLEMENTATION.md) |
| Night Gardener / offline learning | [docs/night-gardener.md](docs/night-gardener.md) |
| Config / storage backends | [docs/configuration.md](docs/configuration.md), [config.yml.example](config.yml.example) |
| Telemetry / metrics | [docs/telemetry.md](docs/telemetry.md) |
| Dependencies / packaging / release | [pyproject.toml](pyproject.toml), [docs/internal/PLAYBOOKS/release.md](docs/internal/PLAYBOOKS/release.md) |
| Finishing any non-trivial task | [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md), [docs/internal/REVIEW.md](docs/internal/REVIEW.md) |

## Repository map

- `hydramem/` — library source (`core`, `storage`, `llm`, `ingest`, `search.py`, `verification`, `garden`, `telemetry`, `server.py`, `cli.py`, `dashboard.py`). Full tree: [docs/internal/CODEMAP.md](docs/internal/CODEMAP.md).
- `tests/` — pytest suite (`asyncio_mode=auto`, coverage ≥ 60%).
- `docs/` — **public documentation site** (GitHub Pages via MkDocs Material): architecture, guides, reference, glossary. Animated landing in [docs/index.md](docs/index.md); site config in [mkdocs.yml](mkdocs.yml).
- `docs/internal/` — **harness & internal knowledge** (excluded from the public site): [CODEMAP.md](docs/internal/CODEMAP.md), [CONSTRAINTS.md](docs/internal/CONSTRAINTS.md), [DECISIONS/](docs/internal/DECISIONS/) (ADRs), [CONTRACTS/](docs/internal/CONTRACTS/), [PLAYBOOKS/](docs/internal/PLAYBOOKS/), [DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md), [REVIEW.md](docs/internal/REVIEW.md), [contributing.md](docs/internal/contributing.md), and `future_work/` research notes.
- `scripts/` — `init.sh`, plus `benchmark.py` / `dogfood.py`.
- `agents/` — persistent agent-facing notes ([IMPLEMENTATION.md](agents/IMPLEMENTATION.md), [MEMORY.md](agents/MEMORY.md)).
- `.agent/` — **local, gitignored** runtime state (current task, tasks, handoff, logs).
- `.github/skills/` — 6 bundled MCP Agent Skills. Adapters: [CLAUDE.md](CLAUDE.md), [.github/copilot-instructions.md](.github/copilot-instructions.md), `.opencode/commands/`.

## Working rules (State subsystem)

- **All agentic work must follow this harness.** If an AI agent is used, it must
  follow `AGENTS.md` + the linked constraints, contracts, and verification gates.
- **Trivial change:** no persistent plan needed, but still run the relevant `nox` session.
- **Non-trivial change:** create/update `.agent/current.md` (goal, plan, files touched, commands run, next steps) and work **one task at a time**.
- **User-visible change:** update [CHANGELOG.md](CHANGELOG.md) and, if the public surface changes, [docs/internal/CONTRACTS/PUBLIC_API.md](docs/internal/CONTRACTS/PUBLIC_API.md).
- **Permanent decision:** add an ADR in [docs/internal/DECISIONS/](docs/internal/DECISIONS/). Do not use task logs as ADRs.
- **Done = verified:** finish a non-trivial task by writing a summary log to `.agent/logs/` and leaving a clean tree (see [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md)).
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/); allowed scopes in [CONTRIBUTING.md](CONTRIBUTING.md).

## Harness map (audit this like code)

| Subsystem | Where it lives |
|---|---|
| Instructions | `AGENTS.md` (this file) + adapters + [docs/internal/CONSTRAINTS.md](docs/internal/CONSTRAINTS.md) |
| Tools | 18 MCP tools ([docs/mcp-tools-reference.md](docs/mcp-tools-reference.md)) + 6 skills (`.github/skills/`) |
| Environment | [pyproject.toml](pyproject.toml), [.python-version](.python-version), [Dockerfile](Dockerfile), [noxfile.py](noxfile.py) |
| State | `.agent/` runtime + [agents/MEMORY.md](agents/MEMORY.md) + [docs/internal/next-session.md](docs/internal/next-session.md) |
| Feedback | `nox -s verify`, CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)), [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md) |

## Further reading (harness engineering)

- OpenAI — *Harness engineering: leveraging Codex in an agent-first world*
- Anthropic — *Effective harnesses for long-running agents* / *Harness design for long-running apps*
- PyPA Packaging Guide; Scientific-Python **SPEC 0** (supported versions) & **SPEC 8** (secure releases)
