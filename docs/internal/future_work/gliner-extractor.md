# GLiNER Extractor Backend 🟢

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Immediate win

## Why it matters

The current entity extractor is regex/heuristic. Recall on long-tail
entities (people, products, jargon) is poor and entirely English-biased.
**GLiNER** is a small zero-shot NER model (~80 MB ONNX) that accepts
**entity types defined at runtime** — perfect for a system whose ontology
evolves with the corpus. This is the single highest-recall improvement
HydraMem can make without architectural change.

## State of the art

- **GLiNER** (Zaratiana et al., 2023) — encoder-based zero-shot NER, types
  passed as natural-language strings at inference time
- **GLiNER-multi** — multilingual variant
- **UniversalNER** (Zhou et al., 2023) — distillation of GPT-4 NER into
  small dense models
- **NuNER** (Bogdanov et al., 2024) — open-data competitor
- **SpanMarker** — span-level encoder, comparable accuracy

GLiNER currently has the best speed/quality/flexibility trade-off for
local-first deployments.

## Proposed architecture

HydraMem already has a pluggable extractor protocol
([`hydramem/ingest/extractor.py`](../../../hydramem/ingest/extractor.py)). Add a
new backend that registers in the existing factory.

```
hydramem/ingest/extractors/
├── regex_extractor.py      # current
├── gliner_extractor.py     # new
└── llm_extractor.py        # current
```

Configuration:

```yaml
extraction:
  backend: gliner            # regex | gliner | llm
  gliner:
    model: "urchade/gliner_multi-v2.1"
    types:
      - person
      - organisation
      - location
      - software_component
      - concept
      - file_path
    threshold: 0.5
    batch_size: 8
```

The `types` list bootstraps the ontology. Future ontology induction
(see 1.x) will populate this automatically.

## Risks

- **Install size.** ONNX runtime + tokenizer + model ≈ 200 MB. Gate behind
  `[gliner]` extra in `pyproject.toml`.
- **Latency on very large chunks** — mitigate by chunking at 512 tokens
  and batching.
- **Type-list drift** between projects. Persist the active type list as
  part of the project metadata so retrieval can rely on it.

## Computational cost

- Cold load: ~2 s
- Inference: ~30–80 ms per 512-token chunk on a modern CPU
- RAM: ~600 MB while loaded

## Privacy implications

None. Pure local inference.

## Local-first viability

Excellent.

## Suggested implementation strategy

1. Add `[gliner]` extra: `gliner`, `onnxruntime` (or torch).
2. Implement `GlinerExtractor(Extractor)` that returns `Entity` objects.
3. Register in
   [`hydramem/ingest/extractor.py`](../../../hydramem/ingest/extractor.py) factory
   keyed by `extraction.backend`.
4. Persist `extraction.gliner.types` in the project config.
5. Side-by-side test on dogfood corpus: regex vs GLiNER, log entities/sec
   and unique-entity-recall delta.
6. Document trade-off in `docs/configuration.md`.

## Concrete code changes

| File | Change |
|------|--------|
| `hydramem/ingest/extractors/gliner_extractor.py` | **NEW** — `GlinerExtractor` class |
| [`hydramem/ingest/extractor.py`](../../../hydramem/ingest/extractor.py) | Register backend in factory |
| [`hydramem/core/config.py`](../../../hydramem/core/config.py) | `ExtractionConfig.gliner` substruct |
| [`config.yml.example`](../../../config.yml.example) | Document `extraction.backend: gliner` |
| [`pyproject.toml`](../../../pyproject.toml) | New `[gliner]` extra |
| [`tests/test_ingest.py`](../../../tests/test_ingest.py) | Stubbed backend test |
| [`docs/configuration.md`](../../configuration.md) | New extractor table |

## References

- Zaratiana et al., *GLiNER: Generalist Model for Named Entity Recognition
  using Bidirectional Transformer*, 2023 — arXiv:2311.08526
- Zhou et al., *UniversalNER: Targeted Distillation*, 2023
- Bogdanov et al., *NuNER*, 2024
