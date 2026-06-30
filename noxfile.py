"""Nox task runner for HydraMem — a cross-platform mirror of CI.

Common entry points:
    nox -s verify     # full local gate (lint + typecheck + tests + api + build)
    nox -s tests      # pytest across the supported Python matrix (3.11/3.12/3.13)
    nox -s lint       # ruff check + ruff format --check
    nox -s typecheck  # mypy (advisory)
    nox -s api        # public-API surface contract test
    nox -s build      # uv build + twine check
    nox -s bench      # offline retrieval benchmark (Recall@k + MRR)
"""

from __future__ import annotations

import glob
import os

import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["lint", "typecheck", "tests", "api"]

PYTHON_VERSIONS = ["3.11", "3.12", "3.13"]
DEFAULT_PYTHON = "3.12"


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the test suite across the supported Python matrix."""
    session.install("-e", ".[dev]")
    session.run("pytest", *session.posargs)


@nox.session(python=DEFAULT_PYTHON)
def lint(session: nox.Session) -> None:
    """Ruff lint + format check (no changes are applied)."""
    session.install("ruff>=0.4.0")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python=DEFAULT_PYTHON)
def typecheck(session: nox.Session) -> None:
    """mypy — advisory: the baseline is not yet clean, so this never fails the gate."""
    session.install("-e", ".[dev]")
    session.run("mypy", "hydramem", success_codes=[0, 1])


@nox.session(python=DEFAULT_PYTHON)
def api(session: nox.Session) -> None:
    """Public-API surface contract test (the import / entry-point contract)."""
    session.install("-e", ".[dev]")
    session.run("pytest", "tests/test_public_api.py", *session.posargs)


@nox.session(python=DEFAULT_PYTHON)
def build(session: nox.Session) -> None:
    """Build sdist + wheel and validate distribution metadata."""
    session.install("uv", "twine")
    session.run("uv", "build")
    dists = glob.glob("dist/*")
    if not dists:
        session.error("uv build produced no artifacts in dist/")
    session.run("twine", "check", *dists)


@nox.session(python=DEFAULT_PYTHON)
def bench(session: nox.Session) -> None:
    """Offline retrieval benchmark (Recall@{1,3,5} + MRR) for algorithm changes.

    Deterministic by default (stub embedder) so before/after runs compare
    cleanly. Pass extra args through, e.g. a quality run with the LLM judge:
        nox -s bench -- --judge
    See docs/internal/PLAYBOOKS/benchmark-regression.md.
    """
    session.install("-e", ".[dev]")
    os.makedirs("reports", exist_ok=True)
    env = {"HYDRAMEM_EMBEDDER": os.environ.get("HYDRAMEM_EMBEDDER", "stub")}
    args = session.posargs or ["--json", "reports/bench.json"]
    session.run("python", "scripts/benchmark.py", "local", *args, env=env)


@nox.session(python=DEFAULT_PYTHON)
def verify(session: nox.Session) -> None:
    """Full local gate in a single venv: lint + typecheck + tests + api + build."""
    session.install("-e", ".[dev]", "uv", "twine")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")
    session.run("mypy", "hydramem", success_codes=[0, 1])
    session.run("pytest")
    session.run("python", "-c", "import hydramem")
    session.run("uv", "build")
    session.run("twine", "check", *glob.glob("dist/*"))
