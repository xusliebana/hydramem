"""Targeted tests for MCP server session persistence."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock


def _install_fake_fastmcp() -> None:
    class FakeFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self, *args, **kwargs):
            return None

    sys.modules.setdefault("fastmcp", SimpleNamespace(FastMCP=FakeFastMCP))


def test_priming_context_persists_compact_session(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.server as server

    fake_search = MagicMock()
    fake_search.priming_context.return_value = {
        "context": "HydraMem links entities through verified graph context.",
        "chunks": [{"id": "c1"}],
    }

    fake_gardener = MagicMock()
    monkeypatch.setattr(server, "_search", fake_search)
    monkeypatch.setattr(server, "_gardener", fake_gardener)
    monkeypatch.setattr(server, "estimate_naive_rag_tokens", lambda *args, **kwargs: 12)

    result = server.priming_context_tool("How does HydraMem reason?", project="demo")

    assert result["context"].startswith("HydraMem links")
    fake_gardener.save_session.assert_called_once()
    saved_session = fake_gardener.save_session.call_args.args[0]
    assert saved_session["project"] == "demo"
    assert saved_session["tool_name"] == "priming_context"
    assert saved_session["query"] == "How does HydraMem reason?"
    assert saved_session["session_id"]
    assert saved_session["entry"]["tool_name"] == "priming_context"
    assert "Grounded context:" in saved_session["entry"]["summary"]


def test_hydra_search_persists_final_context(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.server as server

    fake_search = MagicMock()
    fake_search.hydra_search.return_value = {
        "final_context": "Entity A is connected to Entity B through verified evidence.",
        "chunks_total": 2,
        "rejected_srmkg": 0,
        "rejected_vog": 0,
        "avg_vog_score": 0.88,
    }

    fake_gardener = MagicMock()
    monkeypatch.setattr(server, "_search", fake_search)
    monkeypatch.setattr(server, "_gardener", fake_gardener)
    monkeypatch.setattr(server, "estimate_naive_rag_tokens", lambda *args, **kwargs: 20)

    result = server.hydra_search_tool("Relate A and B", project="demo")

    assert result["chunks_total"] == 2
    fake_gardener.save_session.assert_called_once()
    saved_session = fake_gardener.save_session.call_args.args[0]
    assert saved_session["tool_name"] == "hydra_search"
    assert saved_session["query"] == "Relate A and B"
    assert "verified evidence" in saved_session["entry"]["summary"]


def test_trace_path_persists_summary(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.server as server

    fake_search = MagicMock()
    fake_search.trace_path.return_value = {
        "path": ["A", "B", "C"],
        "length": 2,
        "found": True,
    }

    fake_gardener = MagicMock()
    monkeypatch.setattr(server, "_search", fake_search)
    monkeypatch.setattr(server, "_gardener", fake_gardener)

    result = server.trace_path_tool("A", "C", project="demo", session_id="sess-1")

    assert result["found"] is True
    saved_session = fake_gardener.save_session.call_args.args[0]
    assert saved_session["session_id"] == "sess-1"
    assert saved_session["tool_name"] == "trace_path"
    assert "A -> B -> C" in saved_session["entry"]["summary"]


def test_hydramem_stats_tool_returns_aggregate(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.cli as cli
    import hydramem.server as server

    monkeypatch.setattr(cli, "_compute_stats", lambda days: {"total_calls": 5, "period_days": days})
    monkeypatch.setattr(cli, "_load_garden_metrics", lambda: {"garden_total_runs": 2})

    result = server.hydramem_stats_tool(days=14)
    assert result["available"] is True
    assert result["total_calls"] == 5
    assert result["period_days"] == 14
    assert result["garden_total_runs"] == 2


def test_hydramem_stats_tool_handles_empty(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.cli as cli
    import hydramem.server as server

    monkeypatch.setattr(cli, "_compute_stats", lambda days: {})
    result = server.hydramem_stats_tool(days=3)
    assert result == {"available": False, "period_days": 3}


def test_graph_only_search_tool(monkeypatch):
    _install_fake_fastmcp()
    import hydramem.server as server

    fake_search = MagicMock()
    fake_search.graph_only_search.return_value = {
        "method": "graph_only",
        "chunks": [{"id": "c1"}],
        "context": "ctx",
        "entities": ["X"],
        "matched_entities": [{"id": "e1"}],
    }
    monkeypatch.setattr(server, "_search", fake_search)

    out = server.graph_only_search_tool("query about X", project="demo")
    assert out["method"] == "graph_only"
    fake_search.graph_only_search.assert_called_once()
