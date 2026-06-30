---
description: >
  Deep multi-hop reasoning over the knowledge graph. Use when the question
  requires connecting information from multiple documents, understanding
  cause-effect chains, or tracing implicit relationships.
tools:
  - hydramem-server
---

# hydramem-reason

Use this skill for questions that require combining information from several
sources or traversing implicit relations in the knowledge graph.

## When to invoke

- "How did X affect Y?" (causal chains)
- "What is the relationship between A and B?"
- "Explain the impact of decision X on outcomes Y and Z."
- Any question where a single document is unlikely to contain the full answer.

## Workflow

1. Call `hydra_search_tool` with the question and `max_hops=3`.
2. The tool performs vector search + graph expansion + SR-MKG/VoG filtering.
3. Use `result.final_context` as the grounded context for your answer.
4. If `avg_vog_score < 0.5`, add a caveat: "Note: some connections have low
   confidence and should be verified."
5. If `hallucinations_blocked > 0` is implied (verified list is empty),
   state: "Insufficient verified evidence found."

## MCP Tool

```
hydra_search_tool(query=<question>, max_hops=3, project=<project>)
```

## Output format

Provide a structured answer with:
- A direct response paragraph.
- A **Reasoning trace** section showing which entities/chunks were connected.
- A **Sources** section with citations.
- A **Confidence** line: `VoG avg: X.XX`.
