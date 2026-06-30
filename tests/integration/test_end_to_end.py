"""End-to-end integration test: ingest → search → gardener → prune.

Exercises the full HydraMem pipeline using only in-process backends
(NetworkX graph + in-memory vector store + deterministic stub embedder),
so it runs in <1 s on CI without any model download.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hydramem.core.config import Config
from hydramem.core.types import Entity
from hydramem.garden.gardener import NightGardener
from hydramem.garden.inferrer import RelationInferrer
from hydramem.garden.pruner import KnowledgePruner
from hydramem.garden.repository import SessionRepository, StatusRepository
from hydramem.ingest.chunker import MarkdownChunker
from hydramem.ingest.embedder import EmbeddingService
from hydramem.ingest.extractor import EntityExtractor
from hydramem.ingest.pipeline import IngestionPipeline
from hydramem.search import SearchService
from hydramem.storage.factory import KnowledgeStore
from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
from hydramem.storage.vector.memory_repo import InMemoryVectorRepository
from hydramem.verification.pipeline import VerificationPipeline


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")
    monkeypatch.setenv("HYDRAMEM_GNN_MAX_NODES", "1000")
    return Config({})


@pytest.fixture
def store():
    return KnowledgeStore(NetworkXGraphRepository(), InMemoryVectorRepository())


@pytest.fixture
def session_repo(tmp_path):
    return SessionRepository(path=tmp_path / "sessions.json")


@pytest.fixture
def status_repo(tmp_path):
    return StatusRepository(path=tmp_path / "garden_status.json")


def _write_corpus(root):
    (root / "alpha.md").write_text(
        "# HydraMem\n\nHydraMem connects entities through verified evidence.\n\n"
        "## Verification\n\nThe SR-MKG scorer rejects spurious relations.\n"
    )
    (root / "beta.md").write_text(
        "# Night Gardener\n\nThe Night Gardener autonomously refines the graph.\n"
    )


def test_ingest_search_gardener_prune_e2e(tmp_path, cfg, store, session_repo, status_repo):
    # ── Arrange: write a tiny corpus ─────────────────────────────────────────
    _write_corpus(tmp_path)
    embedder = EmbeddingService()  # uses HYDRAMEM_EMBEDDER=stub
    pipeline = IngestionPipeline(
        store=store,
        chunker=MarkdownChunker(),
        embedder=embedder,
        extractor=EntityExtractor(),
        config=cfg,
    )

    # ── Act 1: ingest both files ─────────────────────────────────────────────
    res = pipeline.ingest_directory(str(tmp_path), project="e2e")
    assert res["files_processed"] == 2
    assert res["chunks_added"] >= 2

    # ── Act 2: priming + hydra search return non-empty results ───────────────
    search = SearchService(store=store, embedder=embedder, config=cfg)
    priming = search.priming_context("HydraMem verification", project="e2e", k=3)
    assert priming["chunks"]

    hydra = search.hydra_search("Night Gardener", project="e2e", top_k=5)
    assert hydra["chunks_total"] >= 1
    assert "rejected_vector" in hydra
    assert "rejected_vog" in hydra

    # ── Act 3: add an isolated entity and run the gardener prune phase ──────
    # The in-memory NetworkX backend cannot track MENTIONS edges, so EVERY
    # entity will look orphaned to the pruner. We assert that the *bug fix*
    # works: deletion is real (count > 0, all gone afterwards), not just
    # counted. The persistent Ladybug backend tracks mentions and won't
    # over-prune.
    store.add_entity(Entity(id="orphan", name="Orphan", project="e2e"))
    pruner = KnowledgePruner(store)
    prune_res = pruner.prune(project="e2e")
    assert prune_res["pruned_entities"] >= 1
    assert prune_res["skipped_entities"] == 0
    names = [e["name"] for e in store.list_entities(project="e2e")]
    assert "Orphan" not in names

    # ── Act 4: gardener cycle with mocked LLM produces verifiable output ────
    fake_llm = MagicMock()
    # Honest LLM response that the inferrer can parse.
    fake_llm.complete.return_value = "HydraMem –[verifies]→ Night Gardener | CONFIDENCE: 0.9\n"
    inferrer = RelationInferrer(fake_llm)

    # Pre-seed a session so the inferrer has text to work with.
    session_repo.save(
        {
            "session_id": "s1",
            "project": "e2e",
            "entry": {
                "ts": "2026-05-07T10:00:00+00:00",
                "tool_name": "hydra_search",
                "summary": "Query: how does the Night Gardener relate to HydraMem? "
                "Grounded context: HydraMem verifies relations via SR-MKG.",
            },
        }
    )
    # Save a duplicate to exceed min_repeat_count=2.
    session_repo.save(
        {
            "session_id": "s1",
            "project": "e2e",
            "entry": {
                "ts": "2026-05-07T11:00:00+00:00",
                "tool_name": "hydra_search",
                "summary": "Query: how does the Night Gardener relate to HydraMem? "
                "Grounded context: HydraMem verifies relations via SR-MKG.",
            },
        }
    )

    gardener = NightGardener(
        store=store,
        session_repo=session_repo,
        status_repo=status_repo,
        inferrer=inferrer,
        pipeline=VerificationPipeline(cfg),
        pruner=pruner,
        config=cfg,
    )
    summary = gardener.run(project="e2e")
    assert "candidates_proposed" in summary
    # No exceptions, status saved correctly.
    status = status_repo.load()
    assert status["total_runs"] >= 1
    assert status["is_running"] is False


def test_search_cache_invalidation(cfg, store):
    embedder = EmbeddingService()
    search = SearchService(store=store, embedder=embedder, config=cfg)

    store.add_entity(Entity(id="e1", name="HydraMem", project="cache"))
    res1 = search.priming_context("HydraMem", project="cache", k=1)
    assert res1 is not None

    # Add a new entity; without invalidation the cached index would miss it.
    store.add_entity(Entity(id="e2", name="Gardener", project="cache"))
    search.invalidate_cache("cache")
    entities, index = search._entities_with_index("cache")
    names = {e["name"] for e in entities}
    assert {"HydraMem", "Gardener"} <= names


def test_relation_inferrer_no_synthetic_fallback():
    """Honesty regression: without sessions, infer() must return [] (no random rels)."""
    fake_llm = MagicMock()
    fake_llm.complete.return_value = ""
    inferrer = RelationInferrer(fake_llm)
    out = inferrer.infer(sessions=[], entity_names=["A", "B", "C"], project="x")
    assert out == []
