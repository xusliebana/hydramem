---
description: >
  Manually curate the knowledge graph: create, verify, or delete explicit
  relations between entities. Use to encode domain knowledge that the
  Night Gardener has not yet inferred automatically.
tools:
  - hydramem-server
---

# hydramem-link

Use this skill when the user wants to manually establish or remove an explicit
relationship between two concepts in the knowledge graph.

## When to invoke

- "Link 'Rust migration' to 'reduced memory usage' with relation 'caused'."
- "Delete the relation between X and Y."
- "Is there a conflict between what document A says about X and document B says about Y?"

## Workflows

### Create a verified relation

```
create_relation(
    from_entity=<name_or_id>,
    to_entity=<name_or_id>,
    relation_type=<e.g. "caused" | "requires" | "contradicts">,
    verify=true,
    project=<project>
)
```

The tool runs the SR-MKG + VoG pipeline before committing. If verification
fails, it returns `created: false` with an explanation.

### Delete a relation

```
delete_relation(from_entity=<id>, to_entity=<id>, relation_type=<type>)
```

### Conflict check

```
check_conflict_tool(
    entity_a=<name>, entity_b=<name>,
    text_a=<passage about A>, text_b=<passage about B>
)
```

## Notes

- Entity IDs can be obtained with `list_entities_tool`.
- The `verify=true` flag is the default and recommended; set `false` only
  for manually curated, high-confidence links.
