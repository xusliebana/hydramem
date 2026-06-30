# Local LoRA Fine-Tuning of the Embedder �

> **Roadmap slot:** Research branch — no shipping commitment (👍 vote to prioritize)
> **Owner:** unassigned
> **Status:** Research branch — domain adaptation without leaving the machine

## Why it matters

Generic encoders (MiniLM, BGE, GTE) are trained on web text. Each
HydraMem deployment indexes a *specific* corpus (engineering wiki, code,
research notes). A short LoRA adaptation on the deployment's own
verified relations can lift retrieval accuracy meaningfully (typical
+5–10 nDCG points in domain) at the cost of one CPU/GPU session.

Crucially, the training signal is **already on disk**: SR-MKG-accepted
+ VoG-grounded relations are reliable positives, and head/tail
corruptions provide negatives. No human labelling. No data leaves the
machine.

## State of the art

- **LoRA** (Hu et al., 2021) — low-rank adapters
- **SimCSE / E5** (Gao et al., 2021; Wang et al., 2022) — contrastive
  fine-tuning recipe for sentence encoders
- **GISTEmbed / NV-Retriever** — modern data-efficient recipes
- **MTEB-finetuning** patterns — community recipes for tiny datasets

## Proposed architecture

### Data construction (offline, in Night Gardener or on demand)

```
Positives:
  for each accepted relation r = (h, r_type, t):
     (text_chunk_for_h, text_chunk_for_t)  → label 1
Negatives:
  for each positive: sample random unrelated entity → label 0
  filter out any pair that is itself a positive
```

Cap per-run training budget (e.g., 50 k pairs).

### Training

- Backbone: frozen embedder (e.g., `bge-small`)
- Adapter: LoRA `r=16, alpha=32` on attention `q_proj`, `v_proj`
- Loss: cosine InfoNCE with in-batch negatives
- Optimiser: AdamW, 2–5 epochs
- Hardware: CPU acceptable for `r=16` on small base; GPU recommended

### Persistence

```
~/.hydramem/projects/<p>/embedder_lora/
  ├── adapter_config.json
  ├── adapter_model.safetensors
  └── metadata.json   # base model, hash, training date, val cos-sim
```

### Loading

`Embedder` checks for an active adapter and merges it at load. Falls
back to base model if disabled or missing. CLI command
`hydramem finetune-embedder --project X` triggers training.

### Versioning

Treat the adapter as part of the index version. A new adapter triggers
a reindex of LanceDB (atomic swap) so vector space stays consistent.

## Risks

- **Catastrophic forgetting of general retrieval ability.** Mitigate
  with low LoRA rank and short training.
- **Data leakage** — positives must not appear in any held-out test
  pair.
- **Index inconsistency** if adapter changes mid-flight. Always reindex
  alongside adapter swap.
- **Adapter file integrity** — sign with HMAC like federated exports.

## Computational cost

- 50 k pairs, `bge-small`, LoRA r=16:
  - CPU: 30–90 minutes
  - GPU (consumer 8 GB): 3–10 minutes
- Storage: < 5 MB per adapter
- Reindex time follows the embedder reindex pathway

## Privacy implications

None new — training data is already local. Adapter encodes
deployment-specific patterns, so it should not be exported in federated
shares unless the user opts in.

## Local-first viability

Good. Requires `[lora]` extra (`peft`, `transformers`, `torch`). Falls
back transparently to base model when not installed.

## Suggested implementation strategy

1. Add `hydramem/ingest/finetune.py` with `LoRATrainer`.
2. Build a `PairsBuilder` that emits positives/negatives from the store.
3. Persist adapter under the project directory.
4. Extend `Embedder` to merge adapter on load.
5. Coordinate with the reindex workflow from
   [modern-embedders.md](modern-embedders.md) — same atomic swap path.
6. CLI: `hydramem finetune-embedder` + `hydramem embedder-status`.
7. Telemetry: log val cosine-similarity uplift.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/ingest/finetune.py` | **NEW** — LoRA training loop |
| `hydramem/ingest/pairs.py` | **NEW** — positive/negative pair builder |
| [`hydramem/ingest/embedder.py`](../../../hydramem/ingest/embedder.py) | Adapter-aware load |
| [`hydramem/cli.py`](../../../hydramem/cli.py) | `finetune-embedder`, `embedder-status` |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `embedding.lora` block |
| [`pyproject.toml`](../../../pyproject.toml) | New `[lora]` extra |
| `tests/test_finetune.py` | **NEW** — smoke + adapter round-trip |

## References

- Hu et al., *LoRA: Low-Rank Adaptation of Large Language Models*, ICLR 2022
- Gao et al., *SimCSE: Simple Contrastive Learning of Sentence Embeddings*,
  EMNLP 2021
- Wang et al., *Text Embeddings by Weakly-Supervised Contrastive
  Pre-training* (E5), 2022
- Reimers & Gurevych, *Sentence-BERT*, EMNLP 2019
