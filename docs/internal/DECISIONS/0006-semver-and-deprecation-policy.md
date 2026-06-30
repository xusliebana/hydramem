# 6. SemVer + deprecation policy for the public API

- **Status:** Accepted
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

`hydramem` is published on PyPI and consumed via console scripts, an MCP server,
and a documented Python surface. Downstream users and agent integrations break
when these change silently. We need a predictable change policy.

## Decision

We will follow **[Semantic Versioning](https://semver.org/)** and treat the
surface in [../CONTRACTS/PUBLIC_API.md](../CONTRACTS/PUBLIC_API.md) as a contract:

- **Pre-1.0 (`0.x`):** minor bumps *may* break APIs, but every break is announced
  in [../../CHANGELOG.md](../../../CHANGELOG.md) (Keep a Changelog format).
- **Post-1.0:** breaking changes require a **major** bump. Deprecations ship a
  `DeprecationWarning` and remain functional for **at least one minor cycle**
  before removal, with a migration note in the changelog.
- Additive changes (new tool, new optional argument, new config key with a safe
  default) are backward-compatible and allowed in minor releases.

Enforcement is mechanical where possible: `tests/test_public_api.py` guards the
import/entry-point surface (`nox -s api`).

## Consequences

- Positive: predictable upgrades; agents can rely on tool signatures; reviewers
  have a clear rule to apply.
- Trade-off: maintaining deprecation shims and the surface test adds work.
- Obligation: the [DEFINITION_OF_DONE.md](../DEFINITION_OF_DONE.md) "public surface"
  checklist must be honoured on every relevant PR.

## References

- [../CONTRACTS/PUBLIC_API.md](../CONTRACTS/PUBLIC_API.md), [../../CONTRIBUTING.md](../../../CONTRIBUTING.md)
