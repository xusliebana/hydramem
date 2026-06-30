"""Temporal invalidation of superseded facts (Zep/Graphiti-style).

A new *functional* relation supersedes an older conflicting one by closing the
old edge's validity window (`valid_to`) rather than deleting it, so history is
preserved and `as_of` retrieval stays correct.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from hydramem.core.types import Entity, Relation, relation_valid_at


def _store():
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    return KnowledgeStore(
        graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository()
    )


def _add(store, frm, to, rtype="located_in", **quals):
    store.add_entity(Entity(id=frm, name=frm, project="p"))
    store.add_entity(Entity(id=to, name=to, project="p"))
    store.add_relation(
        Relation(from_entity=frm, to_entity=to, relation_type=rtype,
                 confidence=0.9, qualifiers=dict(quals))
    )


def _quals(store, frm, to):
    for r in store.list_relations(project="p"):
        if r["from"] == frm and r["to"] == to:
            return r.get("qualifiers") or {}
    return None


class TestSupersedeRelations:
    def test_invalidates_older_conflicting_edge(self):
        store = _store()
        _add(store, "alice", "paris")    # alice located_in paris (old)
        _add(store, "alice", "london")   # alice located_in london (new)
        n = store.supersede_relations(
            "alice", "located_in", keep_to="london", valid_to="2026-06-30T00:00:00Z"
        )
        assert n == 1
        assert _quals(store, "alice", "paris").get("valid_to") == "2026-06-30T00:00:00Z"
        assert "valid_to" not in (_quals(store, "alice", "london") or {})

    def test_does_not_touch_other_relation_types(self):
        store = _store()
        _add(store, "alice", "paris", rtype="located_in")
        _add(store, "alice", "acme", rtype="works_at")
        n = store.supersede_relations("alice", "located_in", keep_to="berlin", valid_to="T")
        assert n == 1                                    # only paris (located_in)
        assert (_quals(store, "alice", "acme") or {}).get("valid_to") in (None, "")

    def test_idempotent_and_unknown_entity(self):
        store = _store()
        _add(store, "alice", "paris")
        store.supersede_relations("alice", "located_in", keep_to="x", valid_to="T1")
        # Already closed → second call is a no-op.
        assert store.supersede_relations("alice", "located_in", keep_to="x", valid_to="T2") == 0
        assert _quals(store, "alice", "paris").get("valid_to") == "T1"
        assert store.supersede_relations("ghost", "located_in", "x", "T") == 0

    def test_as_of_excludes_invalidated(self):
        store = _store()
        _add(store, "alice", "paris", valid_from="2020-01-01")
        store.supersede_relations("alice", "located_in", keep_to="london", valid_to="2026-01-01")
        q = _quals(store, "alice", "paris")
        assert relation_valid_at(q, "2021-06-01") is True    # before the change
        assert relation_valid_at(q, "2026-06-01") is False   # after the change


class TestGardenerTemporalInvalidation:
    def _gardener(self, store, cfg=None):
        from hydramem.garden.gardener import NightGardener

        return NightGardener(
            store=store, inferrer=MagicMock(), pipeline=MagicMock(),
            pruner=MagicMock(), config=cfg,
        )

    def test_disabled_by_default(self):
        store = _store()
        _add(store, "alice", "paris")
        g = self._gardener(store)
        rel = Relation(from_entity="alice", to_entity="london", relation_type="located_in")
        assert g._invalidate_superseded([rel]) == 0
        assert "valid_to" not in (_quals(store, "alice", "paris") or {})

    def test_enabled_invalidates_functional(self):
        from hydramem.core.config import load_config

        store = _store()
        _add(store, "alice", "paris")
        cfg = load_config({"night_gardener": {"temporal_invalidation": {
            "enabled": True, "functional_types": ["located_in"]}}})
        g = self._gardener(store, cfg)
        rel = Relation(from_entity="alice", to_entity="london", relation_type="located_in",
                       qualifiers={"valid_from": "2026-06-30"})
        assert g._invalidate_superseded([rel]) == 1
        assert _quals(store, "alice", "paris").get("valid_to") == "2026-06-30"

    def test_enabled_ignores_non_functional_types(self):
        from hydramem.core.config import load_config

        store = _store()
        _add(store, "alice", "bob", rtype="knows")
        cfg = load_config({"night_gardener": {"temporal_invalidation": {
            "enabled": True, "functional_types": ["located_in"]}}})
        g = self._gardener(store, cfg)
        rel = Relation(from_entity="alice", to_entity="carol", relation_type="knows")
        assert g._invalidate_superseded([rel]) == 0
