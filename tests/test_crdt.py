"""Tests for the CRDT-style session merge."""

from __future__ import annotations

import json

from hydramem.garden.crdt import merge_session_files, merge_sessions


def _entry(summary: str, ts: str, repeat: int = 1) -> dict:
    return {"ts": ts, "tool_name": "priming_context", "summary": summary, "repeat_count": repeat}


def test_merge_dedupes_same_session_and_accumulates_repeats():
    local = [
        {
            "session_id": "s1",
            "project": "demo",
            "entries": [_entry("hello world", "2026-05-07T10:00:00+00:00", repeat=2)],
        }
    ]
    remote = [
        {
            "session_id": "s1",
            "project": "demo",
            "entries": [_entry("hello world", "2026-05-07T11:00:00+00:00", repeat=3)],
        }
    ]

    merged = merge_sessions(local, remote)
    assert len(merged) == 1
    entries = merged[0]["entries"]
    assert len(entries) == 1
    assert entries[0]["repeat_count"] == 5


def test_merge_preserves_distinct_sessions():
    local = [
        {
            "session_id": "s1",
            "project": "demo",
            "entries": [_entry("a", "2026-05-07T10:00:00+00:00")],
        }
    ]
    remote = [
        {
            "session_id": "s2",
            "project": "demo",
            "entries": [_entry("b", "2026-05-07T11:00:00+00:00")],
        }
    ]
    merged = merge_sessions(local, remote)
    assert {m["session_id"] for m in merged} == {"s1", "s2"}


def test_merge_session_files_writes_output(tmp_path):
    local_path = tmp_path / "local.json"
    remote_path = tmp_path / "remote.json"
    local_path.write_text(
        json.dumps(
            [
                {
                    "session_id": "s1",
                    "project": "demo",
                    "entries": [_entry("x", "2026-05-07T10:00:00+00:00")],
                }
            ]
        )
    )
    remote_path.write_text(
        json.dumps(
            [
                {
                    "session_id": "s1",
                    "project": "demo",
                    "entries": [_entry("y", "2026-05-07T11:00:00+00:00")],
                }
            ]
        )
    )

    summary = merge_session_files(local_path, remote_path)
    assert summary["merged_sessions"] == 1
    written = json.loads(local_path.read_text())
    assert written[0]["session_id"] == "s1"
    assert len(written[0]["entries"]) == 2
