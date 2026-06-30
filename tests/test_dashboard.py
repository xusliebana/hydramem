"""Tests for the read-only HTML dashboard."""
from __future__ import annotations

from hydramem import dashboard


def test_render_html_contains_metrics(monkeypatch):
    monkeypatch.setattr(dashboard, "_compute_stats", lambda days: {"period_days": days, "total_calls": 7})
    monkeypatch.setattr(dashboard, "_load_garden_metrics", lambda: {"garden_total_runs": 3})
    html = dashboard._render_html(dashboard._gather(7))
    assert "HydraMem dashboard" in html
    assert "total_calls" in html
    assert "garden_total_runs" in html


def test_gather_merges_stats_and_garden(monkeypatch):
    monkeypatch.setattr(dashboard, "_compute_stats", lambda days: {"a": 1})
    monkeypatch.setattr(dashboard, "_load_garden_metrics", lambda: {"b": 2})
    out = dashboard._gather(1)
    assert out["a"] == 1
    assert out["b"] == 2
