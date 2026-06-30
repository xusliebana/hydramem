"""Tests for the storage layer (KnowledgeStore + repositories)."""

from __future__ import annotations

import pytest

from hydramem.core.types import Chunk, Entity, Relation


class TestNetworkXGraphRepository:
    """Unit tests for the pure-Python graph backend."""

    @pytest.fixture
    def repo(self):
        from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository

        return NetworkXGraphRepository()

    def test_add_and_list_entity(self, repo):
        repo.add_entity(Entity(id="e1", name="HydraMem", type="concept", project="test"))
        entities = repo.list_entities(project="test")
        assert any(e["id"] == "e1" for e in entities)

    def test_add_and_delete_relation(self, repo):
        repo.add_entity(Entity(id="ea", name="A", project="test"))
        repo.add_entity(Entity(id="eb", name="B", project="test"))
        repo.add_relation(
            Relation(from_entity="ea", to_entity="eb", relation_type="causes", confidence=0.9)
        )
        assert repo._graph.has_edge("ea", "eb")

        deleted = repo.delete_relation("ea", "eb", "causes")
        assert deleted
        assert not repo._graph.has_edge("ea", "eb")

    def test_get_entity_neighbors(self, repo):
        repo.add_entity(Entity(id="ea", name="A", project="test"))
        repo.add_entity(Entity(id="eb", name="B", project="test"))
        repo.add_relation(
            Relation(from_entity="ea", to_entity="eb", relation_type="uses", confidence=0.8)
        )
        neighbours = repo.get_entity_neighbors("ea", hops=1)
        assert any(n["id"] == "eb" for n in neighbours)

    def test_add_and_get_chunks(self, repo):
        chunk = Chunk(id="c1", text="hello", source="t.md", project="test")
        repo.add_chunk(chunk)
        all_chunks = repo.get_all_chunks()
        assert any(c.id == "c1" for c in all_chunks)


class TestInMemoryVectorRepository:
    """Unit tests for the in-memory vector backend."""

    @pytest.fixture
    def repo(self):
        from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

        return InMemoryVectorRepository()

    def test_add_and_search(self, repo):
        chunk = Chunk(id="c1", text="hello world", source="t.md", project="test")
        embedding = [1.0] + [0.0] * 383
        repo.add(chunk, embedding)

        results = repo.search([1.0] + [0.0] * 383, k=5, project="test")
        assert len(results) >= 1
        assert results[0].id == "c1"

    def test_search_filters_by_project(self, repo):
        c1 = Chunk(id="c1", text="a", source="t.md", project="proj1")
        c2 = Chunk(id="c2", text="b", source="t.md", project="proj2")
        emb = [1.0] + [0.0] * 383
        repo.add(c1, emb)
        repo.add(c2, emb)
        results = repo.search(emb, k=5, project="proj1")
        ids = [r.id for r in results]
        assert "c1" in ids
        assert "c2" not in ids

    def test_get_all_raw(self, repo):
        chunk = Chunk(id="c1", text="hi", source="f.md", project="test")
        repo.add(chunk, [0.5] * 384)
        raw = repo.get_all_raw()
        assert any(r["id"] == "c1" for r in raw)


class TestKnowledgeStore:
    """Integration test of the KnowledgeStore facade."""

    @pytest.fixture
    def store(self):
        from hydramem.storage.factory import KnowledgeStore
        from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
        from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

        return KnowledgeStore(
            graph=NetworkXGraphRepository(),
            vector=InMemoryVectorRepository(),
        )

    def test_add_chunk_stored_in_both(self, store):
        chunk = Chunk(id="c1", text="test text", source="t.md", project="test")
        store.add_chunk(chunk, [1.0] + [0.0] * 383)
        # vector search returns it
        results = store.vector_search([1.0] + [0.0] * 383, k=5, project="test")
        assert any(r.id == "c1" for r in results)

    def test_add_and_list_entity(self, store):
        store.add_entity(Entity(id="e1", name="Test", project="test"))
        entities = store.list_entities(project="test")
        assert any(e["id"] == "e1" for e in entities)

    def test_add_and_delete_relation(self, store):
        store.add_entity(Entity(id="ea", name="A", project="test"))
        store.add_entity(Entity(id="eb", name="B", project="test"))
        rel = Relation(from_entity="ea", to_entity="eb", relation_type="uses", confidence=0.9)
        store.add_relation(rel)
        assert store.delete_relation("ea", "eb", "uses")


class TestLadybugDeprecation:
    def test_emits_deprecation_warning(self, tmp_path):
        import warnings
        from unittest.mock import MagicMock

        from hydramem.storage.graph.ladybug_repo import LadybugGraphRepository

        fake_mod = MagicMock()  # stands in for kuzu / ladybug
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            LadybugGraphRepository(str(tmp_path / "g.kuzu"), fake_mod)
        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
