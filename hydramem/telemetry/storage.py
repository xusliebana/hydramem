"""SQLite-backed telemetry storage.

All data stays in ~/.hydramem/metrics.db – nothing is sent anywhere
unless the user explicitly opts in via `hydramem telemetry --send`.

Note: ``chunks_rejected_srmkg`` is kept as the column name for backward
compatibility with v0.1.x databases, but in the chunks-prefilter path it
actually counts *vector-similarity* rejections (see
``hydramem/verification/pipeline.py::verify_chunks``). The CLI labels reflect
the correct semantics.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hydramem.core.config import hydramem_home

_log = logging.getLogger(__name__)

DB_DIR: Path = hydramem_home()
DB_PATH: Path = DB_DIR / "metrics.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                      TEXT    NOT NULL,
    project                 TEXT,
    tool_name               TEXT,
    session_id              TEXT,
    llm_preset              TEXT,
    tokens_injected         INTEGER DEFAULT 0,
    tokens_baseline         INTEGER DEFAULT 0,
    vog_score               REAL    DEFAULT 0.0,
    chunks_total            INTEGER DEFAULT 0,
    chunks_rejected_srmkg   INTEGER DEFAULT 0,
    chunks_rejected_vog     INTEGER DEFAULT 0,
    cross_project_hit       INTEGER DEFAULT 0,
    latency_ms              INTEGER DEFAULT 0,
    was_hallucination_blocked INTEGER DEFAULT 0,
    metadata_json           TEXT    DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS srmkg_decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    project       TEXT,
    relation_type TEXT,
    base          REAL    DEFAULT 0.0,
    jaccard       REAL    DEFAULT 0.0,
    type_boost    REAL    DEFAULT 0.0,
    isolated      REAL    DEFAULT 0.0,
    score         REAL    DEFAULT 0.0,
    final_label   INTEGER,
    source        TEXT
);

CREATE INDEX IF NOT EXISTS idx_srmkg_project ON srmkg_decisions(project);
"""


_DB_TIMEOUT = 30  # seconds to wait for the SQLite lock before raising


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a connection with WAL journal mode and a generous busy timeout.

    WAL (Write-Ahead Logging) allows concurrent readers and a single writer
    without blocking — crucial when multiple ``hydramem`` processes share one
    ``metrics.db``.
    """
    conn = sqlite3.connect(path, timeout=_DB_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30 s retry at the SQLite level
    return conn


_init_done: bool = False


def init_db() -> None:
    """Create ~/.hydramem/metrics.db and the events table if needed.

    Uses an idempotent CREATE-IF-NOT-EXISTS pattern with WAL mode so concurrent
    processes don't deadlock.
    """
    global _init_done  # noqa: PLW0603
    if _init_done:
        return
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    _init_done = True


def log_event(
    *,
    project: str = "default",
    tool_name: str = "",
    session_id: str = "",
    llm_preset: str = "",
    tokens_injected: int = 0,
    tokens_baseline: int = 0,
    vog_score: float = 0.0,
    chunks_total: int = 0,
    chunks_rejected_srmkg: int = 0,
    chunks_rejected_vog: int = 0,
    cross_project_hit: int = 0,
    latency_ms: int = 0,
    was_hallucination_blocked: int = 0,
    metadata: dict | None = None,
) -> None:
    """Insert one telemetry row. Silently swallows errors so it never breaks the main flow."""
    try:
        init_db()
        ts = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata or {})
        with _connect() as conn:
            conn.execute(
                """INSERT INTO events (
                    ts, project, tool_name, session_id, llm_preset,
                    tokens_injected, tokens_baseline, vog_score,
                    chunks_total, chunks_rejected_srmkg, chunks_rejected_vog,
                    cross_project_hit, latency_ms, was_hallucination_blocked,
                    metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts,
                    project,
                    tool_name,
                    session_id,
                    llm_preset,
                    tokens_injected,
                    tokens_baseline,
                    vog_score,
                    chunks_total,
                    chunks_rejected_srmkg,
                    chunks_rejected_vog,
                    cross_project_hit,
                    latency_ms,
                    was_hallucination_blocked,
                    meta_json,
                ),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        # Telemetry must never crash the application. Log at WARNING so
        # operators notice when events are being dropped (e.g. filesystem
        # full, permissions error) without requiring DEBUG verbosity.
        _log.warning("telemetry log_event failed: %s", exc)


def query_stats(days: int = 7, project: str | None = None) -> dict:
    """Return aggregated stats for the last *days* days.

    If *project* is given, only events for that project are included.
    """
    init_db()
    sql = """
        SELECT
            COUNT(*)                             AS total_calls,
            COALESCE(SUM(tokens_injected), 0)    AS total_injected,
            COALESCE(SUM(tokens_baseline), 0)    AS total_baseline,
            COALESCE(AVG(vog_score), 0.0)        AS avg_vog,
            COALESCE(SUM(chunks_rejected_srmkg), 0) AS rejected_srmkg,
            COALESCE(SUM(chunks_rejected_vog), 0)   AS rejected_vog,
            COALESCE(SUM(cross_project_hit), 0)  AS cross_hits,
            COALESCE(SUM(was_hallucination_blocked), 0) AS hallucinations_blocked,
            GROUP_CONCAT(DISTINCT project)       AS projects,
            MIN(ts)                              AS period_start,
            MAX(ts)                              AS period_end
        FROM events
        WHERE ts >= datetime('now', :delta)
    """
    params: dict[str, str] = {"delta": f"-{days} days"}
    if project:
        sql += " AND project = :project"
        params["project"] = project
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def list_projects() -> list[str]:
    """Return a sorted list of distinct project names from the events table."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT project FROM events WHERE project IS NOT NULL ORDER BY project"
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# SR-MKG decision log (training set for learned weights)
# ---------------------------------------------------------------------------


def log_srmkg_decision(
    *,
    project: str = "default",
    relation_type: str = "",
    base: float = 0.0,
    jaccard: float = 0.0,
    type_boost: float = 0.0,
    isolated: float = 0.0,
    score: float = 0.0,
    final_label: int = 0,
    source: str = "srmkg",
) -> None:
    """Record one SR-MKG decision for later calibration. Best-effort, never raises."""
    try:
        init_db()
        ts = datetime.now(UTC).isoformat()
        with _connect() as conn:
            conn.execute(
                """INSERT INTO srmkg_decisions (
                    ts, project, relation_type,
                    base, jaccard, type_boost, isolated,
                    score, final_label, source
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts,
                    project,
                    relation_type,
                    float(base),
                    float(jaccard),
                    float(type_boost),
                    float(isolated),
                    float(score),
                    int(final_label),
                    source,
                ),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        _log.debug("telemetry log_srmkg_decision failed: %s", exc)


def fetch_srmkg_decisions(project: str | None = None) -> list[dict]:
    """Return all SR-MKG decisions for *project* (or all projects)."""
    init_db()
    sql = "SELECT * FROM srmkg_decisions"
    params: tuple = ()
    if project:
        sql += " WHERE project = ?"
        params = (project,)
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# Retrieval-reuse signal (Night Gardener consolidation input)
# ---------------------------------------------------------------------------


def _days_since_iso(ts_iso: str, now: datetime) -> float:
    try:
        then = datetime.fromisoformat(ts_iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=UTC)
        return max(0.0, (now - then).total_seconds() / 86400.0)
    except Exception:  # noqa: BLE001
        return 0.0


def entity_reuse(project: str = "default", window_days: int = 30) -> list[dict]:
    """Per-entity retrieval-reuse signal derived from telemetry events.

    Reads the entity ids recorded in each tool call's ``metadata_json``
    (``{"entities": [...]}``) within the last *window_days* for *project* and
    aggregates, per entity:

      - ``sessions_touched`` — distinct sessions that retrieved the entity
      - ``total_touches``    — total retrievals (informational)
      - ``days_since``       — days since the entity was last retrieved

    Uses only data already stored locally (no new collection). Best-effort:
    returns ``[]`` on any error so the Night Gardener never breaks.
    """
    try:
        init_db()
        sql = (
            "SELECT session_id, ts, metadata_json FROM events "
            "WHERE project = ? AND ts >= datetime('now', ?)"
        )
        with _connect() as conn:
            rows = conn.execute(sql, (project, f"-{int(window_days)} days")).fetchall()
    except Exception as exc:  # noqa: BLE001
        _log.debug("entity_reuse query failed: %s", exc)
        return []

    agg: dict[str, dict] = {}
    for session_id, ts, meta in rows:
        try:
            entities = (json.loads(meta or "{}") or {}).get("entities") or []
        except Exception:  # noqa: BLE001
            continue
        for eid in entities:
            if not eid:
                continue
            rec = agg.get(eid)
            if rec is None:
                rec = {"sessions": set(), "total": 0, "last": ts}
                agg[eid] = rec
            rec["sessions"].add(session_id or "")
            rec["total"] += 1
            if ts and ts > rec["last"]:
                rec["last"] = ts

    now = datetime.now(UTC)
    return [
        {
            "entity_id": eid,
            "sessions_touched": len(rec["sessions"]),
            "total_touches": rec["total"],
            "days_since": _days_since_iso(rec["last"], now),
        }
        for eid, rec in agg.items()
    ]
