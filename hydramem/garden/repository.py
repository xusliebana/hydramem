"""Session and Status repositories — single responsibility: persistence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hydramem.core.config import hydramem_home

_HOME = hydramem_home()

_DEFAULT_STATUS: dict = {
    "last_run": None,
    "total_runs": 0,
    "relations_proposed": 0,
    "relations_accepted": 0,
    "relations_rejected": 0,
    "session_entries_filtered_repeat_threshold": 0,
    "nodes_pruned": 0,
    "edges_pruned": 0,
    "is_running": False,
}


class StatusRepository:
    """Persists Night Gardener run status to a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_HOME / "garden_status.json")

    def load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:  # noqa: BLE001
                pass
        return dict(_DEFAULT_STATUS)

    def save(self, status: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(status, indent=2, default=str))


class SessionRepository:
    """Persists Q&A sessions written during agent interactions."""

    _MAX_SESSIONS = 200
    _MAX_ENTRIES_PER_SESSION = 50
    _MAX_TEXT_ENTRIES = 12

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_HOME / "sessions.json")

    def load(self) -> list[dict]:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except Exception:  # noqa: BLE001
                pass
        return []

    def save(self, session: dict) -> None:
        sessions = self.load()
        normalized = self._normalise_session(session)

        if normalized.get("session_id"):
            merged = False
            for index, existing in enumerate(sessions):
                if existing.get("session_id") == normalized.get("session_id") and existing.get(
                    "project"
                ) == normalized.get("project"):
                    sessions[index] = self._merge_sessions(existing, normalized)
                    merged = True
                    break
            if not merged:
                sessions.append(normalized)
        else:
            sessions.append(normalized)

        sessions = sorted(
            sessions,
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        )[-self._MAX_SESSIONS :]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(sessions, indent=2, default=str))

    def last_n(self, n: int = 20) -> list[dict]:
        return self.load()[-n:]

    @classmethod
    def _normalise_session(cls, session: dict) -> dict:
        created_at = session.get("created_at") or session.get("updated_at")
        entries = list(session.get("entries") or [])
        if session.get("entry"):
            entries.append(session["entry"])

        entries = cls._normalise_entries(entries)
        if entries:
            created_at = created_at or entries[0].get("ts")

        normalized = {
            "id": session.get("id") or session.get("session_id") or created_at,
            "session_id": session.get("session_id"),
            "project": session.get("project", "default"),
            "created_at": created_at,
            "updated_at": session.get("updated_at")
            or (entries[-1].get("ts") if entries else created_at),
            "tool_name": session.get("tool_name"),
            "query": session.get("query", ""),
            "entries": entries[-cls._MAX_ENTRIES_PER_SESSION :],
        }

        if normalized["entries"]:
            normalized["text"] = cls._build_text(normalized["entries"])
        else:
            normalized["text"] = session.get("text", "")

        return normalized

    @classmethod
    def _merge_sessions(cls, existing: dict, incoming: dict) -> dict:
        entries = cls._normalise_entries(
            list(existing.get("entries") or []) + list(incoming.get("entries") or [])
        )[-cls._MAX_ENTRIES_PER_SESSION :]
        merged = {
            **existing,
            **incoming,
            "id": existing.get("id") or incoming.get("id"),
            "created_at": existing.get("created_at") or incoming.get("created_at"),
            "updated_at": (
                entries[-1].get("ts")
                if entries
                else incoming.get("updated_at") or existing.get("updated_at")
            ),
            "query": incoming.get("query") or existing.get("query", ""),
            "entries": entries,
        }
        merged["text"] = cls._build_text(entries) if entries else merged.get("text", "")
        return merged

    @classmethod
    def _normalise_entries(cls, entries: list[dict]) -> list[dict]:
        normalized_entries: list[dict] = []
        index_by_fingerprint: dict[str, int] = {}

        for raw_entry in entries:
            summary = str(raw_entry.get("summary", "")).strip()
            if not summary:
                continue

            fingerprint = raw_entry.get("fingerprint") or cls._fingerprint(summary)
            ts = raw_entry.get("ts", "")
            repeat_count = int(raw_entry.get("repeat_count", 1) or 1)

            if fingerprint in index_by_fingerprint:
                existing = normalized_entries[index_by_fingerprint[fingerprint]]
                existing["repeat_count"] = int(existing.get("repeat_count", 1) or 1) + repeat_count
                existing["last_seen_at"] = (
                    ts or existing.get("last_seen_at") or existing.get("ts", "")
                )
                if ts and ts >= str(existing.get("ts", "")):
                    existing["ts"] = ts
                continue

            normalized_entries.append(
                {
                    **raw_entry,
                    "summary": summary,
                    "fingerprint": fingerprint,
                    "repeat_count": repeat_count,
                    "last_seen_at": raw_entry.get("last_seen_at") or ts,
                }
            )
            index_by_fingerprint[fingerprint] = len(normalized_entries) - 1

        return normalized_entries

    @staticmethod
    def _fingerprint(summary: str) -> str:
        return hashlib.sha256(summary.strip().encode("utf-8")).hexdigest()[:16]

    @classmethod
    def _build_text(cls, entries: list[dict]) -> str:
        parts: list[str] = []
        for entry in entries[-cls._MAX_TEXT_ENTRIES :]:
            summary = str(entry.get("summary", "")).strip()
            if not summary:
                continue
            tool_name = entry.get("tool_name", "unknown")
            timestamp = entry.get("ts", "")
            repeats = int(entry.get("repeat_count", 1) or 1)
            repeat_suffix = f" x{repeats}" if repeats > 1 else ""
            parts.append(f"[{timestamp}] {tool_name}{repeat_suffix}\n{summary}")
        return "\n\n".join(parts)
