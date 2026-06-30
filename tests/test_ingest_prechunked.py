"""Tests for agent-driven ingestion: ingest_prechunked + submit_session_extraction.

These tests stub out the verifier so they remain LLM-free.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hydramem.ingest.pipeline import IngestionPipeline
from hydramem.storage.factory import KnowledgeStore
from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
from hydramem.storage.vector.memory_repo import InMemoryVectorRepository
from hydramem.verification.base import VerificationResult


def _accept_all_verifier() -> MagicMock:
    v = MagicMock()
    v.verify.side_effect = lambda rel: VerificationResult(
        accepted=True, score=0.9, level="srmkg_high"
    )
    return v


def _reject_all_verifier() -> MagicMock:
    v = MagicMock()
    v.verify.side_effect = lambda rel: VerificationResult(
        accepted=False, score=0.1, level="srmkg_low"
    )
    return v


@pytest.fixture
def pipeline_accept():
    store = KnowledgeStore(NetworkXGraphRepository(), InMemoryVectorRepository())
    embedder = MagicMock()
    embedder.embed_batch.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
    return IngestionPipeline(
        store=store, embedder=embedder, verifier=_accept_all_verifier()
    )


@pytest.fixture
def pipeline_reject():
    store = KnowledgeStore(NetworkXGraphRepository(), InMemoryVectorRepository())
    embedder = MagicMock()
    embedder.embed_batch.side_effect = lambda texts: [[0.1] * 384 for _ in texts]
    return IngestionPipeline(
        store=store, embedder=embedder, verifier=_reject_all_verifier()
    )


class TestIngestPrechunked:
    def test_basic_payload(self, pipeline_accept):
        payload = [
            {
                "text": "HydraMem uses LanceDB for vectors.",
                "entities": [
                    {"name": "HydraMem", "type": "tool"},
                    {"name": "LanceDB", "type": "tool"},
                ],
                "relations": [
                    {"from": "HydraMem", "to": "LanceDB",
                     "type": "USES", "confidence": 0.9},
                ],
            },
            {
                "text": "HydraMem also persists a graph.",
                "entities": [{"name": "HydraMem", "type": "tool"}],
            },
        ]
        result = pipeline_accept.ingest_prechunked(
            source="doc.md", chunks=payload, project="t",
        )
        assert result["chunks_added"] == 2
        assert result["entities_added"] >= 2
        assert result["relations_proposed"] == 1
        assert result["relations_accepted"] == 1
        assert result["relations_rejected"] == 0
        assert result["truncated_chunks"] == 0

    def test_relation_with_unknown_endpoint_is_rejected(self, pipeline_accept):
        payload = [{
            "text": "X happens.",
            "entities": [{"name": "X", "type": "concept"}],
            "relations": [
                {"from": "X", "to": "Y_NOT_DECLARED",
                 "type": "REL", "confidence": 0.9},
            ],
        }]
        result = pipeline_accept.ingest_prechunked(
            source="doc.md", chunks=payload, project="t",
        )
        assert result["relations_proposed"] == 1
        assert result["relations_accepted"] == 0
        assert result["relations_rejected"] == 1

    def test_verifier_rejects_hallucinated_relation(self, pipeline_reject):
        payload = [{
            "text": "A connects to B.",
            "entities": [
                {"name": "A", "type": "concept"},
                {"name": "B", "type": "concept"},
            ],
            "relations": [
                {"from": "A", "to": "B", "type": "REL", "confidence": 0.5},
            ],
        }]
        result = pipeline_reject.ingest_prechunked(
            source="doc.md", chunks=payload, project="t",
        )
        assert result["relations_accepted"] == 0
        assert result["relations_rejected"] == 1

    def test_chunk_limit_truncates(self, pipeline_accept):
        # Force a tiny limit on the pipeline.
        pipeline_accept._max_chunks = 3
        payload = [
            {"text": f"chunk {i}", "entities": [{"name": f"E{i}", "type": "x"}]}
            for i in range(10)
        ]
        result = pipeline_accept.ingest_prechunked(
            source="big.md", chunks=payload, project="t",
        )
        assert result["chunks_added"] == 3
        assert result["truncated_chunks"] == 7

    def test_empty_chunks_list(self, pipeline_accept):
        result = pipeline_accept.ingest_prechunked(
            source="empty.md", chunks=[], project="t",
        )
        assert result["chunks_added"] == 0
        assert result["entities_added"] == 0

    def test_invalid_payload_raises(self, pipeline_accept):
        with pytest.raises(TypeError):
            pipeline_accept.ingest_prechunked(
                source="x", chunks="not a list", project="t",  # type: ignore[arg-type]
            )


class TestSubmitSessionExtraction:
    def test_basic_session_dump(self, pipeline_accept):
        result = pipeline_accept.submit_session_extraction(
            session_id="s1",
            project="t",
            entities=[
                {"name": "Alpha", "type": "concept"},
                {"name": "Beta", "type": "concept"},
            ],
            relations=[
                {"from": "Alpha", "to": "Beta",
                 "type": "REL", "confidence": 0.8},
            ],
        )
        assert result["entities_added"] == 2
        assert result["relations_proposed"] == 1
        assert result["relations_accepted"] == 1

    def test_unknown_endpoint_rejected(self, pipeline_accept):
        result = pipeline_accept.submit_session_extraction(
            session_id="s1",
            project="t",
            entities=[{"name": "Alpha", "type": "concept"}],
            relations=[
                {"from": "Alpha", "to": "Missing",
                 "type": "REL", "confidence": 0.8},
            ],
        )
        assert result["relations_accepted"] == 0
        assert result["relations_rejected"] == 1

    def test_invalid_payload_raises(self, pipeline_accept):
        with pytest.raises(TypeError):
            pipeline_accept.submit_session_extraction(
                session_id="s",
                project="t",
                entities="bad",  # type: ignore[arg-type]
                relations=[],
            )
