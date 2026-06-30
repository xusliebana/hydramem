# Agent Memory (durable lessons)

Stable, project-specific gotchas. Add a bullet when a mistake feels like it could
recur. Keep it terse. This file is versioned — it is shared knowledge, not session
scratch (that lives in `.agent/`).

## Verification & tooling

- **mypy is advisory.** The baseline is **not** clean. Do not "fix" unrelated type
  errors in a feature PR; just don't *regress* it. `nox -s typecheck` is non-blocking.
- **Coverage gate is ≥ 60%** (CI enforces). New code generally needs tests anyway.
- **Tests are async-aware:** `asyncio_mode=auto` — no need to mark every coroutine.
- **pre-commit** enforces **LF** line endings, trailing-whitespace, YAML validity,
  and max file size **500 KB**. New files must be LF and small.
- **ruff** only lints Python (`E,F,I,B,UP`, line-length 100, `E501` ignored). Shell
  and Markdown are not linted by ruff.

## Library / contract

- **Never break entry points** (`hydramem`, `hydramem-server`, `hydramem-dashboard`)
  or MCP tool signatures without a deprecation cycle + `CHANGELOG.md`. Update
  `tests/test_public_api.py` and run `nox -s api`.
- When **adding/renaming an MCP tool**, update *all four*: `hydramem/server.py`,
  `docs/mcp-tools-reference.md`, `docs/internal/CONTRACTS/PUBLIC_API.md`, `CHANGELOG.md`.
- When **adding telemetry**, extend the events schema *and* `docs/telemetry.md`.
- **`py.typed` must ship in the wheel.** Verify with `nox -s build`.

## Domain facts that are easy to get wrong

- The **chunk** path in `hydra_search` is **vector-similarity + VoG**, *not* SR-MKG.
  SR-MKG only scores **relations**.
- **Grafeo** is the default **graph** backend (and optional vector store), not just
  a vector DB. Python **3.11** falls back to **persistent NetworkX**.
- **No chain-of-thought capture** — sessions store only observable snapshots
  (ADR-0004). Don't add code that records client reasoning.
- Session store: `~/.hydramem/sessions.json`, grouped by `session_id`, deduped by
  context fingerprint; Night Gardener gates on `min_repeat_count` (default 2).

## Retrieval / algorithm changes need a benchmark

- Touching `search.py`, `ppr.py`, `verification/`, `garden/pruner.py`,
  `gnn_prune.py`, or `ingest/{chunker,embedder,extractor}.py`? Run the before/after
  benchmark — `docs/internal/PLAYBOOKS/benchmark-regression.md` (`nox -s bench`,
  `HYDRAMEM_EMBEDDER=stub` for determinism). Don't merge a silent quality regression.
- The `local` benchmark uses a **passthrough verifier** (measures retrieval, not
  VoG), so VoG/SR-MKG changes also need `tests/test_calibration.py` + the audit in
  `docs/verification.md`.

## Honesty

- Don't describe a feature/metric as working unless it measurably does. The
  "tokens saved" number comes from the naive-RAG shadow estimator
  (`hydramem/telemetry/shadow.py`) — keep it defensible.
