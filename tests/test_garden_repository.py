"""Tests for grouped Night Gardener session persistence."""

from __future__ import annotations

from hydramem.garden.repository import SessionRepository


def test_save_groups_entries_by_session_id(tmp_path):
    repo = SessionRepository(path=tmp_path / "sessions.json")

    repo.save(
        {
            "project": "demo",
            "session_id": "sess-1",
            "query": "How does HydraMem work?",
            "updated_at": "2026-05-07T10:00:00+00:00",
            "entry": {
                "ts": "2026-05-07T10:00:00+00:00",
                "tool_name": "priming_context",
                "summary": "Query: How does HydraMem work?\nGrounded context:\nChunk A",
            },
        }
    )
    repo.save(
        {
            "project": "demo",
            "session_id": "sess-1",
            "query": "How does HydraMem work?",
            "updated_at": "2026-05-07T10:01:00+00:00",
            "entry": {
                "ts": "2026-05-07T10:01:00+00:00",
                "tool_name": "trace_path",
                "summary": "Trace path from A to B\nFound: True",
            },
        }
    )

    sessions = repo.load()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess-1"
    assert len(sessions[0]["entries"]) == 2
    assert sessions[0]["updated_at"] == "2026-05-07T10:01:00+00:00"
    assert "priming_context" in sessions[0]["text"]
    assert "trace_path" in sessions[0]["text"]


def test_save_declines_duplicate_context(tmp_path):
    repo = SessionRepository(path=tmp_path / "sessions.json")

    payload = {
        "project": "demo",
        "session_id": "sess-1",
        "query": "How does HydraMem work?",
        "updated_at": "2026-05-07T10:00:00+00:00",
        "entry": {
            "ts": "2026-05-07T10:00:00+00:00",
            "tool_name": "priming_context",
            "summary": "Query: How does HydraMem work?\nGrounded context:\nChunk A",
        },
    }

    repo.save(payload)
    repo.save(
        {
            **payload,
            "updated_at": "2026-05-07T10:05:00+00:00",
            "entry": {
                **payload["entry"],
                "ts": "2026-05-07T10:05:00+00:00",
            },
        }
    )

    sessions = repo.load()
    assert len(sessions) == 1
    assert len(sessions[0]["entries"]) == 1
    assert sessions[0]["entries"][0]["fingerprint"]
    assert sessions[0]["entries"][0]["repeat_count"] == 2
    assert sessions[0]["entries"][0]["last_seen_at"] == "2026-05-07T10:05:00+00:00"
    assert sessions[0]["updated_at"] == "2026-05-07T10:05:00+00:00"
    assert "x2" in sessions[0]["text"]
