"""Tests for Night Gardener session prioritization."""
from __future__ import annotations


def test_prepare_sessions_filters_and_prioritizes_by_repeat_count():
    from hydramem.garden.gardener import NightGardener

    sessions = [
        {
            "session_id": "sess-low",
            "entries": [
                {
                    "ts": "2026-05-07T10:00:00+00:00",
                    "tool_name": "priming_context",
                    "summary": "low repeat",
                    "repeat_count": 1,
                    "last_seen_at": "2026-05-07T10:00:00+00:00",
                }
            ],
        },
        {
            "session_id": "sess-high",
            "entries": [
                {
                    "ts": "2026-05-07T11:00:00+00:00",
                    "tool_name": "hydra_search",
                    "summary": "high repeat",
                    "repeat_count": 4,
                    "last_seen_at": "2026-05-07T11:00:00+00:00",
                },
                {
                    "ts": "2026-05-07T09:00:00+00:00",
                    "tool_name": "trace_path",
                    "summary": "medium repeat",
                    "repeat_count": 2,
                    "last_seen_at": "2026-05-07T09:00:00+00:00",
                },
            ],
        },
    ]

    prepared, metrics = NightGardener._prepare_sessions(sessions, min_repeat_count=2)

    assert [session["session_id"] for session in prepared] == ["sess-high"]
    assert [entry["repeat_count"] for entry in prepared[0]["entries"]] == [4, 2]
    assert "x4" in prepared[0]["text"]
    assert metrics == {
        "sessions_considered": 2,
        "sessions_used": 1,
        "entries_considered": 3,
        "entries_used": 2,
        "entries_filtered_repeat_threshold": 1,
    }


# ---------------------------------------------------------------------------
# Retrieval-success consolidation (Phase 2.5)
# ---------------------------------------------------------------------------


def test_consolidation_boosts_reused_and_decays_isolates():
    from unittest.mock import MagicMock

    from hydramem.garden.gardener import NightGardener

    adjust_calls: list[tuple[str, float]] = []

    class _FakeStore:
        def get_entity_neighbors(self, eid, hops=1):
            return [{"id": "n1"}, {"id": "n2"}]  # degree 2

        def adjust_confidences(self, eid, delta, *, min_confidence, max_confidence):
            adjust_calls.append((eid, delta))
            return 1

    reuse = [
        {"entity_id": "hot", "sessions_touched": 4, "total_touches": 9, "days_since": 1.0},
        {"entity_id": "cold", "sessions_touched": 1, "total_touches": 1, "days_since": 40.0},
        {"entity_id": "fresh", "sessions_touched": 1, "total_touches": 1, "days_since": 2.0},
    ]

    gardener = NightGardener(
        store=_FakeStore(),
        inferrer=MagicMock(),
        pipeline=MagicMock(),
        pruner=MagicMock(),
        reuse_fn=lambda project, window_days: reuse,
    )
    out = gardener._consolidate("p")

    assert out["entities_boosted"] == 1          # 'hot' boosted
    assert out["entities_decayed"] == 1          # 'cold' decayed (aged isolate)
    assert "hot" in out["protected_ids"]         # reused → prune-protected
    assert "cold" not in out["protected_ids"]
    assert "fresh" not in out["protected_ids"]   # recent single-touch untouched

    deltas = dict(adjust_calls)
    assert deltas["hot"] > 0                      # boost is positive
    assert deltas["cold"] < 0                     # decay is negative
    assert "fresh" not in deltas                  # within decay window → no change


def test_consolidation_disabled_is_noop():
    from unittest.mock import MagicMock

    from hydramem.core.config import load_config
    from hydramem.garden.gardener import NightGardener

    cfg = load_config({"night_gardener": {"consolidation": {"enabled": False}}})
    gardener = NightGardener(
        store=MagicMock(),
        inferrer=MagicMock(),
        pipeline=MagicMock(),
        pruner=MagicMock(),
        config=cfg,
        reuse_fn=lambda *a, **k: [
            {"entity_id": "x", "sessions_touched": 9, "days_since": 0.0}
        ],
    )
    out = gardener._consolidate("p")
    assert out == {"entities_boosted": 0, "entities_decayed": 0, "protected_ids": set()}


def test_pruner_protects_reused_entities():
    from unittest.mock import MagicMock

    from hydramem.garden.pruner import KnowledgePruner

    store = MagicMock()
    store.list_entities.return_value = [
        {"id": "iso1", "name": "Iso1"},
        {"id": "iso2", "name": "Iso2"},
    ]
    store.get_entity_neighbors.return_value = []   # both isolated
    store.get_chunks_near_entity.return_value = []
    store.delete_entity.return_value = True

    result = KnowledgePruner(store).prune(project="p", protected_ids={"iso1"})

    assert result["pruned_entities"] == 1          # only iso2 deleted
    assert result["prune_protected"] == 1          # iso1 protected from prune
    store.delete_entity.assert_called_once_with("iso2")


def test_adjust_confidences_clamps_outgoing_relations():
    from hydramem.core.types import Entity, Relation
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    store = KnowledgeStore(
        graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository()
    )
    store.add_entity(Entity(id="a", name="A", project="p"))
    store.add_entity(Entity(id="b", name="B", project="p"))
    store.add_relation(
        Relation(from_entity="a", to_entity="b", relation_type="rel", confidence=0.5)
    )

    assert store.adjust_confidences("a", 0.2) == 1
    edge = next(r for r in store.list_relations(project="p") if r["from"] == "a")
    assert abs(edge["confidence"] - 0.7) < 1e-9

    # Upper clamp holds.
    store.adjust_confidences("a", 5.0, max_confidence=0.99)
    edge = next(r for r in store.list_relations(project="p") if r["from"] == "a")
    assert edge["confidence"] == 0.99

    # Unknown entity → no-op.
    assert store.adjust_confidences("zzz", 0.1) == 0
