# Hyper-Relational Knowledge Schema 🟡

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Mid-term bet — schema-level change with broad downstream wins

## Why it matters

Today a `Relation` is a flat record:
`(from_entity, relation_type, to_entity, confidence, project, session_id, created_at)`.
Provenance lives in side columns and is invisible to graph queries. There
is **no way** to express:

- temporal validity (`valid_from`, `valid_to`)
- multiple co-existing pieces of evidence with different confidences
- the verifier identity (SR-MKG-only vs. VoG vs. human)
- derived-from relations (a relation inferred from another relation)

A **hyper-relational schema** treats every relation as a hyperedge with
*qualifiers*: `(h, r, t, {qualifier_k: qualifier_v})`. This is the
RDF-star data model and the format used by recent KG models like StarE
and HINGE. It unlocks principled provenance, temporal queries, and
fairer SR-MKG scoring (a contradicted-but-fresh edge ≠ a stale one).

## State of the art

- **RDF-star / SPARQL-star** (W3C, ratified 2024)
- **StarE** (Galkin et al., 2020) — first transformer for hyper-relational KGs
- **HINGE** (Rosso et al., 2020) — convolutional hyper-relational embeddings
- **GRAN** (Wang et al., 2021) — graph attention over qualifiers
- **NeuInfer** — fact prediction with qualifier conditioning

## Proposed architecture

### Schema additions

```python
# hydramem/core/types.py
@dataclass
class Relation:
    # existing
    from_entity: str
    to_entity: str
    relation_type: str
    confidence: float
    project: str
    session_id: str
    created_at: str
    origin_tool: str
    # NEW
    qualifiers: dict[str, str] = field(default_factory=dict)
    # canonical reserved keys: "valid_from", "valid_to", "verifier",
    # "evidence_chunk_id", "derived_from", "source_doc"
```

### Storage

- **Kuzu / LadybugDB**: leverage native property maps on rels (already
  supported); persist `qualifiers` as a JSON-encoded property + denormalised
  index columns for the canonical keys.
- **NetworkX fallback**: `data["qualifiers"]` dict on each edge.

### Reserved qualifier vocabulary

| Key | Meaning |
|-----|---------|
| `valid_from`, `valid_to` | temporal validity (ISO-8601) |
| `verifier` | `srmkg` \| `vog` \| `manual` \| `gnn` |
| `evidence_chunk_id` | provenance link to LanceDB chunk |
| `derived_from` | id of parent relation if inferred |
| `source_doc` | document path or hash |

### SR-MKG impact

Penalise relations whose qualifier sets contradict each other (same
`(h,r,t)` with overlapping temporal validity but different `verifier`
verdicts → reduce score).

### Federated export impact

Qualifiers ride along in the signed envelope; the schema bump is
backwards-compatible (missing qualifiers = empty dict).

## Risks

- **Migration cost** of the existing graph. Provide a one-shot migration
  script that fills `qualifiers = {}` for all legacy edges.
- **Index bloat** if qualifier keys are unbounded. Mitigate by reserving
  a fixed canonical set; everything else stays in JSON.
- **API surface creep** in MCP tools. Keep the simple `(h, r, t)`
  signature in tools and accept qualifiers as optional dict.

## Computational cost

- Storage: +5–15 % per relation, dominated by JSON encoding.
- Query: negligible for canonical keys (indexed); JSON scan for the rest.

## Privacy implications

Improves auditability — neutral-to-positive impact.

## Local-first viability

Excellent. Kuzu handles property maps natively.

## Suggested implementation strategy

1. Extend `Relation` dataclass + serialization.
2. Migrate Kuzu schema; add migration script
   `scripts/migrate_qualifiers.py`.
3. Update NetworkX fallback edge attrs.
4. Update `RelationInferrer` to attach `verifier`, `evidence_chunk_id`,
   `derived_from`.
5. Update VoG to attach `verifier=vog` and confidence history.
6. Update federated export/import format to v2 (with backwards-compat
   reader for v1).
7. Document the canonical vocabulary in
   [`docs/architecture.md`](../../architecture.md).

## Concrete code changes

| File | Change |
|------|--------|
| [`hydramem/core/types.py`](../../../hydramem/core/types.py) | Add `qualifiers` field |
| [`hydramem/storage/graph/ladybug_repo.py`](../../../hydramem/storage/graph/ladybug_repo.py) | Persist + index canonical keys |
| [`hydramem/storage/graph/networkx_repo.py`](../../../hydramem/storage/graph/networkx_repo.py) | Edge attrs |
| [`hydramem/garden/inferrer.py`](../../../hydramem/garden/inferrer.py) | Emit qualifiers |
| [`hydramem/verification/pipeline.py`](../../../hydramem/verification/pipeline.py) | Stamp `verifier` |
| [`hydramem/storage/federation.py`](../../../hydramem/storage/federation.py) | Schema v2 with v1 fallback |
| `scripts/migrate_qualifiers.py` | **NEW** |
| `tests/test_provenance_and_graph.py` | Cover qualifier round-trip |
| [`docs/architecture.md`](../../architecture.md) | Canonical vocabulary table |

## References

- Galkin et al., *Message Passing for Hyper-Relational Knowledge Graphs*
  (StarE), EMNLP 2020
- Rosso et al., *Beyond Triplets: Hyper-Relational Knowledge Graph
  Embedding for Link Prediction*, WWW 2020
- W3C, *RDF-star and SPARQL-star Recommendation*, 2024
- Wang et al., *Link Prediction on N-ary Relational Data Based on
  Relatedness Evaluation*, 2021 (GRAN)
