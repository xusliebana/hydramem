# Definition of Done

A change is **done** only when every applicable box is checked with **evidence**
(a command you actually ran, not an assumption). This is the final gate before a
PR is opened or a task is marked complete. It absorbs the checklist in
[CONTRIBUTING.md](../../CONTRIBUTING.md) and the `.github/PULL_REQUEST_TEMPLATE.md`.

## Always

- [ ] **Scope.** The change addresses one concern and nothing extra.
- [ ] **Tests.** Behaviour change ships with a test. `nox -s tests` passes
      (or `uv run pytest`). Coverage stays ≥ 60%.
- [ ] **Lint/format.** `nox -s lint` is clean (`ruff check` + `ruff format --check`).
- [ ] **Types.** `nox -s typecheck` does not *regress* the mypy baseline (advisory).
- [ ] **Honesty.** Any claim in docs, dashboard, or metrics matches what the code
      actually does. No aspirational wording. See the honesty contract in
      [AGENTS.md](../AGENTS.md).
- [ ] **Conventional commit** message with an allowed scope.

## If the public surface is touched

(entry points, CLI flags, MCP tools, documented Python API, config keys)

- [ ] Backward-compatible, **or** a `DeprecationWarning` + one-cycle window is in place.
- [ ] [CHANGELOG.md](../CHANGELOG.md) updated.
- [ ] [CONTRACTS/PUBLIC_API.md](CONTRACTS/PUBLIC_API.md) updated (and
      [mcp-tools-reference.md](../mcp-tools-reference.md) if a tool changed).
- [ ] `nox -s api` passes (public-API surface test).

## If packaging / dependencies are touched

- [ ] `nox -s build` passes (`uv build` + `twine check`); `py.typed` is present in
      the built wheel.
- [ ] New heavy dependency is behind an extra and justified (ADR if architectural).
- [ ] Supported Python matrix (3.11/3.12/3.13) still green, including the 3.11
      NetworkX fallback.

## If you changed a retrieval / ranking / pruning / verification algorithm

(e.g. a new pruning algorithm, a new VoG variant, a re-ranker, a different chunker)

- [ ] Ran the before/after benchmark per
      [PLAYBOOKS/benchmark-regression.md](PLAYBOOKS/benchmark-regression.md) and
      attached both tables (Recall@{1,3,5} + MRR) as evidence.
- [ ] Retrieval is **not worse**, or the regression is explicitly justified in the
      PR (and an [ADR](DECISIONS/README.md) if it is a permanent trade-off).
- [ ] For VoG / SR-MKG changes: also ran
      `uv run pytest tests/test_calibration.py tests/test_verify.py`.

## If it is a release

- [ ] Follow [PLAYBOOKS/release.md](PLAYBOOKS/release.md).

## Final gate

- [ ] `nox -s verify` passes.
- [ ] For non-trivial work: `.agent/current.md` updated and a summary written to
      `.agent/logs/`; working tree clean.

> Reviewer's reminder (see [REVIEW.md](REVIEW.md)): the **author** is optimistic by
> default. Re-check this list as a fresh-context **checker** before accepting.
