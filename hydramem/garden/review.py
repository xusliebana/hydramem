"""Human-in-the-loop prune review store + golden-dataset persistence.

This is the storage layer for the *active-learning* loop around the GNN
spurious-edge pruner. When enabled, the Night Gardener routes a sample of
borderline prune candidates (edges whose spuriousness is near the decision
threshold — **uncertainty sampling**, Settles 2009) into a local review queue.
A human labels each as ``prune`` or ``keep`` via ``hydramem review``; the
labelled rows become a **golden dataset** that
:func:`hydramem.garden.prune_trainer.train_pruner` turns into a learned,
supervised edge scorer (weak supervision → graph denoising, cf. NRGNN /
Cleanlab / Confident Learning).

Everything stays on disk under the HydraMem home directory — no data leaves the
machine. Paths are injectable so tests never touch real state.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from hydramem.core.config import hydramem_home
from hydramem.core.logging import get_logger

logger = get_logger(__name__)

#: Canonical, ordered feature names. The same vector is used at capture,
#: training, and scoring time so the learned weights stay interpretable and
#: consistent (see ``hydramem/gnn_prune.py::edge_feature_vector``).
PRUNE_FEATURES: tuple[str, ...] = (
    "heuristic",   # heuristic spuriousness score (0..1)
    "jaccard",     # |common| / |union| of neighbours
    "common",      # common neighbours / max(deg_u, deg_v)
    "deg_u",       # source degree, normalised by the graph max
    "deg_v",       # target degree, normalised by the graph max
    "hub",         # 1.0 if either endpoint is a hub (deg > 20)
)

_VALID_LABELS = ("prune", "keep")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prune_reviews (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    project       TEXT    NOT NULL,
    from_id       TEXT    NOT NULL,
    to_id         TEXT    NOT NULL,
    from_name     TEXT,
    to_name       TEXT,
    rel_type      TEXT,
    spuriousness  REAL,
    features_json TEXT    DEFAULT '{}',
    source        TEXT,
    status        TEXT    DEFAULT 'pending',
    label         TEXT,
    reviewed_at   TEXT,
    UNIQUE(project, from_id, to_id)
);
CREATE INDEX IF NOT EXISTS idx_prune_reviews_project_status
    ON prune_reviews(project, status);
"""


def prune_weights_path(project: str = "default") -> Path:
    """Per-project path for the learned pruner weights JSON."""
    return hydramem_home() / "projects" / project / "prune_weights.json"


def load_prune_weights(project: str = "default") -> dict | None:
    """Load learned pruner weights for *project*, or ``None`` if absent/invalid."""
    path = prune_weights_path(project)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_prune_weights failed (%s)", exc)
        return None


def save_prune_weights(project: str, payload: dict) -> Path:
    """Persist learned pruner weights for *project*; returns the path."""
    path = prune_weights_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path


class PruneReviewStore:
    """SQLite-backed queue of prune candidates awaiting human labelling.

    The DB path is injectable (defaults to ``<hydramem_home>/prune_reviews.db``)
    so tests can point it at a temp directory.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = Path(db_path) if db_path else (hydramem_home() / "prune_reviews.db")
        self._init_db()

    def _init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    # ── Write ──────────────────────────────────────────────────────────────

    def add_candidate(
        self,
        *,
        project: str,
        from_id: str,
        to_id: str,
        from_name: str = "",
        to_name: str = "",
        rel_type: str = "",
        spuriousness: float = 0.0,
        features: dict | None = None,
        source: str = "gnn",
    ) -> bool:
        """Queue one prune candidate. Returns ``True`` if newly inserted.

        De-duplicated on ``(project, from_id, to_id)`` — re-capturing an edge
        that is still pending is a no-op (idempotent across cycles).
        """
        try:
            with sqlite3.connect(self._path) as conn:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO prune_reviews (
                        ts, project, from_id, to_id, from_name, to_name,
                        rel_type, spuriousness, features_json, source, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')""",
                    (
                        datetime.now(UTC).isoformat(), project, from_id, to_id,
                        from_name, to_name, rel_type, float(spuriousness),
                        json.dumps(features or {}), source,
                    ),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as exc:  # noqa: BLE001
            logger.debug("add_candidate failed: %s", exc)
            return False

    def label(self, review_id: int, label: str) -> bool:
        """Apply a human label (``prune`` | ``keep``) to a queued candidate."""
        if label not in _VALID_LABELS:
            raise ValueError(f"label must be one of {_VALID_LABELS}, got {label!r}")
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                """UPDATE prune_reviews
                   SET label = ?, status = 'labeled', reviewed_at = ?
                   WHERE id = ?""",
                (label, datetime.now(UTC).isoformat(), int(review_id)),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Read ───────────────────────────────────────────────────────────────

    def pending(self, project: str = "default", limit: int = 50) -> list[dict]:
        """Return up to *limit* unlabelled candidates (most-uncertain first).

        "Uncertain" = closest to the GNN decision threshold (0.65) — the most
        informative examples to label in an active-learning loop.
        """
        return self._select(
            "WHERE project = ? AND status = 'pending' "
            "ORDER BY ABS(spuriousness - 0.65) ASC, id ASC LIMIT ?",
            (project, int(limit)),
        )

    def labeled(self, project: str = "default") -> list[dict]:
        """Return all labelled rows for *project* (the golden dataset)."""
        return self._select(
            "WHERE project = ? AND status = 'labeled' ORDER BY id ASC", (project,)
        )

    def stats(self, project: str = "default") -> dict:
        """Counts for `garden-status` / the review CLI."""
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT
                    COUNT(*)                                          AS total,
                    SUM(status = 'pending')                           AS pending,
                    SUM(status = 'labeled')                           AS labeled,
                    SUM(label = 'prune')                              AS prune,
                    SUM(label = 'keep')                               AS keep
                   FROM prune_reviews WHERE project = ?""",
                (project,),
            ).fetchone()
        return {k: int(row[k] or 0) for k in ("total", "pending", "labeled", "prune", "keep")}

    def export_jsonl(self, project: str, path: str | Path) -> int:
        """Write the labelled golden dataset to *path* as JSONL. Returns rows."""
        rows = self.labeled(project)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({
                    "from_id": r["from_id"], "to_id": r["to_id"],
                    "from_name": r["from_name"], "to_name": r["to_name"],
                    "features": r["features"], "label": r["label"],
                }) + "\n")
        return len(rows)

    def _select(self, where_sql: str, params: tuple) -> list[dict]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM prune_reviews {where_sql}", params
            ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            try:
                d["features"] = json.loads(d.pop("features_json") or "{}")
            except Exception:  # noqa: BLE001
                d["features"] = {}
            out.append(d)
        return out
