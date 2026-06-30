# 4. No client chain-of-thought capture

- **Status:** Accepted (retroactively documented)
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

HydraMem persists session knowledge to power the Night Gardener and cross-session
recall. A tempting source of signal is the client model's private reasoning
(chain-of-thought). Capturing it would be a privacy violation, would bloat
storage, and would couple HydraMem to provider-internal formats.

## Decision

We will persist **only observable snapshots** of a session (inputs/outputs and
tool I/O the client chooses to share). We will **not** capture, store, or infer
client chain-of-thought. Session entries are deduplicated by context fingerprint
(`repeat_count` / `last_seen_at`) and gated for inference by
`night_gardener.min_repeat_count` (default `2`).

## Consequences

- Positive: privacy-preserving and provider-agnostic; smaller, auditable session
  store; aligns with the local-first contract (ADR-0001).
- Trade-off: the Night Gardener has less raw signal and must rely on repeated,
  observable evidence — by design, this reduces speculative inference.
- Obligation: tools that persist sessions must strip anything resembling private
  reasoning; this rule is part of the public honesty contract.

## References

- [../night-gardener.md](../../night-gardener.md), [../telemetry.md](../../telemetry.md),
  [../CONSTRAINTS.md](../CONSTRAINTS.md)
