# 7. Supported Python version policy

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

Supporting too many Python versions slows CI and constrains code; too few drops
users. The native Grafeo graph backend only ships wheels for Python ≥ 3.12, while
many environments are still on 3.11.

## Decision

We will support **Python 3.11, 3.12, and 3.13**, tested as a matrix in CI and via
`nox -s tests`. Guided by **[Scientific-Python SPEC 0](https://scientific-python.org/specs/spec-0000/)**
(a rolling support window), we drop end-of-life Python versions in a **minor**
release with a `CHANGELOG.md` note. `requires-python` in
[../../pyproject.toml](../../../pyproject.toml) is the single source of truth.

- The dev pin ([../../.python-version](../../../.python-version)) is **3.12** (matches
  the Docker image; enables Grafeo).
- **3.11** must keep working via the **persistent NetworkX** graph fallback
  (Grafeo is gated by `python_version >= '3.12'`).

## Consequences

- Positive: clear, bounded test matrix; users on 3.11 are not stranded.
- Trade-off: code must avoid 3.12+-only syntax and preserve the 3.11 fallback path.
- Obligation: when dropping a version, update `requires-python`, the CI matrix, and
  `noxfile.py` together.

## References

- [Scientific-Python SPEC 0](https://scientific-python.org/specs/spec-0000/),
  [../CONSTRAINTS.md](../CONSTRAINTS.md), [../../pyproject.toml](../../../pyproject.toml)
