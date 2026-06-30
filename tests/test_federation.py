"""Tests for federated signed exports / imports."""

from __future__ import annotations

import json

import pytest

from hydramem.core.types import Entity, Relation
from hydramem.storage import federation


class _FakeStore:
    def __init__(self) -> None:
        self.entities: list[dict] = []
        self.relations: list[dict] = []
        self.chunks: list = []
        self._graph = self  # so federation.import_project can call _graph.add_chunk

    # KnowledgeStore-shaped API
    def list_entities(self, project: str = "default") -> list[dict]:
        return [e for e in self.entities if e.get("project", project) == project]

    def list_relations(self, project: str = "default") -> list[dict]:
        return list(self.relations)

    def get_all_chunks(self) -> list:
        return list(self.chunks)

    def add_entity(self, entity: Entity) -> None:
        self.entities.append(
            {"id": entity.id, "name": entity.name, "type": entity.type, "project": entity.project}
        )

    def add_relation(self, relation: Relation) -> None:
        self.relations.append(
            {
                "from": relation.from_entity,
                "to": relation.to_entity,
                "relation_type": relation.relation_type,
                "confidence": relation.confidence,
                "verified": relation.verified,
                "session_id": relation.session_id,
                "origin_tool": relation.origin_tool,
                "created_at": relation.created_at,
            }
        )

    def add_chunk(self, chunk) -> None:
        self.chunks.append(chunk)


def test_export_then_import_roundtrip(tmp_path):
    src = _FakeStore()
    src.entities = [
        {"id": "e1", "name": "Alpha", "type": "concept", "project": "demo"},
        {"id": "e2", "name": "Beta", "type": "concept", "project": "demo"},
    ]
    src.relations = [
        {"from": "e1", "to": "e2", "relation_type": "uses", "confidence": 0.8, "verified": True},
    ]

    out = tmp_path / "export.json"
    summary = federation.export_project(out, project="demo", secret="hunter2", store=src)
    assert summary["entities"] == 2
    assert summary["relations"] == 1
    assert out.exists()

    dst = _FakeStore()
    federation.import_project(out, secret="hunter2", store=dst)
    assert len(dst.entities) == 2
    assert len(dst.relations) == 1
    assert dst.relations[0]["origin_tool"] in {"federation_import", ""}


def test_import_rejects_bad_signature(tmp_path):
    src = _FakeStore()
    out = tmp_path / "export.json"
    federation.export_project(out, project="demo", secret="key-A", store=src)
    dst = _FakeStore()
    with pytest.raises(ValueError, match="Signature"):
        federation.import_project(out, secret="wrong-key", store=dst)


def test_import_rejects_unlisted_issuer(tmp_path):
    src = _FakeStore()
    out = tmp_path / "export.json"
    federation.export_project(out, project="demo", secret="k", issuer="mallory", store=src)
    with pytest.raises(ValueError, match="Issuer"):
        federation.import_project(
            out, secret="k", store=_FakeStore(), accept_issuers=["alice", "bob"]
        )


def test_import_rejects_tampered_payload(tmp_path):
    src = _FakeStore()
    src.entities = [{"id": "e1", "name": "Alpha", "type": "concept", "project": "demo"}]
    out = tmp_path / "export.json"
    federation.export_project(out, project="demo", secret="k", store=src)
    envelope = json.loads(out.read_text())
    envelope["payload"]["entities"].append(
        {"id": "evil", "name": "Injected", "type": "concept", "project": "demo"}
    )
    out.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="Signature"):
        federation.import_project(out, secret="k", store=_FakeStore())
