# Reasoning Motifs (Privacy-Safe CoT Abstraction) 🔵

> **Roadmap slot:** Research branch — no shipping commitment (👍 vote to prioritize)
> **Owner:** unassigned
> **Status:** Long-term research, but designed to ship incrementally

## Why it matters

HydraMem **must not** capture the agent's chain-of-thought. But it can
observe **which public graph nodes the agent traverses** during a session
(through tool calls), without storing any private text. If across many
sessions the agent repeatedly walks `[Concept] → [Implementation] →
[Test]`, that **subgraph motif** is a property of the *corpus*, not of
the user. Mining motifs gives:

- **Proactive expansion**: when a query enters at the start of a known
  motif, pre-fetch its tail
- **Subgraph caching** for hot patterns
- A privacy-safe abstract representation of "how this corpus is reasoned
  about" — which is the only legitimate variant of *CoT capture* in a
  local-first memory layer

This is HydraMem's **most differentiated** feature on the roadmap. No
existing GraphRAG / memory system does it.

## State of the art

- **Network motifs** (Milo et al., 2002) — foundational
- **Graphlet kernels** (Shervashidze et al., 2009)
- **subgraph2vec** (Narayanan et al., 2017) — embeddings for subgraphs
- **GLAMOUR / GraSP** — modern motif discovery in heterogeneous graphs
- **Path-based reasoning** (PathCon, NBFNet) — adjacent literature

## Proposed architecture

### What is recorded

Every tool call already produces a session entry. Extend it with an
**ordered traversal record** containing only graph identifiers:

```json
{
  "session_id": "...",
  "ts": "...",
  "tool_name": "expand_context",
  "traversal": {
    "entry_entities": ["e_42", "e_77"],
    "visited": [
      {"entity_id": "e_42", "via_relation": null,         "hop": 0},
      {"entity_id": "e_91", "via_relation": "depends_on", "hop": 1},
      {"entity_id": "e_134","via_relation": "tested_by",  "hop": 2}
    ]
  }
}
```

**Important:** never store user text in this structure.

### Mining (in Night Gardener)

```
For k in [2, 3, 4]:
  enumerate length-k typed paths across all traversals
  count support
  compute lift = support / Π(marginal type frequencies)
  keep motifs with support >= S_min and lift >= L_min and unique sessions >= U_min
```

Persist as:

```json
{
  "motif_id": "m_001",
  "pattern": ["concept", "depends_on", "implementation", "tested_by", "test"],
  "support": 47,
  "lift": 6.3,
  "unique_sessions": 12,
  "last_seen": "2026-05-08T..."
}
```

### Use sites

1. **Priming**: if `priming_context` finds a query that matches the head
   of a motif, optionally pre-attach its tail to the response.
2. **Cache**: precompute the resolved subgraph for hot motifs to skip
   BFS/PPR.
3. **Future**: condition retrieval planner on the motif distribution.

### Configuration

```yaml
motifs:
  enabled: true
  min_k: 2
  max_k: 4
  min_support: 5
  min_unique_sessions: 3
  min_lift: 2.0
  privacy:
    discard_traversals_below_unique_sessions: 3
```

The last knob enforces that any motif used at retrieval time must come
from at least 3 distinct sessions — preventing single-user pattern
exposure.

## Risks

- **Privacy contract** — must be airtight. No motif may leak content.
  Audit by inspecting `traversal_logs` schema in tests; CI assertion
  that no string field other than entity ids / relation types exists.
- **Overfitting to one user's habits** — the `min_unique_sessions`
  threshold mitigates this.
- **Motif explosion** at k=4 on dense graphs. Bound enumeration with
  beam search.
- **Stale motifs** as the graph evolves. TTL + recompute.

## Computational cost

- Mining at k≤4 on 10⁴ traversal records: minutes per Night Gardener run
- Use-site lookup: O(motifs) hash, sub-millisecond

## Privacy implications

This is the central concern. Design rules:

1. `traversal` field contains only opaque entity ids and relation types
   that already exist as public graph data.
2. The original session text is **already** restricted to grounded
   context returned by HydraMem, never the agent's CoT (existing
   contract).
3. Motifs that match a single session are discarded.
4. Federated export must strip traversals by default.
5. Document this contract in [`../verification.md`](../../verification.md)
   and add a test that fails CI if the traversal record contains free
   text.

## Local-first viability

Excellent.

## Suggested implementation strategy

### Phase A — Logging (0.5.x)

1. Extend `Session` schema with `traversal` field.
2. Tools that traverse the graph emit traversal records.
3. CI test: traversal contains no free text.

### Phase B — Mining (0.5.x)

4. `hydramem/garden/motifs.py` — k-path miner with support / lift / unique
   sessions.
5. Persist motifs under `~/.hydramem/projects/<p>/motifs.json`.
6. `garden-status` exposes counts.

### Phase C — Use (1.x)

7. Hook `priming_context` to optionally pre-attach motif tails.
8. Subgraph cache layer.
9. Optional embedding of motifs (subgraph2vec) for similarity matching.

### Phase D — Research (1.x+, branch)

10. Contrastive learning over motifs as a representation of corpus
    reasoning style; expose via a new MCP tool.

## Concrete code changes

| File | Change |
|------|--------|
| [`hydramem/core/types.py`](../../../hydramem/core/types.py) | `TraversalRecord` dataclass |
| [`hydramem/garden/repository.py`](../../../hydramem/garden/repository.py) | Persist traversals |
| [`hydramem/search.py`](../../../hydramem/search.py) | Emit traversals |
| `hydramem/garden/motifs.py` | **NEW** — miner |
| [`hydramem/garden/gardener.py`](../../../hydramem/garden/gardener.py) | New mining phase |
| [`hydramem/server.py`](../../../hydramem/server.py) | Optional motif injection in `priming_context_tool` |
| [`hydramem/storage/federation.py`](../../../hydramem/storage/federation.py) | Strip traversals on export by default |
| `tests/test_motifs.py` | **NEW** — privacy + mining correctness |
| [`docs/verification.md`](../../verification.md) | Document privacy contract |

## References

- Milo et al., *Network Motifs: Simple Building Blocks of Complex
  Networks*, Science 2002
- Shervashidze et al., *Efficient Graphlet Kernels for Large Graph
  Comparison*, AISTATS 2009
- Narayanan et al., *subgraph2vec: Learning Distributed Representations
  of Rooted Sub-graphs from Large Graphs*, MLG 2017
- McClelland & O'Reilly (1995) — biological motivation
