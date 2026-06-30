"""Tests for Personalized PageRank retrieval and RRF fusion."""
from __future__ import annotations

from unittest.mock import MagicMock

from hydramem.ppr import PPRRetriever, reciprocal_rank_fusion


def _store_for_chain():
    """Linear chain a -> b -> c -> d (undirected for PPR)."""
    store = MagicMock()
    store.list_entities.return_value = [
        {"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"},
    ]
    neighbors = {
        "a": [{"id": "b", "confidence": 1.0}],
        "b": [{"id": "a", "confidence": 1.0}, {"id": "c", "confidence": 1.0}],
        "c": [{"id": "b", "confidence": 1.0}, {"id": "d", "confidence": 1.0}],
        "d": [{"id": "c", "confidence": 1.0}],
    }
    store.get_entity_neighbors.side_effect = lambda nid, hops=1: neighbors.get(nid, [])
    return store


def test_ppr_seed_dominates_score():
    store = _store_for_chain()
    ppr = PPRRetriever(store)
    result = ppr.run(["a"], project="default", alpha=0.5, max_iter=100)
    assert result.converged
    # The seed node should have the highest mass at convergence.
    assert max(result.node_scores, key=result.node_scores.get) == "a"


def test_ppr_unknown_seed_returns_empty():
    store = _store_for_chain()
    ppr = PPRRetriever(store)
    result = ppr.run(["nonexistent"], project="default")
    assert result.node_scores == {}
    assert result.seeds == []


def test_ppr_invalidate_clears_cache():
    store = _store_for_chain()
    ppr = PPRRetriever(store)
    ppr.run(["a"], project="default")
    assert "default" in ppr._cache
    ppr.invalidate("default")
    assert "default" not in ppr._cache


def test_rrf_orders_by_consensus():
    rankings = [
        ["x", "y", "z"],
        ["y", "x", "z"],
        ["x", "z", "y"],
    ]
    fused = reciprocal_rank_fusion(rankings)
    # x is rank 1, 2, 1 → highest consensus.
    assert fused[0][0] == "x"
