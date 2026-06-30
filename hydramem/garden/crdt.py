"""CRDT-style merge for HydraMem session repositories.

The Night Gardener consumes the local ``sessions.json`` file. When a user
runs HydraMem on multiple machines and wants the gardener on machine *A* to
benefit from sessions captured on machine *B*, we need a deterministic merge
that survives concurrent writes without a central coordinator.

We model each session as an ``LWW-element-set`` keyed by ``session_id`` /
``project``, with per-entry deduplication by fingerprint and a "highest wins"
rule for ``repeat_count`` so observations from both machines accumulate.

This is intentionally tiny — no vector clocks, no causal history — because
sessions are append-only and entries are idempotent. If two replicas saw the
same observation, fingerprint-equality dedupes them; if they saw different
observations, both survive.
"""
from __future__ import annotations

import json
from pathlib import Path

from hydramem.garden.repository import SessionRepository


def merge_sessions(local: list[dict], remote: list[dict]) -> list[dict]:
    """Return the LWW union of *local* and *remote* session lists.

    The output is normalised through ``SessionRepository._normalise_session``
    which already handles fingerprint dedup, repeat-count accumulation, and
    text rebuilding.
    """
    by_key: dict[tuple[str, str], dict] = {}

    for source in (local, remote):
        for session in source:
            key = (session.get("project", "default"), session.get("session_id") or session.get("id") or "")
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = SessionRepository._normalise_session(session)
            else:
                by_key[key] = SessionRepository._merge_sessions(
                    existing, SessionRepository._normalise_session(session)
                )

    merged = sorted(
        by_key.values(),
        key=lambda item: item.get("updated_at") or item.get("created_at") or "",
    )
    return merged


def merge_session_files(
    local_path: str | Path,
    remote_path: str | Path,
    *,
    out_path: str | Path | None = None,
) -> dict:
    """Merge two ``sessions.json`` files on disk. Returns a small summary."""
    local = _load(Path(local_path))
    remote = _load(Path(remote_path))
    merged = merge_sessions(local, remote)

    target = Path(out_path) if out_path is not None else Path(local_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2, default=str))

    return {
        "local_sessions": len(local),
        "remote_sessions": len(remote),
        "merged_sessions": len(merged),
        "wrote": str(target),
    }


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []
