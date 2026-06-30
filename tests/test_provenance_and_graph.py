"""Tests for persistent MENTIONS edges + graph-only search + provenance."""
from __future__ import annotations

from hydramem.core.types import Chunk, Entity, Relation
from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository


def test_networkx_persistent_mentions():
    repo = NetworkXGraphRepository()
    chunk = Chunk(id="c1", text="LanceDB is great", source="x.md", chunk_idx=0, doc_id="d1", project="demo")
    repo.add_chunk(chunk)
    repo.add_entity(Entity(id="e1", name="LanceDB", type="identifier", project="demo"))
    repo.add_mention("c1", "e1")

    near = repo.get_chunks_near_entity("e1")
    assert len(near) == 1
    assert near[0].id == "c1"


def test_networkx_relation_records_provenance():
    repo = NetworkXGraphRepository()
    repo.add_entity(Entity(id="a", name="A", project="demo"))
    repo.add_entity(Entity(id="b", name="B", project="demo"))
    rel = Relation(
        from_entity="a", to_entity="b", relation_type="uses",
        confidence=0.9, verified=True, project="demo",
        session_id="sess-42", origin_tool="verify_relation",
        created_at="2026-05-08T10:00:00+00:00",
    )
    repo.add_relation(rel)
    edges = list(repo._graph.edges(data=True))
    assert edges[0][2]["session_id"] == "sess-42"
    assert edges[0][2]["origin_tool"] == "verify_relation"
    assert edges[0][2]["created_at"] == "2026-05-08T10:00:00+00:00"


def test_networkx_relation_qualifiers_roundtrip():
    repo = NetworkXGraphRepository()
    repo.add_entity(Entity(id="a", name="A", project="demo"))
    repo.add_entity(Entity(id="b", name="B", project="demo"))
    repo.add_relation(Relation(
        from_entity="a", to_entity="b", relation_type="uses",
        confidence=0.8, project="demo",
        qualifiers={"valid_from": "2026-01-01", "verifier": "manual"},
    ))
    rels = repo.list_relations(project="demo")
    assert rels[0]["qualifiers"]["valid_from"] == "2026-01-01"
    assert rels[0]["qualifiers"]["verifier"] == "manual"


def test_networkx_relation_readd_merges_qualifiers_no_collision():
    repo = NetworkXGraphRepository()
    repo.add_entity(Entity(id="a", name="A", project="demo"))
    repo.add_entity(Entity(id="b", name="B", project="demo"))
    # First observation: temporal start + manual verifier, low confidence.
    repo.add_relation(Relation(
        from_entity="a", to_entity="b", relation_type="uses",
        confidence=0.4, verified=False, project="demo",
        qualifiers={"valid_from": "2026-01-01", "verifier": "manual"},
    ))
    # Re-observe the SAME typed edge: add an end date, upgrade the verifier,
    # higher confidence, now verified. Must MERGE, not collide/overwrite.
    repo.add_relation(Relation(
        from_entity="a", to_entity="b", relation_type="uses",
        confidence=0.9, verified=True, project="demo",
        qualifiers={"valid_to": "2026-06-01", "verifier": "vog"},
    ))
    rels = repo.list_relations(project="demo")
    assert len(rels) == 1                     # still one edge, no duplicate
    q = rels[0]["qualifiers"]
    assert q["valid_from"] == "2026-01-01"    # preserved from first observation
    assert q["valid_to"] == "2026-06-01"      # added by the second
    assert q["verifier"] == "vog"             # newer wins
    assert rels[0]["confidence"] == 0.9       # strongest confidence kept
    assert rels[0]["verified"] is True        # verified OR-accumulated


def test_relation_valid_at_temporal_window():
    from hydramem.core.types import relation_valid_at
    q = {"valid_from": "2026-01-01", "valid_to": "2026-06-01"}
    assert relation_valid_at(q, "2026-03-01")              # inside window
    assert not relation_valid_at(q, "2025-12-31")          # before start
    assert not relation_valid_at(q, "2026-07-01")          # after end
    assert relation_valid_at(q, "2026-06-01T12:00:00Z")    # date-only end = whole day
    assert relation_valid_at({}, "2026-03-01")             # no window = always valid
    assert relation_valid_at(q, "")                         # no as_of = match all


def test_temporal_neighbors_and_entity_relations_as_of():
    from hydramem.search import SearchService
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    repo = NetworkXGraphRepository()
    for eid, name in (("a", "A"), ("b", "B"), ("c", "C")):
        repo.add_entity(Entity(id=eid, name=name, project="demo"))
    # A worked on B only in H1 2026; A works on C from mid-2026 onward.
    repo.add_relation(Relation(
        from_entity="a", to_entity="b", relation_type="worked_on",
        confidence=0.9, project="demo",
        qualifiers={"valid_from": "2026-01-01", "valid_to": "2026-06-01"},
    ))
    repo.add_relation(Relation(
        from_entity="a", to_entity="c", relation_type="worked_on",
        confidence=0.9, project="demo",
        qualifiers={"valid_from": "2026-07-01"},
    ))
    svc = SearchService(
        store=KnowledgeStore(graph=repo, vector=InMemoryVectorRepository())
    )

    march = {e["id"] for e in svc.temporal_neighbors("a", project="demo", as_of="2026-03-01")}
    assert march == {"b"}
    august = {e["id"] for e in svc.temporal_neighbors("a", project="demo", as_of="2026-08-01")}
    assert august == {"c"}
    assert {e["id"] for e in svc.temporal_neighbors("a", project="demo")} == {"b", "c"}

    facts = svc.entity_relations("a", project="demo", as_of="2026-03-01")
    assert len(facts) == 1
    assert facts[0]["to"] == "b"
    assert facts[0]["valid_to"] == "2026-06-01"
    assert facts[0]["current"] is False


def test_search_service_graph_only(monkeypatch):
    from hydramem.search import SearchService

    repo = NetworkXGraphRepository()
    chunk = Chunk(
        id="c1",
        text="The Night Gardener prunes the graph nightly.",
        source="x.md",
        chunk_idx=0,
        doc_id="d1",
        project="demo",
    )
    repo.add_chunk(chunk)
    repo.add_entity(Entity(id="e1", name="Night Gardener", type="concept", project="demo"))
    repo.add_mention("c1", "e1")

    # Build a SearchService with our NetworkX repo as the underlying store.
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    store = KnowledgeStore(graph=repo, vector=InMemoryVectorRepository())
    svc = SearchService(store=store)

    result = svc.graph_only_search("Tell me about Night Gardener", project="demo")
    assert result["method"] == "graph_only"
    assert any(c["id"] == "c1" for c in result["chunks"])
    assert any(e.get("name") == "Night Gardener" for e in result["matched_entities"])


def test_pluggable_extractor_factory_unknown_name():
    import pytest

    from hydramem.ingest.extractor import create_extractor

    with pytest.raises(ValueError):
        create_extractor("does-not-exist")


def test_pluggable_extractor_default_is_heuristic():
    from hydramem.ingest.extractor import EntityExtractor, create_extractor

    assert isinstance(create_extractor(), EntityExtractor)
