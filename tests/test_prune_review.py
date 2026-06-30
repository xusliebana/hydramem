"""Tests for the human-in-the-loop prune review + learned-pruner loop."""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock

import pytest

from hydramem.garden.review import PRUNE_FEATURES, PruneReviewStore


def _store(tmp_path):
    return PruneReviewStore(db_path=tmp_path / "reviews.db")


def _small_graph_store():
    """A tiny KnowledgeStore with a handful of edges of varying spuriousness."""
    from hydramem.core.types import Entity, Relation
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    store = KnowledgeStore(
        graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository()
    )
    for n in "abcde":
        store.add_entity(Entity(id=n, name=n.upper(), project="p"))
    for u, v in [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("a", "c"), ("b", "d")]:
        store.add_relation(
            Relation(from_entity=u, to_entity=v, relation_type="rel", confidence=0.5)
        )
    return store


class TestPruneReviewStore:
    def test_add_dedup_and_stats(self, tmp_path):
        s = _store(tmp_path)
        feats = {"heuristic": 0.7, "jaccard": 0.1}
        assert s.add_candidate(project="p", from_id="a", to_id="b",
                               spuriousness=0.7, features=feats) is True
        # De-duplicated on (project, from, to).
        assert s.add_candidate(project="p", from_id="a", to_id="b",
                               spuriousness=0.7, features=feats) is False
        assert s.add_candidate(project="p", from_id="c", to_id="d",
                               spuriousness=0.6, features=feats) is True
        st = s.stats("p")
        assert st["total"] == 2 and st["pending"] == 2 and st["labeled"] == 0

    def test_label_builds_golden_dataset(self, tmp_path):
        s = _store(tmp_path)
        s.add_candidate(project="p", from_id="a", to_id="b",
                        spuriousness=0.7, features={"heuristic": 0.7})
        s.add_candidate(project="p", from_id="c", to_id="d",
                        spuriousness=0.6, features={"heuristic": 0.6})
        ids = [r["id"] for r in s.pending("p")]
        assert s.label(ids[0], "prune") is True
        s.label(ids[1], "keep")
        st = s.stats("p")
        assert st["labeled"] == 2 and st["prune"] == 1 and st["keep"] == 1
        labeled = s.labeled("p")
        assert {r["label"] for r in labeled} == {"prune", "keep"}
        assert all(isinstance(r["features"], dict) for r in labeled)

    def test_label_rejects_invalid_value(self, tmp_path):
        s = _store(tmp_path)
        s.add_candidate(project="p", from_id="a", to_id="b")
        rid = s.pending("p")[0]["id"]
        with pytest.raises(ValueError):
            s.label(rid, "maybe")

    def test_pending_orders_by_uncertainty(self, tmp_path):
        s = _store(tmp_path)
        s.add_candidate(project="p", from_id="a", to_id="b", spuriousness=0.66)  # near 0.65
        s.add_candidate(project="p", from_id="c", to_id="d", spuriousness=0.95)
        assert [r["from_id"] for r in s.pending("p")][0] == "a"

    def test_export_jsonl(self, tmp_path):
        s = _store(tmp_path)
        s.add_candidate(project="p", from_id="a", to_id="b", features={"heuristic": 0.7})
        s.label(s.pending("p")[0]["id"], "prune")
        out = tmp_path / "golden.jsonl"
        assert s.export_jsonl("p", out) == 1
        line = json.loads(out.read_text().splitlines()[0])
        assert line["label"] == "prune" and "features" in line


class TestEdgeFeatures:
    def test_features_and_vector_consistent(self):
        import networkx as nx

        from hydramem.gnn_prune import compute_edge_features, edge_feature_vector

        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("a", "c")
        feats = compute_edge_features(g)
        assert ("a", "b") in feats
        vec = edge_feature_vector(feats[("a", "b")])
        assert len(vec) == len(PRUNE_FEATURES)
        assert all(isinstance(x, float) for x in vec)


class TestTrainPruner:
    def _labeled_store(self, tmp_path, n):
        s = PruneReviewStore(db_path=tmp_path / "r.db")
        for i in range(n):
            if i % 2 == 0:
                feats = {"heuristic": 0.9, "jaccard": 0.05, "common": 0.1,
                         "deg_u": 0.2, "deg_v": 0.2, "hub": 0.0}
                label = "prune"
            else:
                feats = {"heuristic": 0.2, "jaccard": 0.8, "common": 0.7,
                         "deg_u": 0.3, "deg_v": 0.3, "hub": 0.0}
                label = "keep"
            s.add_candidate(project="p", from_id=f"u{i}", to_id=f"v{i}",
                            spuriousness=feats["heuristic"], features=feats)
            s.label(s.pending("p", limit=1)[0]["id"], label)
        return s

    def test_trains_and_separates_classes(self, tmp_path):
        from hydramem.garden.prune_trainer import train_pruner

        s = self._labeled_store(tmp_path, n=40)
        report = train_pruner("p", store=s, save=False, epochs=300)
        assert report.n_train > 0
        assert report.auc >= 0.9  # cleanly separable synthetic data
        assert set(report.weights) == set(PRUNE_FEATURES)

    def test_refuses_too_few_samples(self, tmp_path):
        from hydramem.garden.prune_trainer import train_pruner

        s = self._labeled_store(tmp_path, n=4)
        with pytest.raises(RuntimeError):
            train_pruner("p", store=s, min_samples=20, save=False)

    def test_refuses_single_class(self, tmp_path):
        from hydramem.garden.prune_trainer import train_pruner

        s = PruneReviewStore(db_path=tmp_path / "r.db")
        for i in range(25):
            s.add_candidate(project="p", from_id=f"u{i}", to_id=f"v{i}",
                            features={"heuristic": 0.9})
            s.label(s.pending("p", limit=1)[0]["id"], "prune")
        with pytest.raises(RuntimeError):
            train_pruner("p", store=s, min_samples=10, save=False)


class TestGardenerCapture:
    def test_capture_disabled_by_default(self):
        from hydramem.garden.gardener import NightGardener

        g = NightGardener(
            store=_small_graph_store(), inferrer=MagicMock(),
            pipeline=MagicMock(), pruner=MagicMock(),
        )
        assert g._capture_prune_reviews("p") == {"queued": 0}

    def test_capture_enabled_queues_candidates(self, tmp_path):
        from hydramem.core.config import load_config
        from hydramem.garden.gardener import NightGardener

        cfg = load_config(
            {"night_gardener": {"review": {
                "enabled": True, "sample_rate": 1.0, "uncertainty_band": 1.0,
            }}}
        )
        review = PruneReviewStore(db_path=tmp_path / "r.db")
        g = NightGardener(
            store=_small_graph_store(), inferrer=MagicMock(), pipeline=MagicMock(),
            pruner=MagicMock(), config=cfg, review_store=review,
        )
        out = g._capture_prune_reviews("p")
        assert out["queued"] >= 4
        assert review.stats("p")["pending"] == out["queued"]


class TestLearnedScorerAndCLI:
    def test_full_loop_capture_label_train_score(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path))
        from hydramem.core.config import load_config
        from hydramem.garden.gardener import NightGardener
        from hydramem.garden.prune_trainer import train_pruner
        from hydramem.garden.review import load_prune_weights
        from hydramem.gnn_prune import GNNPruner

        store = _small_graph_store()
        review = PruneReviewStore(db_path=tmp_path / "r.db")
        cfg = load_config(
            {"night_gardener": {"review": {
                "enabled": True, "sample_rate": 1.0, "uncertainty_band": 1.0,
            }}}
        )
        gardener = NightGardener(
            store=store, inferrer=MagicMock(), pipeline=MagicMock(),
            pruner=MagicMock(), config=cfg, review_store=review,
        )
        queued = gardener._capture_prune_reviews("p")["queued"]
        assert queued >= 4

        # Human labels both classes → golden dataset.
        for i, row in enumerate(review.pending("p", limit=100)):
            review.label(row["id"], "prune" if i % 2 == 0 else "keep")

        report = train_pruner("p", store=review, min_samples=4, save=True)
        assert report.saved_path
        assert load_prune_weights("p") is not None

        # The pruner now uses the learned (supervised) backend.
        assert GNNPruner(store).analyse("p").method == "learned"

    def test_cli_review_status_and_train_refuses(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path))
        from hydramem.cli import cmd_review, cmd_train_pruner

        cmd_review(argparse.Namespace(project="p", limit=10, status=True, export=None))
        assert '"pending": 0' in capsys.readouterr().out

        with pytest.raises(SystemExit):
            cmd_train_pruner(argparse.Namespace(
                project="p", min_samples=20, test_fraction=0.2,
                l2=1.0, lr=0.1, epochs=100, dry_run=True,
            ))

    def test_auto_train_off_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path))
        from hydramem.garden.gardener import NightGardener

        review = PruneReviewStore(db_path=tmp_path / "r.db")
        g = NightGardener(
            store=_small_graph_store(), inferrer=MagicMock(), pipeline=MagicMock(),
            pruner=MagicMock(), review_store=review,
        )
        assert g._maybe_autotrain("p") is False

    def test_auto_train_when_enabled_and_enough_labels(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path))
        from hydramem.core.config import load_config
        from hydramem.garden.gardener import NightGardener
        from hydramem.garden.review import load_prune_weights

        review = PruneReviewStore(db_path=tmp_path / "r.db")
        for i in range(24):
            feats = {"heuristic": 0.9 if i % 2 == 0 else 0.2}
            review.add_candidate(project="p", from_id=f"u{i}", to_id=f"v{i}",
                                 spuriousness=feats["heuristic"], features=feats)
            review.label(review.pending("p", limit=1)[0]["id"],
                         "prune" if i % 2 == 0 else "keep")
        cfg = load_config(
            {"night_gardener": {"review": {"enabled": True, "auto_train": True}}}
        )
        g = NightGardener(
            store=_small_graph_store(), inferrer=MagicMock(), pipeline=MagicMock(),
            pruner=MagicMock(), config=cfg, review_store=review,
        )
        assert g._maybe_autotrain("p") is True
        assert load_prune_weights("p") is not None
