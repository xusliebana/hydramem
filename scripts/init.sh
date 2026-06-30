#!/usr/bin/env bash
# HydraMem first-run bootstrap (Environment subsystem of the agent harness).
# Installs dev dependencies, sets up pre-commit, runs a baseline verification,
# and prints next steps. Safe to re-run.
set -euo pipefail

echo "==> HydraMem init — $(pwd)"

# 1. Dependencies (uv) -------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not installed. Install it with:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

echo "==> Installing dev dependencies (uv sync --extra dev)"
uv sync --extra dev

echo "==> Installing pre-commit hooks"
uv run pre-commit install || echo "WARN: pre-commit not available; skipping"

# 2. Baseline verification ---------------------------------------------------
# Fast gate so a fresh checkout is known-good before any feature work.
# (Full matrix + build live in: uv run nox -s verify)
echo "==> Baseline verification (lint + public-API contract)"
uv run ruff check .
uv run ruff format --check .
uv run pytest -q tests/test_public_api.py

# 3. Next steps --------------------------------------------------------------
cat <<'EOF'

==> Ready.
Next steps:
  uv run nox -s verify        # full local gate (lint + typecheck + tests + api + build)
  uv run nox -s tests         # test matrix (3.11 / 3.12 / 3.13)
  uv run hydramem --help      # CLI
  uv run hydramem-server      # start the MCP server

Read AGENTS.md first. Track non-trivial work in .agent/current.md.
EOF
