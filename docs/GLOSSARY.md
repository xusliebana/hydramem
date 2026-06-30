# Glossary

Domain terms used across HydraMem. Use these definitions to avoid semantic drift.

| Term | Definition |
|---|---|
| **SR-MKG** | *Structured Relation – Mutual Knowledge Graph.* A pure-Python, topological scorer that ranks/filters candidate **relations** using graph structure and heuristic weights — **no LLM**. Stage 1 of verification. |
| **VoG** | *Verification of Groundedness.* An LLM step that checks whether a candidate is grounded in retrieved evidence. Stage 2 of verification; also used for the chunk path. |
| **Chunk prefilter** | The **vector-similarity** (cosine) filter applied to chunks inside `hydra_search`. It is **not** SR-MKG; only relations go through SR-MKG. |
| **Night Gardener** | The autonomous offline cycle that runs in three phases — **infer → verify → prune** — to refine the graph. Honest contract: emits **zero** relations when there is no real evidence. |
| **Fast path** | Low-latency retrieval with **no LLM**: vector ANN + entity term match + 1-hop expansion. Used by `priming_context`. |
| **Full path** | High-precision retrieval: vector ANN + multi-hop graph traversal + SR-MKG + VoG. Used by `hydra_search`. |
| **`priming_context`** | Fast-path tool returning top-k chunks + neighbouring entity names for the agent to expand. |
| **`hydra_search`** | Full-path tool returning verified context with metadata. |
| **`expand_context`** | Multi-hop graph traversal from known entity IDs. |
| **`trace_path`** | Shortest path between two entities (NetworkX `shortest_path`). |
| **MENTIONS** | The edge type linking a chunk to an entity it references. |
| **Hyper-relational qualifier** | Extra key/value context attached to a relation (subject–predicate–object **+ qualifiers**), making relations first-class hyper-edges. |
| **PPR** | *Personalized PageRank* retrieval (HippoRAG-style), in `hydramem/ppr.py`. |
| **CRDT** | *Conflict-free Replicated Data Type*, used by the garden (`hydramem/garden/crdt.py`) for mergeable state. |
| **LightGNN pruning** | Optional GNN-based spurious-edge detection (`hydramem/gnn_prune.py`); heuristic fallback; auto-skips on graphs larger than `HYDRAMEM_GNN_MAX_NODES`. |
| **Honesty contract** | The project rule that no feature/metric is described as working unless it measurably works; the dashboard must reflect reality. |
| **Shadow estimator** | The naive-RAG baseline used to estimate token savings (`hydramem/telemetry/shadow.py`); the source of the "tokens saved" metric. |
| **Grafeo / LadybugDB** | The persistent **graph** backend (Grafeo = Rust core via PyO3; LadybugDB = a Kuzu fork). On Python 3.11 the graph falls back to a NetworkX persistent store. |
| **LanceDB** | The persistent **vector** store for chunks + embeddings. |
| **fastembed** | The default lightweight ONNX embedder (~80 MB, no torch); falls back to `sentence-transformers` when configured. |
| **MCP** | *Model Context Protocol* — the agent-facing tool protocol served by FastMCP in `hydramem/server.py`. |
| **Project namespacing** | Per-`project` isolation of stored data so multiple knowledge bases coexist in one deployment. |
| **`min_repeat_count`** | Night Gardener config gating how many times a session snapshot must repeat before it is considered for inference (default `2`). |
| **Calibration** | Per-project tuning of SR-MKG/verification thresholds (`tests/test_calibration.py`). |
