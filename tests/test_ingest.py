"""Tests for the ingestion pipeline (chunker, embedder, extractor, pipeline)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestMarkdownChunker:
    def test_basic_split(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunker = MarkdownChunker()
        md = """# Title

First paragraph here.

## Section One

Content of section one.

## Section Two

Content of section two.
"""
        chunks = chunker.chunk(md)
        assert len(chunks) >= 2
        assert any("section one" in c.lower() for c in chunks)

    def test_empty_document(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunks = MarkdownChunker().chunk("")
        assert chunks == []

    def test_no_headers(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunks = MarkdownChunker().chunk("Just a single paragraph with no headers.")
        assert len(chunks) == 1

    def test_long_section_splits_by_paragraph(self):
        from hydramem.ingest.chunker import MarkdownChunker
        paragraphs = [f"Paragraph {i}: " + ("word " * 50) for i in range(20)]
        md = "## Big Section\n\n" + "\n\n".join(paragraphs)
        chunks = MarkdownChunker(max_tokens=200).chunk(md)
        assert len(chunks) > 1

    def test_no_chunk_exceeds_limit(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunker = MarkdownChunker(max_tokens=100)  # 400-char hard limit
        md = "## Big\n\n" + ("word " * 2000)  # ~10k chars, one giant paragraph
        chunks = chunker.chunk(md)
        assert len(chunks) > 1
        assert all(len(c) <= 100 * 4 for c in chunks)

    def test_consecutive_chunks_overlap(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunker = MarkdownChunker(max_tokens=100, overlap_tokens=20)
        body = " ".join(f"Sentence {i} about memory systems." for i in range(80))
        chunks = chunker.chunk("## S\n\n" + body)
        assert len(chunks) > 1
        # The head of each chunk reappears in the previous one (carried overlap).
        assert any(chunks[i + 1][:15] in chunks[i] for i in range(len(chunks) - 1))


class TestEntityExtractor:
    def test_finds_camel_case(self):
        from hydramem.ingest.extractor import EntityExtractor
        extractor = EntityExtractor()
        text = "HydraMem uses GraphRAG and LadybugDB for storage."
        entities = extractor.extract(text, "doc1", "test")
        names = [e.name for e in entities]
        assert any("HydraMem" in n or "GraphRAG" in n or "LadybugDB" in n for n in names)

    def test_finds_backtick_code(self):
        from hydramem.ingest.extractor import EntityExtractor
        entities = EntityExtractor().extract("Use `hydra_search` to find documents.", "d", "t")
        assert any(e.name == "hydra_search" for e in entities)

    def test_deduplicates(self):
        from hydramem.ingest.extractor import EntityExtractor
        entities = EntityExtractor().extract(
            "HydraMem uses HydraMem extensively. HydraMem is great.", "d", "t"
        )
        ids = [e.id for e in entities]
        assert len(ids) == len(set(ids))


class TestIngestionPipeline:
    @pytest.fixture
    def pipeline(self):
        from hydramem.ingest.pipeline import IngestionPipeline
        from hydramem.storage.factory import KnowledgeStore
        from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
        from hydramem.storage.vector.memory_repo import InMemoryVectorRepository
        store = KnowledgeStore(NetworkXGraphRepository(), InMemoryVectorRepository())
        embedder_mock = MagicMock()
        embedder_mock.embed.return_value = [0.1] * 384
        # Pipeline now batch-embeds; configure embed_batch to return one vector
        # per input text so zip() consumes the right number of chunks.
        embedder_mock.embed_batch.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
        return IngestionPipeline(store=store, embedder=embedder_mock)

    def test_ingest_file_returns_summary(self, pipeline, sample_md_file):
        result = pipeline.ingest_file(str(sample_md_file), project="test")
        assert result["chunks_added"] > 0
        assert result["entities_added"] >= 0
        assert result["project"] == "test"

    def test_ingest_file_not_found(self, pipeline):
        with pytest.raises(FileNotFoundError):
            pipeline.ingest_file("/nonexistent/path.md")

    def test_ingest_directory(self, pipeline, tmp_path):
        for i in range(3):
            (tmp_path / f"doc{i}.md").write_text(f"# Doc {i}\n\nContent of document {i}.")
        result = pipeline.ingest_directory(str(tmp_path), project="test")
        assert result["files_processed"] == 3
        assert result["chunks_added"] > 0

    def test_ingest_canonicalises_entity_variants(self, pipeline, tmp_path):
        from hydramem.ingest.registry import canonical_key
        md = tmp_path / "d.md"
        md.write_text("# Doc\n\nHydraMem is great here. Hydra Mem also works.")
        result = pipeline.ingest_file(str(md), project="t")
        ents = pipeline._store.list_entities(project="t")
        hydra = [e for e in ents if canonical_key(e["name"]) == "hydramem"]
        assert len(hydra) == 1                     # surface-form variants collapsed
        assert hydra[0]["name"] == "HydraMem"      # deterministic best display
        assert result["entities_merged"] >= 1

    def test_ingest_text_remembers_a_note(self, pipeline):
        result = pipeline.ingest_text(
            "HydraMem verifies relations with SR-MKG and VoG.",
            source="chat-note", project="t",
        )
        assert result["chunks_added"] >= 1
        assert result["source"] == "chat-note"
        assert pipeline._store.get_all_chunks()      # the note was persisted


# Shim backward-compat
class TestIngestShim:
    def test_chunk_markdown_via_shim(self):
        from hydramem.ingest.chunker import MarkdownChunker
        chunks = MarkdownChunker().chunk("# H\n\nPara.")
        assert len(chunks) >= 1

    def test_extract_entities_via_shim(self):
        from hydramem.ingest.extractor import EntityExtractor
        entities = EntityExtractor().extract("LanceDB stores vectors.", "d", "t")
        assert isinstance(entities, list)


class TestGlinerExtractor:
    def test_factory_returns_gliner_backend(self):
        from hydramem.ingest.extractor import GlinerExtractor, create_extractor
        ext = create_extractor("gliner")
        assert isinstance(ext, GlinerExtractor)

    def test_falls_back_to_heuristic_when_unavailable(self):
        # `gliner` is not installed in the test env, so extract() must degrade
        # to the heuristic backend rather than crash (local-first contract).
        from hydramem.ingest.extractor import EntityExtractor, GlinerExtractor
        ext = GlinerExtractor()
        text = "Call `hydra_search` then `KnowledgeStore`."
        ents = ext.extract(text, "d", "p")
        assert isinstance(ents, list)
        assert ext._degraded is True
        # Degraded output must match the heuristic backend exactly (delegation).
        heuristic = [e.name for e in EntityExtractor().extract(text, "d", "p")]
        assert [e.name for e in ents] == heuristic
        assert heuristic  # the chosen sentence yields at least one entity

    def test_maps_spans_to_canonical_entities(self):
        from hydramem.ingest.extractor import GlinerExtractor
        from hydramem.ingest.registry import entity_id

        class _FakeModel:
            def predict_entities(self, text, labels, threshold=0.5):
                return [
                    {"text": "HydraMem", "label": "product", "score": 0.9},
                    {"text": "hydramem", "label": "product", "score": 0.8},
                    {"text": "Guido van Rossum", "label": "person", "score": 0.95},
                    {"text": "", "label": "noise", "score": 0.1},
                ]

        ext = GlinerExtractor()
        ext._model = _FakeModel()  # inject → bypass the lazy import/load
        ents = ext.extract("irrelevant", "d", "proj")

        names = {e.name for e in ents}
        assert "Guido van Rossum" in names
        # Canonical ids collapse "HydraMem"/"hydramem" into one; empty span dropped.
        ids = [e.id for e in ents]
        assert len(ids) == len(set(ids))
        assert entity_id("proj", "HydraMem") in ids
        assert len(ents) == 2

    def test_config_drives_backend_selection(self):
        from hydramem.core.config import load_config
        from hydramem.ingest.extractor import GlinerExtractor
        from hydramem.ingest.pipeline import IngestionPipeline

        cfg = load_config({"extraction": {"backend": "gliner"}})
        pipeline = IngestionPipeline(
            store=MagicMock(), embedder=MagicMock(), config=cfg
        )
        assert isinstance(pipeline._extractor, GlinerExtractor)
