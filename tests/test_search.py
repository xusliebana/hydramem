"""Tests for SearchService."""

from __future__ import annotations

from unittest.mock import MagicMock

from hydramem.core.types import Chunk


def _make_chunks(n, project="test"):
    return [
        Chunk(
            id=f"c{i}",
            text=f"Chunk {i} about HydraMem.",
            source=f"doc{i}.md",
            similarity=0.9 - i * 0.05,
            project=project,
        )
        for i in range(n)
    ]


def _make_service(mock_store, embed_val=None):
    from hydramem.search import SearchService

    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = embed_val or [0.1] * 384
    mock_pipeline = MagicMock()
    mock_pipeline.verify_chunks.return_value = {
        "filtered": [],
        "verified": [],
        "rejected_vector": [],
        "rejected_srmkg": [],
        "rejected_vog": [],
        "vog_scores": [],
    }
    mock_pipeline.reset_vog_cap.return_value = None
    return SearchService(store=mock_store, embedder=mock_embedder, pipeline=mock_pipeline)


class TestPrimingContext:
    def test_returns_structure(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(3)
        svc = _make_service(mock_store)
        result = svc.priming_context("What is HydraMem?", project="test", k=3)
        assert "chunks" in result
        assert "context" in result
        assert "entities" in result

    def test_returns_empty_on_embed_failure(self, mock_store):
        from hydramem.search import SearchService

        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = RuntimeError("no model")
        svc = SearchService(store=mock_store, embedder=mock_embedder)
        result = svc.priming_context("query", project="test")
        assert result["chunks"] == []
        assert result["context"] == ""


class TestHydraSearch:
    def test_full_pipeline(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(5)
        mock_store.list_entities.return_value = [{"id": "e1", "name": "HydraMem"}]
        mock_store.get_chunks_near_entity.return_value = _make_chunks(2)

        from hydramem.search import SearchService

        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384
        svc = SearchService(store=mock_store, embedder=mock_embedder)
        result = svc.hydra_search("How does HydraMem work?", project="test")

        assert "chunks" in result
        assert "verified" in result
        assert "final_context" in result
        assert isinstance(result["avg_vog_score"], float)

    def test_handles_no_results(self, mock_store):
        mock_store.vector_search.return_value = []
        mock_store.list_entities.return_value = []
        svc = _make_service(mock_store)
        result = svc.hydra_search("unknown query", project="test")
        assert isinstance(result["verified"], list)


class TestBM25Hybrid:
    def test_bm25_recalls_lexical_match_missed_by_vectors(self):
        from hydramem.search import SearchService

        corpus = [
            Chunk(
                id="k1",
                text="The Night Gardener prunes spurious edges.",
                source="a.md",
                project="test",
            ),
            Chunk(id="k2", text="LanceDB stores vector embeddings.", source="b.md", project="test"),
            Chunk(
                id="k3", text="Grafeo is the default graph backend.", source="c.md", project="test"
            ),
        ]
        store = MagicMock()
        store.get_all_chunks.return_value = corpus
        store.vector_search.return_value = []  # dense arm misses it
        store.list_entities.return_value = []
        store.get_chunks_near_entity.return_value = []
        store.get_entity_neighbors.return_value = []
        embedder = MagicMock()
        embedder.embed.return_value = [0.0] * 384
        pipeline = MagicMock()
        pipeline.reset_vog_cap.return_value = None
        pipeline.verify_chunks.return_value = {
            "filtered": [],
            "verified": [],
            "rejected_vector": [],
            "rejected_srmkg": [],
            "rejected_vog": [],
            "vog_scores": [],
        }
        svc = SearchService(store=store, embedder=embedder, pipeline=pipeline)

        result = svc.hydra_search("Grafeo backend", project="test")
        ids = [c["id"] for c in result["chunks"]]
        assert "k3" in ids  # recalled by the BM25 arm
        assert result["bm25"]["enabled"] is True
        assert result["bm25"]["candidates"] >= 1

    def test_bm25_no_op_on_empty_corpus(self, mock_store):
        svc = _make_service(mock_store)  # get_all_chunks() == []
        result = svc.hydra_search("anything", project="test")
        assert result["bm25"]["candidates"] == 0


class TestTracePath:
    def test_no_path(self, mock_store):
        mock_store.list_entities.return_value = []
        svc = _make_service(mock_store)
        result = svc.trace_path("A", "B", project="test")
        assert result["found"] is False


class TestHydraSearchTraversal:
    def test_ppr_mode_runs_and_emits_meta(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(2)
        mock_store.list_entities.return_value = [
            {"id": "e1", "name": "HydraMem"},
            {"id": "e2", "name": "LanceDB"},
        ]
        mock_store.get_entity_neighbors.return_value = [{"id": "e2", "confidence": 1.0}]
        mock_store.get_chunks_near_entity.return_value = _make_chunks(1)

        svc = _make_service(mock_store)
        result = svc.hydra_search("HydraMem", project="test", traversal="ppr")
        assert result["traversal"] == "ppr"
        assert result["ppr"] is not None
        assert result["ppr"]["n_seeds"] >= 1

    def test_hybrid_mode_falls_back_when_no_seeds(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(2)
        mock_store.list_entities.return_value = []
        svc = _make_service(mock_store)
        result = svc.hydra_search("lowercase nothing", project="test", traversal="hybrid")
        # No seeds → no PPR call, but the search should still complete.
        assert result["traversal"] == "hybrid"


# ---------------------------------------------------------------------------
# Typed retrieval planner
# ---------------------------------------------------------------------------


class TestZeroShotPlanner:
    def _planner(self, qvec, threshold=0.1):
        from hydramem.planner import ZeroShotPlanner

        class _E:
            def embed(self, text, *, is_query: bool = False):
                return list(qvec)

        planner = ZeroShotPlanner(_E(), threshold=threshold)
        # Inject orthonormal prototypes so class selection is deterministic.
        planner._proto = {
            "factoid": [1.0, 0.0, 0.0, 0.0],
            "multi_hop": [0.0, 1.0, 0.0, 0.0],
            "temporal": [0.0, 0.0, 1.0, 0.0],
            "comparative": [0.0, 0.0, 0.0, 1.0],
        }
        return planner

    def test_factoid_maps_to_cheap_bfs_skip_vog(self):
        from hydramem.planner import RetrievalStrategy

        strat = self._planner([1.0, 0.0, 0.0, 0.0]).plan("q", default_top_k=7)
        assert isinstance(strat, RetrievalStrategy)
        assert strat.name == "factoid"
        assert strat.traversal == "bfs"
        assert strat.skip_vog is True
        assert strat.top_k == 7
        assert strat.confidence > 0.9

    def test_multi_hop_maps_to_hybrid(self):
        strat = self._planner([0.0, 1.0, 0.0, 0.0]).plan("q")
        assert strat.name == "multi_hop"
        assert strat.traversal == "hybrid"
        assert strat.skip_vog is False

    def test_comparative_maps_to_ppr(self):
        strat = self._planner([0.0, 0.0, 0.0, 1.0]).plan("q")
        assert strat.name == "comparative"
        assert strat.traversal == "ppr"

    def test_low_confidence_falls_through(self):
        # Uniform query → cosine ≈ 0.5 to any basis prototype; high threshold
        # makes the planner abstain rather than guess (honesty contract).
        planner = self._planner([0.1, 0.1, 0.1, 0.1], threshold=0.95)
        assert planner.plan("ambiguous") is None

    def test_embedder_failure_returns_none(self):
        from hydramem.planner import ZeroShotPlanner

        class _Broken:
            def embed(self, text, *, is_query: bool = False):
                raise RuntimeError("no embedder")

        assert ZeroShotPlanner(_Broken()).plan("q") is None


class TestPlannerIntegration:
    def _svc(self, mock_store, *, enabled, threshold=0.0):
        from hydramem.core.config import load_config
        from hydramem.search import SearchService

        cfg = load_config({"search": {"planner": {"enabled": enabled, "threshold": threshold}}})
        embedder = MagicMock()
        embedder.embed.return_value = [0.1] * 8
        pipeline = MagicMock()
        pipeline.verify_chunks.return_value = {
            "filtered": [],
            "verified": [],
            "rejected_vector": [],
            "rejected_srmkg": [],
            "rejected_vog": [],
            "vog_scores": [],
        }
        pipeline.reset_vog_cap.return_value = None
        return SearchService(
            store=mock_store, embedder=embedder, pipeline=pipeline, config=cfg
        ), pipeline

    def test_planner_dispatches_when_enabled(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(2)
        mock_store.list_entities.return_value = []
        svc, pipeline = self._svc(mock_store, enabled=True)
        result = svc.hydra_search("what is HydraMem?", project="test")
        # Constant embeddings → all prototypes equal → first class (factoid).
        assert result["planner"]["strategy"] == "factoid"
        assert result["traversal"] == "bfs"
        pipeline.verify_chunks.assert_not_called()  # factoid skips VoG

    def test_planner_off_by_default(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(1)
        mock_store.list_entities.return_value = []
        svc = _make_service(mock_store)
        result = svc.hydra_search("what is HydraMem?", project="test")
        assert result["planner"] is None

    def test_strategy_override_bypasses_planner(self, mock_store):
        mock_store.vector_search.return_value = _make_chunks(1)
        mock_store.list_entities.return_value = []
        svc, _ = self._svc(mock_store, enabled=True)
        result = svc.hydra_search("q", project="test", strategy_override="ppr")
        assert result["traversal"] == "ppr"
        assert result["planner"] is None  # planner not run under explicit override
