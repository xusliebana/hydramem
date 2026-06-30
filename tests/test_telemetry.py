"""Tests for hydramem/telemetry/ (storage, shadow, stats query)."""

from __future__ import annotations

import sqlite3


class TestInitDb:
    def test_creates_table(self, tmp_metrics_db):
        from hydramem.telemetry.storage import init_db

        init_db()
        assert tmp_metrics_db.exists()

        with sqlite3.connect(tmp_metrics_db) as conn:
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert "events" in tables

    def test_idempotent(self, tmp_metrics_db):
        from hydramem.telemetry.storage import init_db

        init_db()
        init_db()  # should not raise

        with sqlite3.connect(tmp_metrics_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 0


class TestLogEvent:
    def test_inserts_row(self, tmp_metrics_db):
        from hydramem.telemetry.storage import init_db, log_event

        init_db()
        log_event(
            project="proj1",
            tool_name="hydra_search",
            session_id="sess-abc",
            tokens_injected=100,
            tokens_baseline=500,
            vog_score=0.87,
            chunks_total=10,
            chunks_rejected_srmkg=2,
            chunks_rejected_vog=1,
            latency_ms=120,
        )

        with sqlite3.connect(tmp_metrics_db) as conn:
            row = conn.execute(
                "SELECT project, tool_name, tokens_injected, tokens_baseline, vog_score"
                " FROM events ORDER BY id DESC LIMIT 1"
            ).fetchone()

        assert row[0] == "proj1"
        assert row[1] == "hydra_search"
        assert row[2] == 100
        assert row[3] == 500
        assert abs(row[4] - 0.87) < 0.001

    def test_never_raises_on_bad_db(self, monkeypatch, tmp_path):
        """log_event must silently swallow errors."""
        import hydramem.telemetry.storage as storage_mod

        monkeypatch.setattr(storage_mod, "DB_PATH", tmp_path / "bad" / "metrics.db")
        monkeypatch.setattr(storage_mod, "DB_DIR", tmp_path / "bad")

        # Should NOT raise even when directory creation might fail on weird paths
        from hydramem.telemetry.storage import log_event

        log_event(tool_name="test")  # no exception


class TestQueryStats:
    def test_returns_zeros_when_empty(self, tmp_metrics_db):
        from hydramem.telemetry.storage import init_db, query_stats

        init_db()
        stats = query_stats(days=7)
        assert stats["total_calls"] == 0
        assert stats["total_injected"] == 0

    def test_aggregates_correctly(self, tmp_metrics_db):
        from hydramem.telemetry.storage import init_db, log_event, query_stats

        init_db()
        log_event(tokens_injected=100, tokens_baseline=400, vog_score=0.8)
        log_event(tokens_injected=200, tokens_baseline=600, vog_score=0.9)

        stats = query_stats(days=7)
        assert stats["total_calls"] == 2
        assert stats["total_injected"] == 300
        assert stats["total_baseline"] == 1000
        assert abs(stats["avg_vog"] - 0.85) < 0.01


class TestEstimateNaiveRagTokens:
    def test_returns_positive_int(self):
        from hydramem.telemetry.shadow import estimate_naive_rag_tokens

        class FakeChunk:
            def __init__(self, text, sim):
                self.text = text
                self.similarity = sim

        chunks = [
            FakeChunk(f"This is chunk number {i} with some text.", 1.0 - i * 0.05)
            for i in range(25)
        ]
        result = estimate_naive_rag_tokens("What is HydraMem?", chunks, k=20)
        assert isinstance(result, int)
        assert result > 0

    def test_k_limits_chunks(self):
        from hydramem.telemetry.shadow import estimate_naive_rag_tokens

        chunks = [{"text": "x " * 100, "similarity": 1.0} for _ in range(50)]
        result_5 = estimate_naive_rag_tokens("query", chunks, k=5)
        result_20 = estimate_naive_rag_tokens("query", chunks, k=20)
        assert result_20 > result_5

    def test_handles_dict_chunks(self):
        from hydramem.telemetry.shadow import estimate_naive_rag_tokens

        chunks = [{"text": "Hello world", "similarity": 0.9}]
        result = estimate_naive_rag_tokens("test", chunks, k=10)
        assert result > 0

    def test_handles_empty_chunks(self):
        from hydramem.telemetry.shadow import estimate_naive_rag_tokens

        result = estimate_naive_rag_tokens("test", [], k=10)
        assert result > 0  # at least the query tokens


class TestEntityReuse:
    def test_aggregates_sessions_and_recency(self, tmp_metrics_db):
        from hydramem.telemetry.storage import entity_reuse, init_db, log_event

        init_db()
        # e1 retrieved in two distinct sessions; e2 in one.
        log_event(project="p", session_id="s1", metadata={"entities": ["e1", "e2"]})
        log_event(project="p", session_id="s2", metadata={"entities": ["e1"]})
        # A different project must not leak into the reuse signal.
        log_event(project="other", session_id="s3", metadata={"entities": ["e1"]})

        reuse = {r["entity_id"]: r for r in entity_reuse("p", window_days=30)}
        assert set(reuse) == {"e1", "e2"}  # 'other' project excluded
        assert reuse["e1"]["sessions_touched"] == 2
        assert reuse["e1"]["total_touches"] == 2
        assert reuse["e2"]["sessions_touched"] == 1
        assert reuse["e1"]["days_since"] >= 0.0

    def test_empty_when_no_entities_logged(self, tmp_metrics_db):
        from hydramem.telemetry.storage import entity_reuse, init_db, log_event

        init_db()
        log_event(project="p", session_id="s1")  # no entities in metadata
        assert entity_reuse("p") == []
