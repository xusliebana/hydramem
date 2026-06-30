# Contributing to HydraMem

Thanks for considering a contribution! HydraMem aims to be a **honest,
local-first** memory layer for AI agents. We value working code, reproducible
benchmarks, and clear documentation over hype.

> **Working with an AI agent (or as one)?** Read [AGENTS.md](AGENTS.md) first — it
> is the harness entry point: project map, non-negotiable rules, and the
> verification commands every change must pass.

## Ground rules

1. **No marketing in code or metrics.** If a feature does not measurably work,
   it does not get described as if it does. The dashboard must reflect reality.
2. **One concern per PR.** Easier to review, easier to revert.
3. **Tests are not optional.** Every behaviour change ships with a test.
4. **Be kind.** See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/xusliebana/hydramem
cd hydramem
uv sync --extra dev --extra fastembed
uv run pre-commit install
```

Run the test suite:

```bash
uv run pytest                       # all tests
uv run pytest tests/integration     # end-to-end only
uv run pytest --cov=hydramem           # with coverage
```

Lint and format:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy hydramem/
```

Or run the full gate the way CI does — across the supported Python matrix — with
[nox](https://nox.thea.codes/):

```bash
uv run nox -s verify        # lint + typecheck + tests + public-API + build
uv run nox -s tests         # pytest on 3.11 / 3.12 / 3.13
```

## Project layout

| Path | Responsibility |
|------|----------------|
| `hydramem/core/` | Config, types, logging, token counting |
| `hydramem/storage/` | Graph + vector repository abstractions and backends |
| `hydramem/llm/` | LLM provider implementations (Ollama / OpenAI / Anthropic) |
| `hydramem/ingest/` | Markdown chunking, entity extraction, embedding |
| `hydramem/search/` | Hybrid retrieval (vector + graph + cached entity index) |
| `hydramem/verification/` | SR-MKG topological scorer + VoG groundedness checker |
| `hydramem/garden/` | Night Gardener phases (infer / verify / prune) |
| `hydramem/telemetry/` | Local SQLite metrics + naive-RAG shadow estimator |
| `hydramem/server.py` | FastMCP server with 18 tools |

The technical architecture is described in [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md).

## Coding standards

- **Python 3.11+**, `from __future__ import annotations` everywhere.
- Type hints on every public signature.
- No `except Exception: pass`. Log at `debug` minimum.
- Storage / LLM / embedder are injected through the constructor (DIP) so
  every component is unit-testable without monkey-patching.
- Public APIs return `dict`s or dataclasses, not raw tuples.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(garden): infer relations from cross-project sessions
fix(verify): drop random fallback in VoGVerifier
docs(readme): clarify naive-RAG baseline
```

Allowed scopes: `core`, `storage`, `search`, `verify`, `garden`, `ingest`,
`telemetry`, `cli`, `server`, `docs`, `ci`.

## Pull requests

HydraMem follows **GitHub Flow**:

- Create a short-lived feature branch from `main`.
- Open a PR back to `main`.
- Keep the branch focused on a single concern.
- Squash-merge after CI + review are green.

If you are using an AI agent, the work must follow the project harness in
[AGENTS.md](AGENTS.md) (constraints, verification, and state rules).

1. Fork → feature branch (`feat/short-name` or `fix/short-name`).
2. Before opening, work through [docs/internal/DEFINITION_OF_DONE.md](docs/internal/DEFINITION_OF_DONE.md).
   If you touched the public surface (entry points, MCP tools, documented API,
   config keys), update [docs/internal/CONTRACTS/PUBLIC_API.md](docs/internal/CONTRACTS/PUBLIC_API.md)
   and `CHANGELOG.md`.
3. Push and open a PR against `main`. Fill the PR template. Reviewers follow
   [docs/internal/REVIEW.md](docs/internal/REVIEW.md).
4. CI must be green. A maintainer will review within a few days.
5. Squash-merge is the default; release notes are generated from PR titles.

## Reporting bugs and security issues

- Functional bugs → [issue tracker](https://github.com/xusliebana/hydramem/issues).
- Security vulnerabilities → see [SECURITY.md](SECURITY.md). **Do not** open a
  public issue.

## Releases

Maintainers tag `vX.Y.Z`; CI publishes to PyPI through trusted publishing.
Pre-1.0: minor bumps may break APIs; we will note breakages in `CHANGELOG.md`.

## Code of Conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md).
