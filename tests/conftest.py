"""Shared pytest fixtures for HydraMem tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Override all paths so tests never touch real files."""
    monkeypatch.setenv("LADYBUG_DB_PATH", str(tmp_path / "test.ladybug"))
    monkeypatch.setenv("LANCEDB_PATH", str(tmp_path / "lancedb"))
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "kms"))
    monkeypatch.setenv("HYDRAMEM_PROJECT", "test")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")

    import importlib

    import hydramem.core.config as cfg_mod
    importlib.reload(cfg_mod)
    yield


@pytest.fixture
def tmp_metrics_db(tmp_path, monkeypatch):
    import hydramem.telemetry.storage as storage_mod
    db_path = tmp_path / "metrics.db"
    monkeypatch.setattr(storage_mod, "DB_PATH", db_path)
    monkeypatch.setattr(storage_mod, "DB_DIR", tmp_path)
    return db_path


@pytest.fixture
def mock_store():
    """Return a MagicMock KnowledgeStore injected into the storage singleton."""
    import hydramem.storage.factory as fac
    mock = MagicMock()
    mock.vector_search.return_value = []
    mock.list_entities.return_value = []
    mock.get_entity_neighbors.return_value = []
    mock.get_chunks_near_entity.return_value = []
    mock.get_all_chunks_for_telemetry.return_value = []
    mock.get_all_chunks.return_value = []
    mock.list_relations.return_value = []
    with patch.object(fac, "_default_store", mock):
        with patch.object(fac, "get_store", return_value=mock):
            yield mock


@pytest.fixture
def mock_db(mock_store):
    return mock_store


@pytest.fixture
def sample_md_file(tmp_path):
    md = tmp_path / "sample.md"
    md.write_text("""# HydraMem

HydraMem is a local knowledge management system.

## Architecture

It uses LanceDB for vector search and LadybugDB for graph storage.

## Night Gardener

The Night Gardener runs autonomously to refine the knowledge graph.
""")
    return md
