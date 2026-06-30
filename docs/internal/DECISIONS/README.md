# Architecture Decision Records

Permanent technical decisions for HydraMem. ADRs are **not** task history — they
capture *why* the project is the way it is, and they outlive any single change.

- Use [0000-adr-template.md](0000-adr-template.md) for new records.
- Number sequentially; never delete an ADR — supersede it with a new one and link both.
- A decision is "permanent" if reversing it would be expensive or contentious.

| # | Title | Status |
|---|---|---|
| [0001](0001-local-first-only.md) | Local-first, zero exfiltration by default | Accepted |
| [0002](0002-storage-backends.md) | Pluggable storage backends; Grafeo by default | Accepted |
| [0003](0003-two-stage-verification.md) | Two-stage relation verification (SR-MKG + VoG) | Accepted |
| [0004](0004-no-chain-of-thought-capture.md) | No client chain-of-thought capture | Accepted |
| [0005](0005-agent-driven-ingestion.md) | Agent-driven (BYO-extraction) ingestion | Accepted |
| [0006](0006-semver-and-deprecation-policy.md) | SemVer + deprecation policy for the public API | Accepted |
| [0007](0007-python-support-policy.md) | Supported Python version policy | Accepted |
| [0008](0008-packaging-and-trusted-publishing.md) | Hatchling packaging + PyPI trusted publishing | Accepted |
