---
description: >
  Ask a direct question to HydraMem and get a grounded, source-cited answer
  from the local knowledge base. Use for factual lookups, "what does X mean?",
  and "what does the docs say about Y?" queries.
tools:
  - hydramem-server
---

# hydramem-query

Use this skill when the user asks a direct, factual question that might be
answered by the ingested knowledge base.

## When to invoke

- "What does [document / concept] say about X?"
- "How does Y work according to our docs?"
- Direct lookup questions where a single, grounded answer is expected.

## Workflow

1. Call `priming_context` with the user's question to retrieve the top-3
   most relevant chunks and their immediate graph neighbours.
2. Inject the returned `context` into the system prompt with the instruction:
   "Answer using only the sources below. Cite [N] for each claim."
3. If `chunks` is empty, tell the user that no relevant content was found
   and suggest running `hydramem-ingest` first.

## MCP Tool

```
priming_context_tool(query=<user_question>, k=3, project=<project>)
```

## Output format

Reply with a concise answer and inline citations like `[1]`, followed by a
**Sources** section listing the source file for each cited chunk.
