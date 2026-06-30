# 2. Pluggable storage backends; Grafeo by default

- **Status:** Accepted (retroactively documented)
- **Date:** 2026-06-30
- **Deciders:** HydraMem maintainers

## Context

HydraMem needs a persistent **graph** store (entities/relations, multi-hop
traversal) and a persistent **vector** store (chunks + embeddings). Earlier
versions used Kuzu/LadybugDB for the graph and LanceDB for vectors, which meant
two stores, heavier native binaries, and dual-directory drift risk.

## Decision

We will treat storage as a **dependency-injected seam** (abstract base classes in
`hydramem/storage/`) and default to **[Grafeo](https://pypi.org/project/grafeo/)**
(Rust core via PyO3, Apache-2.0, ~5 MB wheel) for the graph. Grafeo can also hold
the HNSW vector index, so a single embedded directory supports full hybrid search.
Backends are selectable via environment switches:

- `HYDRAMEM_GRAPH_BACKEND` ∈ `grafeo` (default) | `kuzu` | `ladybug`
- `HYDRAMEM_VECTOR_BACKEND` ∈ `grafeo` (default) | `lancedb` | `memory`
- On Python **3.11** (no Grafeo wheel) the graph falls back to a **persistent
  NetworkX** store.

## Consequences

- Positive: one small default dependency; ACID writes to a single DB; LanceDB
  optional; backends remain swappable and unit-testable via the base classes.
- Trade-off: must maintain multiple backend adapters and a fallback chain
  (Grafeo → LanceDB → memory for vectors; Grafeo → NetworkX for the graph).
- Obligation: keep the 3.11/NetworkX path working; defensively parse Grafeo row
  shapes for forward compatibility.

## References

- [../../CHANGELOG.md](../../../CHANGELOG.md) (0.2.0), [../architecture.md](../../architecture.md),
  [../configuration.md](../../configuration.md)
