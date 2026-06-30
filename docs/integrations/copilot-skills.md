# GitHub Copilot Agent Skills (HydraMem)

HydraMem ships six Copilot skills in
`/home/runner/work/hydramem/hydramem/.github/skills/` so agent-mode workflows can
use a predictable pattern to **ingest knowledge**, **recover context**, and
**maintain graph quality**.

## Skill map

| Skill | Purpose | Main MCP tools | Context flow |
|---|---|---|---|
| `hydramem-ingest` | Ingest Markdown files/directories | `ingest_markdown`, `ingest_directory_tool` | Adds new searchable chunks/entities. |
| `hydramem-ingest-smart` | Agent-led semantic ingestion | `ingest_prechunked`, `submit_session_extraction` | Injects high-quality structured context into memory. |
| `hydramem-query` | Direct factual lookup with citations | `priming_context_tool` | Recovers top chunks + neighbours, then injects them into answer prompt. |
| `hydramem-reason` | Multi-hop reasoning across graph | `hydra_search_tool` | Recovers expanded graph context for cross-document reasoning. |
| `hydramem-link` | Manual relation curation | `create_relation`, `delete_relation`, `check_conflict_tool` | Improves graph structure so future retrieval is better grounded. |
| `hydramem-garden` | Autonomous maintenance cycle | `get_garden_status_tool`, `run_night_gardener`, `train_gnn_tool` | Consolidates and prunes context after ingestion bursts. |

## Context injection and retrieval patterns

### 1) Inject context into HydraMem

Use these when the goal is to **store new knowledge**:

- **`hydramem-ingest`** for standard Markdown indexing.
- **`hydramem-ingest-smart`** when the agent can read and chunk the content itself
  and submit entities/relations directly.
- **`hydramem-link`** when you need to manually add/remove explicit graph edges.

### 2) Recover context for answers/search

Use these when the goal is to **answer with grounded memory**:

- **`hydramem-query`** for direct questions, where `priming_context_tool`
  retrieves focused evidence blocks for citation-backed answers.
- **`hydramem-reason`** for multi-hop or causal questions, where
  `hydra_search_tool` expands through graph links to build richer context.

### 3) Keep context quality high over time

- **`hydramem-garden`** runs inference + verification + pruning after heavy
  ingestion or on periodic maintenance windows.

## Recommended Copilot flow

1. Ingest docs/notes (`hydramem-ingest` or `hydramem-ingest-smart`).
2. Ask factual questions (`hydramem-query`) or deep relationship questions
   (`hydramem-reason`).
3. Curate critical edges manually when needed (`hydramem-link`).
4. Run maintenance (`hydramem-garden`) after significant updates.

This keeps retrieval grounded while steadily improving long-term context quality.
