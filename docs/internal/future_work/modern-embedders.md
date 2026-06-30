# Modern Embedder Backends (bge / gte / jina) 🟢

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Immediate win

## Why it matters

The default embedder is `nomic-ai/nomic-embed-text-v1.5` (Matryoshka, 512-d). Other modern small
ONNX-deployable encoders such as `bge-small-en-v1.5`, `gte-small`, or
`jina-embeddings-v3` consistently outperform MiniLM by **3–8 nDCG points**
on MTEB retrieval benchmarks at comparable size. They are drop-in
replacements that improve every downstream stage (vector prefilter,
chunk-level VoG candidates, graph priming) for zero architectural cost.

## State of the art

- **BGE** (BAAI General Embedding) — `bge-small-en-v1.5` (133M),
  `bge-m3` (multilingual + multi-functional)
- **GTE** (Alibaba) — `gte-small`, `gte-base-en-v1.5`
- **Jina v3** — task-specific LoRA adapters, multilingual
- **Nomic Embed v1.5** — long-context (8 k tokens), Matryoshka representation
- **MTEB leaderboard** — public benchmark for embedding quality

All of the above ship ONNX weights and run on CPU in < 50 ms per chunk
of 256 tokens.

## Proposed architecture

HydraMem already auto-detects `fastembed` before falling back to
`sentence-transformers`. Extend the existing factory with a
**model-name-aware backend** rather than a new abstraction.

```
hydramem/ingest/embedder.py
└── Embedder
    ├── _backend: "fastembed" | "sentence-transformers" | "onnx-runtime"
    └── _model_name from config.embedding.model
```

Add a `config.embedding` section:

```yaml
embedding:
  model: "BAAI/bge-small-en-v1.5"   # default upgraded
  backend: auto                      # auto | fastembed | st | onnx
  dimension: 384                     # validated against the model card
  matryoshka_dim: null               # optional truncation for Nomic-style
```

LanceDB schema needs to handle dimension changes — provide a
`hydramem reindex --embedder bge-small` command that re-embeds the
existing chunk corpus into a new lance dataset and atomically swaps it.

## Risks

- **Dimension mismatch with existing LanceDB index.** Mitigate with the
  reindex command and a startup sanity check (already partially in
  `hydramem/storage/vector/lancedb_repo.py`).
- **Model licence drift.** Pin a known-permissive default (BGE is MIT,
  GTE is Apache-2.0).
- **Tokenizer behaviour differences** can shift chunking — the chunker
  is character-based today, so this is low risk in practice.

## Computational cost

- Disk: 80–500 MB depending on model
- RAM: < 1 GB
- CPU latency: 20–80 ms per chunk of 256 tokens
- Reindex of a 50 k-chunk corpus: ~10–20 minutes on a modern CPU

## Privacy implications

None. Models are downloaded once and run locally.

## Local-first viability

Excellent. All listed models ship ONNX or have clean GGUF/ONNX exports.

## Suggested implementation strategy

1. Add `embedding:` section to `config.yml.example`.
2. Extend `Embedder` to honour `model` + `backend` knobs.
3. Add `hydramem reindex` CLI command (reuses `IngestionService`).
4. Document migration path in `docs/configuration.md`.
5. Run `scripts/benchmark.py` with each candidate, record nDCG@10
   against the dogfood corpus.
6. Promote the winner to default in `config.yml.example`.

## Concrete code changes

| File | Change |
|------|--------|
| [`hydramem/ingest/embedder.py`](../../../hydramem/ingest/embedder.py) | Honour `model` / `backend`; add ONNX runtime backend |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | New `EmbeddingConfig` section |
| [`hydramem/cli.py`](../../../hydramem/cli.py) | New `reindex` subcommand |
| [`hydramem/storage/vector/lancedb_repo.py`](../../../hydramem/storage/vector/lancedb_repo.py) | Atomic swap of dataset on reindex |
| [`config.yml.example`](../../../config.yml.example) | New section, default to `BAAI/bge-small-en-v1.5` |
| [`scripts/benchmark.py`](../../../scripts/benchmark.py) | Embedder comparison harness |
| [`pyproject.toml`](../../../pyproject.toml) | Add `[bge]` / `[onnx]` extras |
| [`tests/test_ingest.py`](../../../tests/test_ingest.py) | Backend selection + dimension mismatch tests |

## References

- Xiao et al., *C-Pack: Packed Resources For General Chinese Embeddings*, 2023 (BGE)
- Li et al., *Towards General Text Embeddings with Multi-stage Contrastive Learning*, 2023 (GTE)
- Jina AI, *jina-embeddings-v3*, 2024
- Nussbaum et al., *Nomic Embed*, 2024
- Muennighoff et al., *MTEB: Massive Text Embedding Benchmark*, EACL 2023
