# Contributing to HydraMem

Thank you for considering contributing to HydraMem! This document explains how to get started, our code conventions, and the contribution process.

---

## Table of contents

- [Code of Conduct](#code-of-conduct)
- [How to contribute](#how-to-contribute)
- [Development setup](#development-setup)
- [Project structure](#project-structure)
- [Writing tests](#writing-tests)
- [Code style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting bugs](#reporting-bugs)
- [Feature requests](#feature-requests)

---

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be respectful, inclusive, and constructive.

---

## How to contribute

- **Bug fixes** — open an issue first if the bug is non-trivial; small fixes can go straight to a PR.
- **Features** — open an issue or discussion to align on design before writing code.
- **Documentation** — always welcome; no issue required.
- **Tests** — improving coverage is always appreciated.

---

## Development setup

### Requirements

- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv) package manager

### Install with dev dependencies

```bash
git clone https://github.com/hydramem/hydramem
cd hydramem
uv sync --extra dev
```

### Run tests

```bash
uv run pytest -v
```

Tests use mocked databases and embeddings — **no Ollama or GPU required**.

### Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

### Format

```bash
uv run ruff format .
```

---

## Project structure

```
hydramem/
├── tools/
│   ├── server.py          # MCP server (the main integration point)
│   ├── db.py              # Storage layer (LadybugDB + LanceDB)
│   ├── ingest.py          # Document ingestion pipeline
│   ├── search.py          # Hybrid retrieval
│   ├── verify.py          # SR-MKG + VoG verification
│   ├── night_gardener.py  # Autonomous learning
│   ├── gnn_prune.py       # LightGNN pruning
│   ├── utils.py           # Config, LLM client, shared types
│   ├── cli.py             # CLI commands
│   └── telemetry/         # Metrics storage
├── tests/                 # pytest test suite
├── docs/                  # Documentation (you are here)
├── scripts/               # Utility scripts
│   └── dogfood.py         # Self-ingest pipeline
├── kms/                   # Knowledge base (Markdown files)
├── .github/skills/        # Agent Skills for OpenCode / Cursor
├── config.yml.example     # Full configuration template
└── pyproject.toml
```

---

## Writing tests

All tests live in `tests/`. We use `pytest` with `asyncio_mode = "auto"`.

### Conventions

- Test files are named `test_<module>.py`.
- Tests that call LLMs must mock `hydramem.llm.factory.call_llm`.
- Tests that use storage must use the `tmp_path` fixture or an in-memory database.
- Never make real network calls in tests.

### Example test

```python
# tests/test_verify.py
from hydramem.core.types import Relation
from hydramem.verification.srmkg import SRMKGScorer


def test_srmkg_high_common_neighbours():
    rel = Relation(from_entity="a", to_entity="b", relation_type="uses", confidence=0.6)
    score = SRMKGScorer().score(rel, common_neighbors=5, degree_from=8, degree_to=8)
    assert 0.0 <= score <= 1.0


def test_vog_skips_llm_when_disabled():
    rel = Relation(from_id="a", to_id="b", relation_type="uses", confidence=0.5)
    accepted, confidence = vog_verify(rel, use_llm=False)
    # Heuristic fallback: confidence 0.5 → partial accept
    assert isinstance(accepted, bool)
    assert 0.0 <= confidence <= 1.0
```

### Running a single test

```bash
uv run pytest tests/test_verify.py -v
```

---

## Code style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting.

**Key conventions:**

- Line length: 100 characters
- Python target: 3.11+
- Imports: `isort` order (I rule in Ruff)
- No `from __future__ import annotations` — already in `pyproject.toml` defaults
- Docstrings: short one-liner for public functions, full description for complex ones
- Type hints: use them for all public function signatures
- No bare `except:` — use `except Exception:` with a comment at minimum

---

## Submitting a Pull Request

1. **Fork** the repository.
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. **Write tests** for any new behaviour.
4. **Run the full test suite** and linter:
   ```bash
   uv run pytest -v
   uv run ruff check .
   ```
5. **Commit** using conventional commit messages:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `test:` tests only
   - `refactor:` no behaviour change
   - `chore:` tooling, CI, dependencies
6. **Open a Pull Request** with a clear description of what changed and why.

### PR checklist

- [ ] Tests pass locally
- [ ] Ruff reports no errors
- [ ] New behaviour is documented (docstring + docs/ if public-facing)
- [ ] No secrets or personal data committed
- [ ] `config.yml.example` updated if new configuration keys were added

---

## Reporting bugs

Open a GitHub Issue with:
- HydraMem version (`uv run hydramem --version`)
- Python version (`python --version`)
- OS and architecture
- Steps to reproduce
- Expected vs actual behaviour
- Relevant log output (set `HYDRAMEM_LOG_LEVEL=DEBUG`)

---

## Feature requests

Open a GitHub Discussion (category: Ideas) with:
- The use case you are trying to solve
- How you envision it working
- Any alternatives you have considered

Features that align with the project goals (local-first, privacy, verified knowledge) are most likely to be accepted.

---

## Roadmap

See [README.md § Roadmap](../../README.md#roadmap) for the planned feature list.

If you want to work on a roadmap item, open an issue to coordinate with the maintainers before starting.
