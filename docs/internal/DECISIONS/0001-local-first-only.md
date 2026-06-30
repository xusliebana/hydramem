# 1. Local-first, zero exfiltration by default

- **Status:** Accepted (retroactively documented)
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

HydraMem stores a user's knowledge base — potentially private notes, code, and
session content. AI-agent tooling frequently leaks such data to third-party APIs.
The project's positioning is "private, local-first memory for agents."

## Decision

We will run **100% locally by default** with **zero data exfiltration**. Cloud
LLM providers (OpenAI, Anthropic) are used **only** when the user explicitly
configures them. Telemetry is **opt-in**, stored in a local SQLite database, and
contains no content or queries. Secrets are read from environment variables only.

## Consequences

- Positive: strong privacy guarantee; the project is usable offline; easy to audit
  (`hydramem stats --raw`).
- Trade-off: the default embedder/LLM stack must work without cloud calls (hence
  ONNX `fastembed` + optional Ollama), which bounds default quality.
- Obligation: every feature must preserve an offline default path. Network calls
  require explicit user configuration and must be documented.

## References

- [../CONSTRAINTS.md](../CONSTRAINTS.md), [../../SECURITY.md](../../../SECURITY.md),
  [../telemetry.md](../../telemetry.md)
