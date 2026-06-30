---
description: >
  Ingest one or more Markdown files into the HydraMem knowledge base.
  Chunks the documents, generates embeddings, extracts entities, and stores
  everything locally. No data leaves the machine.
tools:
  - hydramem-server
---

# hydramem-ingest

Use this skill when the user wants to add documents to the knowledge base.

## When to invoke

- "Add this file to my knowledge base."
- "Ingest all docs in the `./docs` folder."
- After creating or updating a Markdown document that should be searchable.

## Workflow

### Single file

```
ingest_markdown(file_path=<path>, project=<project>)
```

### Directory

```
ingest_directory_tool(directory=<path>, project=<project>, recursive=true)
```

## After ingestion

- Report the number of chunks and entities created.
- Suggest running `hydramem-garden` to let the Night Gardener build
  relations between the new content and existing knowledge.

## Notes

- Only `.md` files are processed.
- Re-ingesting the same file is safe (chunks are upserted by hash).
- Large directories (>100 files) may take a few minutes; embeddings are
  generated locally via `nomic-ai/nomic-embed-text-v1.5`.
