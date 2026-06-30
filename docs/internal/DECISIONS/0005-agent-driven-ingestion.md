# 5. Agent-driven (BYO-extraction) ingestion

- **Status:** Accepted (retroactively documented)
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

HydraMem's built-in entity/relation extraction is a regex heuristic. The calling
agent (Copilot, opencode, Claude Desktop) already has a capable LLM with the
document in context. Spinning up a *second* provider inside HydraMem to re-extract
is wasteful and lower quality.

## Decision

We will let agents submit **already chunked + extracted** content through two MCP
tools, while HydraMem still owns embedding, storage, and verification:

- `ingest_prechunked(source, chunks=[{text, idx?, entities, relations?}], …)`
- `submit_session_extraction(entities, relations, session_id, project)`

Defence-in-depth: every agent-submitted relation passes the **SR-MKG (+ VoG)**
filter (`ingest.verify_agent_relations`, default `true`); hard caps
(`ingest.max_chunks/max_entities/max_relations`, default 200/1000/500) bound
payloads; provenance (`origin_tool`, `session_id`) keeps the graph auditable and
revertible. The `hydramem-ingest-smart` skill instructs agents on honest
extraction with a fallback to plain `ingest_markdown`.

## Consequences

- Positive: higher-quality extraction, no second LLM, lower latency; the agent's
  loaded context is reused; graph stays auditable.
- Trade-off: trust boundary moves to the agent — mitigated by the mandatory
  verifier pass and caps. Turning verification off is explicitly "not recommended".
- Obligation: keep the verifier and caps on by default; never present
  agent-trusted mode as safe.

## References

- [../../CHANGELOG.md](../../../CHANGELOG.md) (0.2.0),
  [../../.github/skills/hydramem-ingest-smart/SKILL.md](../../../.github/skills/hydramem-ingest-smart/SKILL.md),
  [../mcp-tools-reference.md](../../mcp-tools-reference.md)
