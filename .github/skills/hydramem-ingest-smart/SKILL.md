---
description: >
  Ingest a document into the HydraMem knowledge base by performing the
  semantic chunking and entity/relation extraction YOURSELF and submitting
  the structured payload. Higher quality than the regex fallback and avoids
  spinning up a separate LLM inside HydraMem. Falls back to plain
  ``ingest_markdown`` when the document is unavailable to the agent or
  exceeds the limits below.
tools:
  - hydramem-server
---

# hydramem-ingest-smart

Use this skill when the user asks you to add a document to the HydraMem
knowledge base **and** you can read the document yourself. It moves the
chunking + entity recognition work to **your** model (the one running this
session) instead of HydraMem's local LLM.

## When to invoke

- "Add this file to HydraMem."
- "Save these notes to my knowledge base."
- "Index the architecture doc."
- After producing a long Markdown artefact that should be searchable.

## When NOT to invoke (use `hydramem-ingest` instead)

- You don't have read access to the file/URL.
- Bulk ingest of an entire directory (use `ingest_directory_tool`).
- Document has > 200 chunks or > 1000 entities (hard limits — split first
  or fall back to `ingest_markdown`).

## Workflow

### Step 1 — Read the source

Read the file yourself (no shortcut: HydraMem will not read it on your
behalf in this skill). If the user pasted text directly, work from that.

### Step 2 — Chunk semantically

Split into ~400-token chunks respecting structural boundaries (headers,
function definitions, paragraphs). Aim for 1-50 chunks per document.

### Step 3 — Extract entities per chunk

For each chunk, list the named concepts that appear. Types are free-form
strings; suggested vocabulary:

- `concept`   — abstract idea ("two-phase verification")
- `tool`      — software / library ("LanceDB", "FastMCP")
- `module`    — code unit ("`VerificationPipeline`", "hydramem/garden/")
- `person`    — individual
- `protocol`  — standard / interface ("MCP", "Cypher")
- `metric`    — measurable quantity ("token-savings ratio")
- `parameter` — config knob ("`min_repeat_count`")

Deduplicate across the document: the same entity name should reuse the
same `{"name": ..., "type": ...}` shape every time it appears.

### Step 4 — Extract relations (optional but recommended)

For each chunk, list directed triples whose **both endpoints** are
entities you declared in this same payload. Format:

```json
{"from": "Night Gardener", "to": "RelationInferrer",
 "type": "DELEGATES_TO", "confidence": 0.85}
```

Suggested relation types (free-form, but prefer SCREAMING_SNAKE_CASE):
`USES`, `USED_BY`, `IMPLEMENTS`, `PART_OF`, `DELEGATES_TO`, `DEPENDS_ON`,
`DEFINED_IN`, `PRODUCES`, `VERIFIES`, `CONTRADICTS`.

Set `confidence` honestly:

- `0.9-1.0` — explicit in the text
- `0.6-0.8` — strongly implied
- `0.4-0.6` — inference from context (will likely go through VoG)
- `<0.3`    — don't include it

### Step 5 — Call the tool

```
ingest_prechunked(
  source="docs/architecture.md",            # path or logical URI
  doc_id="",                                # optional, default = hash(source)
  project="<project_or_default>",
  chunks=[
    {
      "text":     "<raw chunk 1 text>",
      "idx":      0,
      "entities": [
        {"name": "HydraMem", "type": "tool"},
        {"name": "Night Gardener", "type": "module"}
      ],
      "relations": [
        {"from": "Night Gardener", "to": "HydraMem",
         "type": "PART_OF", "confidence": 0.95}
      ]
    },
    ...
  ]
)
```

## What HydraMem does on its side

1. Embeds every chunk locally (`nomic-ai/nomic-embed-text-v1.5`, no network).
2. Persists chunks + entities + `MENTIONS` edges.
3. Runs **SR-MKG topological scoring** on each relation:
   - `score ≥ 0.7` → auto-accept
   - `score < 0.3` → reject (rejected as likely hallucination)
   - middle band   → forwarded to **VoG** semantic verifier
4. Returns counters: `chunks_added`, `entities_added`,
   `relations_proposed`, `relations_accepted`, `relations_rejected`,
   `truncated_*` (if you exceeded a limit, the excess was dropped).

## Hard limits (per call)

| Field      | Max  | What happens past limit |
|-----------|------|-------------------------|
| chunks    | 200  | extra chunks dropped (`truncated_chunks > 0`) |
| entities  | 1000 | extra entities dropped (`truncated_entities`) |
| relations | 500  | extra relations dropped (`truncated_relations`) |

Override via `HYDRAMEM_INGEST_MAX_*` env vars on the server side.

## After ingestion

- Report the counters returned by the tool.
- If `relations_rejected` is high, you may have hallucinated edges — try
  again with more conservative relations next time.
- Suggest running `hydramem-garden` only if you want long-term
  consolidation; usually unnecessary since you already extracted in-line.

## Closing a working session

When the user signals the end of a task ("done", "thanks", session end),
you may also call:

```
submit_session_extraction(
  session_id="<this session>",
  project="...",
  entities=[ {"name": "...", "type": "..."}, ... ],
  relations=[ {"from": "...", "to": "...", "type": "...", "confidence": 0.x}, ... ]
)
```

to deposit any **new** entities/relations you discovered during the
session (no chunks — just graph contributions). Same SR-MKG/VoG filter
applies.

## Privacy

All processing is local. Your chunked payload is stored on the user's
machine in the HydraMem data directory; nothing is sent to external
services unless the user opted into external embeddings or LLM
verification.
