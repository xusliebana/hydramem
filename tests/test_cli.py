"""Tests for CLI helpers."""

from __future__ import annotations

import argparse


def test_cmd_garden_status_json(monkeypatch, capsys):
    import hydramem.cli as cli

    class FakeRepo:
        def load(self):
            return {
                "last_run": "2026-05-07T03:00:12Z",
                "total_runs": 5,
                "relations_proposed": 12,
                "relations_accepted": 8,
                "relations_rejected": 4,
                "session_entries_filtered_repeat_threshold": 9,
                "nodes_pruned": 2,
                "edges_pruned": 3,
                "is_running": False,
            }

    monkeypatch.setattr("hydramem.garden.repository.StatusRepository", FakeRepo)

    cli.cmd_garden_status(argparse.Namespace(json=True))
    out = capsys.readouterr().out

    assert '"session_entries_filtered_repeat_threshold": 9' in out


def test_print_garden_status_plain(capsys):
    import hydramem.cli as cli

    cli._print_garden_status_plain(
        {
            "last_run": "2026-05-07T03:00:12Z",
            "total_runs": 5,
            "relations_proposed": 12,
            "relations_accepted": 8,
            "relations_rejected": 4,
            "session_entries_filtered_repeat_threshold": 9,
            "nodes_pruned": 2,
            "edges_pruned": 3,
            "is_running": False,
        }
    )
    out = capsys.readouterr().out

    assert "Entries filtered repeat thresh:" in out
    assert "9" in out


def test_print_plain_stats_includes_garden_metrics(capsys):
    import hydramem.cli as cli

    cli._print_plain_table(
        {
            "period_start": "2026-05-01T00:00:00Z",
            "period_end": "2026-05-07T00:00:00Z",
            "projects": "default",
            "total_calls": 10,
            "tokens_without_hydramem": 1000,
            "tokens_injected": 400,
            "tokens_saved": 600,
            "savings_pct": 60.0,
            "cost_saved_usd": 0.003,
            "avg_vog_score": 0.8,
            "rejected_srmkg": 2,
            "rejected_vog": 1,
            "cross_project_hits": 0,
            "hallucinations_blocked": 1,
            "garden_last_run": "2026-05-07T03:00:12Z",
            "garden_total_runs": 5,
            "garden_entries_filtered_repeat_threshold": 9,
            "garden_nodes_pruned": 2,
            "garden_edges_pruned": 3,
        },
        7,
    )
    out = capsys.readouterr().out

    assert "Garden entries filt:" in out
    assert "9" in out


def test_export_md_includes_garden_metrics(capsys):
    import hydramem.cli as cli

    cli._export_md(
        {
            "period_days": 7,
            "period_start": "2026-05-01T00:00:00Z",
            "period_end": "2026-05-07T00:00:00Z",
            "projects": "default",
            "total_calls": 10,
            "tokens_without_hydramem": 1000,
            "tokens_injected": 400,
            "tokens_saved": 600,
            "savings_pct": 60.0,
            "cost_saved_usd": 0.003,
            "avg_vog_score": 0.8,
            "rejected_srmkg": 2,
            "rejected_vog": 1,
            "cross_project_hits": 0,
            "hallucinations_blocked": 1,
            "garden_last_run": "2026-05-07T03:00:12Z",
            "garden_total_runs": 5,
            "garden_entries_filtered_repeat_threshold": 9,
            "garden_nodes_pruned": 2,
            "garden_edges_pruned": 3,
        }
    )
    out = capsys.readouterr().out

    assert "| Garden entries filtered | 9 |" in out
