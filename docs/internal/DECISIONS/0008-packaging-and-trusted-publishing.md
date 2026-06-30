# 8. Hatchling packaging + PyPI trusted publishing

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

As a PyPI library, HydraMem needs a reproducible build and a secure release path.
Long-lived PyPI API tokens are a supply-chain risk, and ad-hoc local builds are
hard to audit.

## Decision

We will build with **Hatchling** (`build-backend = "hatchling.build"`) producing
an sdist + wheel, and publish from CI using **PyPI Trusted Publishing (OIDC)** —
no long-lived tokens. The version is single-sourced from
[../../pyproject.toml](../../../pyproject.toml). The wheel ships the `py.typed`
marker (PEP 561). Releases follow [../PLAYBOOKS/release.md](../PLAYBOOKS/release.md)
and are validated with `nox -s build` (`uv build` + `twine check`).

This aligns with **[Scientific-Python SPEC 8](https://scientific-python.org/specs/spec-0008/)**
(securing the release process).

## Consequences

- Positive: no token to leak; reproducible, auditable releases; typed package.
- Trade-off: releases must go through CI (a tagged workflow), not a maintainer's
  laptop.
- Obligation: keep `py.typed` packaged and the trusted-publisher configuration in
  sync with the GitHub workflow.

## References

- [../PLAYBOOKS/release.md](../PLAYBOOKS/release.md),
  [Scientific-Python SPEC 8](https://scientific-python.org/specs/spec-0008/),
  [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
