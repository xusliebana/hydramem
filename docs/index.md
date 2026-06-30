---
hide:
  - navigation
  - toc
---

<section class="hm-hero" markdown>

<span class="hm-hero__badge">🧠 100% local · MCP-native · MIT-licensed</span>

# Memory your AI agent **actually keeps** { .hm-hero__title }

Local, private long-term memory for AI coding agents — hybrid **graph + vector**
search, two-stage verification, and an autonomous **Night Gardener**. Runs entirely
on your machine. Zero cloud by default.
{ .hm-hero__subtitle }

[🚀&nbsp; Quick Start](getting-started/){ .md-button .md-button--primary }
[★&nbsp; Star on GitHub](https://github.com/xusliebana/hydramem){ .md-button }
{ .hm-hero__cta }

```bash
uv tool install git+https://github.com/xusliebana/hydramem
hydramem init ~/my-memory && cd ~/my-memory
hydramem ingest ./kms && hydramem search "what did we decide about auth?"
```

</section>

<div class="hm-stats reveal" markdown>
<div class="hm-stat"><span class="hm-stat__num" data-count="77.8" data-suffix="%" data-dec="1">0</span><span class="hm-stat__label">token savings vs naive RAG<br><em>auditable, not a vibe</em></span></div>
<div class="hm-stat"><span class="hm-stat__num" data-count="18" data-suffix="" data-dec="0">0</span><span class="hm-stat__label">MCP tools<br><em>Claude Desktop · Cursor · OpenCode</em></span></div>
<div class="hm-stat"><span class="hm-stat__num" data-count="5" data-suffix="k" data-dec="0">0</span><span class="hm-stat__label">lines of code<br><em>readable in an afternoon</em></span></div>
<div class="hm-stat"><span class="hm-stat__num" data-count="0" data-suffix="" data-dec="0">0</span><span class="hm-stat__label">bytes sent to the cloud<br><em>by default</em></span></div>
</div>

<div class="hm-terminal reveal" markdown>

```text
$ hydramem stats --last-7d
╭─────────────────────────────────────────────────╮
│  HydraMem Stats – last 7 days                   │
├──────────────────────────┬──────────────────────┤
│ Tool calls               │                 142  │
│ Tokens (naive RAG)       │               1.4M   │
│ Tokens injected          │               312K   │
│ Tokens saved             │    1.09M (77.8%)     │
│ Avg VoG score            │              0.887   │
│ Rejected by SR-MKG       │                 89   │
│ Hallucinations blocked   │                  5   │
╰──────────────────────────┴──────────────────────╯
```

</div>

## Why HydraMem { .hm-section .reveal }

<div class="grid cards reveal" markdown>

-   :material-shield-lock:{ .lg .middle } &nbsp;__100% local, zero exfiltration__

    ---

    Your codebase context, graph, vectors and telemetry never leave your machine.
    No cloud memory service in the loop. Secrets come from env vars only.

-   :material-graph-outline:{ .lg .middle } &nbsp;__Hybrid graph + vector search__

    ---

    LanceDB / Grafeo vectors **+** graph traversal **+** BM25, fused with
    Reciprocal Rank Fusion in a single query.

-   :material-check-decagram:{ .lg .middle } &nbsp;__Two-stage verification__

    ---

    Every relation passes a topological **SR-MKG** scorer and an optional **VoG**
    groundedness check — so the graph never fills with hallucinated edges.

-   :material-sprout:{ .lg .middle } &nbsp;__Autonomous Night Gardener__

    ---

    Offline relation inference & pruning that refines the graph overnight — and
    emits **zero** relations when there is no real evidence.

-   :material-connection:{ .lg .middle } &nbsp;__MCP-native (18 tools)__

    ---

    A FastMCP server that plugs into Claude Desktop, Cursor and OpenCode over
    stdio or HTTP. Single-tenant by design.

-   :material-scale-balance:{ .lg .middle } &nbsp;__Honest & auditable__

    ---

    `hydramem stats --raw` audits every token saved. No fabricated metrics —
    if a component doesn't measurably work, the docs say so.

</div>

## Quick start in 60 seconds { .hm-section .reveal }

<div class="reveal" markdown>

=== "uv (recommended)"

    ```bash
    uv tool install git+https://github.com/xusliebana/hydramem
    hydramem init ~/my-memory
    cd ~/my-memory
    ```

=== "pipx"

    ```bash
    pipx install git+https://github.com/xusliebana/hydramem
    hydramem init ~/my-memory
    cd ~/my-memory
    ```

=== "From source"

    ```bash
    git clone https://github.com/xusliebana/hydramem && cd hydramem
    cp config.yml.example config.yml
    uv sync
    uv run hydramem --help
    ```

Then ingest your notes and ask a question — everything runs locally:

```bash
hydramem ingest ./kms --project myproject
hydramem search "what does my documentation say about the Night Gardener?"
hydramem serve --transport stdio        # expose to your MCP client
```

[Full quick start →](getting-started/){ .md-button .md-button--primary }
[All MCP tools →](mcp-tools-reference/){ .md-button }
[Integrations →](integrations/){ .md-button }

</div>

## How it works { .hm-section .reveal }

<div class="reveal" markdown>

```text
AI client (Claude Desktop / Cursor / OpenCode)
        │  MCP (stdio · http)
        ▼
HydraMem MCP server (FastMCP · 18 tools · local telemetry)
        │
   ┌────┴───────────────┬────────────────────┐
   ▼                    ▼                     ▼
Ingest             Hybrid search         Night Gardener
chunk → embed      vector + graph        infer → verify → prune
(Nomic v1.5,       + BM25 (RRF)          (offline, evidence-only)
 512-d, local)     → SR-MKG → VoG
        │                    │                    │
        └──────────┬─────────┴──────────┬─────────┘
                   ▼                     ▼
        Graph store (Grafeo)   Vector store (LanceDB / Grafeo HNSW)
```

The default stack is **Gemma 4 (`gemma4:e4b`)** for local reasoning/verification and
**Nomic Embed Text v1.5** (Matryoshka, truncated to 512-d) for embeddings — both run
locally. Swap any of them in `config.yml`.

</div>

## How does it compare? { .hm-section .reveal }

<div class="reveal" markdown>

| Project | Local-first | Graph + vector | Verifies relations | Offline learning | MCP-native | License |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **HydraMem** | ✅ | ✅ | ✅ (SR-MKG + VoG) | ✅ (Night Gardener) | ✅ | MIT |
| Mem0 | partial | optional | ❌ | partial | community | Apache-2.0 |
| Letta / MemGPT | ✅ | ❌ | ❌ | ❌ | ❌ | Apache-2.0 |
| Zep / Graphiti | partial | ✅ | partial | ✅ | community | Apache-2.0 |
| MS GraphRAG | ✅ | ✅ | indirect | ❌ | ❌ | MIT |

!!! quote "Honest positioning"
    HydraMem is **not** the first memory system, graph-RAG, or hallucination filter.
    It's an opinionated **local-first integration** of those patterns, small enough
    to read in an afternoon (~5k LOC) and with metrics you can audit.

</div>

<div class="hm-cta reveal" markdown>

### Give your agent a memory that stays yours.

[🚀&nbsp; Get started](getting-started/){ .md-button .md-button--primary }
[�&nbsp; Integrations](integrations/){ .md-button }
[�📦&nbsp; MCP tools reference](mcp-tools-reference/){ .md-button }
[★&nbsp; Star on GitHub](https://github.com/xusliebana/hydramem){ .md-button }

</div>
