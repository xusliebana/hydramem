"""SR-MKG topological scorer — fast, LLM-free confidence estimation.

The default weights below are heuristic baselines derived from internal
experiments on the HydraMem dogfood corpus (see ``docs/benchmarks.md``).
They are exposed in ``hydramem/core/config.py`` so operators can tune them
without forking the code, and replaced by a per-project learned
calibration via :mod:`tools.verification.calibration`.

When a project has a trained weights file at
``~/.hydramem/projects/<project>/srmkg_weights.json``, :class:`SRMKGScorer`
loads it transparently — the API contract is unchanged.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from hydramem.core.types import Relation
from hydramem.verification.base import VerificationResult

_HIGH = 0.7
_LOW = 0.3
_DEFAULT_W_BASE = 0.4
_DEFAULT_W_JACCARD = 0.4
_DEFAULT_W_TYPE_BOOST = 0.05
_DEFAULT_PENALTY_ISOLATED = 0.3

WEIGHTS_DIR = Path.home() / ".hydramem" / "projects"


@dataclass
class ScoreBreakdown:
    """Raw component contributions for one SR-MKG scoring call.

    Audit-friendly: every persisted field is also exposed back to callers
    so the calibration layer can train on the same numbers SR-MKG produced.
    """

    base: float
    jaccard: float
    type_boost: float
    isolated: float
    score: float


def _weights_path(project: str) -> Path:
    return WEIGHTS_DIR / project / "srmkg_weights.json"


def load_project_weights(project: str) -> dict | None:
    """Return ``{"weights": {...}, "intercept": float, ...}`` or ``None``."""
    path = _weights_path(project)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def save_project_weights(project: str, payload: dict) -> Path:
    """Persist a calibration result for *project*."""
    path = _weights_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path


class SRMKGScorer:
    """Scalable Relation Mining with Knowledge Graphs — topological filter.

    Computes a confidence score purely from graph topology.
    No LLM call is made; this is the cheap first gate.

    Score formula (heuristic mode)::

        score = w_base * base
              + w_jaccard * jaccard
              + w_type_boost * type_boost
              - penalty_isolated * isolated_indicator

    When a project provides a learned weights file, the score becomes
    a sigmoid of a logistic regression over the same components — same
    interpretability, calibrated to the local distribution.
    """

    def __init__(
        self,
        threshold_accept: float = _HIGH,
        threshold_reject: float = _LOW,
        weight_base: float = _DEFAULT_W_BASE,
        weight_jaccard: float = _DEFAULT_W_JACCARD,
        weight_type_boost: float = _DEFAULT_W_TYPE_BOOST,
        penalty_isolated: float = _DEFAULT_PENALTY_ISOLATED,
        project: str | None = None,
    ) -> None:
        self._accept = threshold_accept
        self._reject = threshold_reject
        self._w_base = weight_base
        self._w_jaccard = weight_jaccard
        self._w_type_boost = weight_type_boost
        self._penalty_isolated = penalty_isolated
        self._project = project
        self._learned: dict | None = load_project_weights(project) if project else None

    @property
    def is_calibrated(self) -> bool:
        return self._learned is not None

    @property
    def calibration_metadata(self) -> dict:
        return dict(self._learned or {})

    def _components(
        self,
        relation: Relation,
        common_neighbors: int,
        degree_from: int,
        degree_to: int,
    ) -> tuple[float, float, float, float]:
        total = max(degree_from + degree_to - common_neighbors, 1)
        jaccard = common_neighbors / total
        isolated = 1.0 if (degree_from == 0 or degree_to == 0) else 0.0
        type_boost = 1.0 if relation.relation_type not in ("related_to", "unknown") else 0.0
        base = relation.confidence if relation.confidence > 0.0 else 0.5
        return base, jaccard, type_boost, isolated

    def score(
        self,
        relation: Relation,
        common_neighbors: int = 0,
        degree_from: int = 1,
        degree_to: int = 1,
    ) -> float:
        return self.score_with_breakdown(relation, common_neighbors, degree_from, degree_to).score

    def score_with_breakdown(
        self,
        relation: Relation,
        common_neighbors: int = 0,
        degree_from: int = 1,
        degree_to: int = 1,
    ) -> ScoreBreakdown:
        """Score *relation* and return both the final score and components."""
        base, jaccard, type_boost, isolated = self._components(
            relation, common_neighbors, degree_from, degree_to
        )

        if self._learned:
            w = self._learned.get("weights") or {}
            intercept = float(self._learned.get("intercept", 0.0))
            logit = (
                float(w.get("base", 0.0)) * base
                + float(w.get("jaccard", 0.0)) * jaccard
                + float(w.get("type_boost", 0.0)) * type_boost
                + float(w.get("isolated", 0.0)) * isolated
                + intercept
            )
            # Numerically stable sigmoid.
            if logit >= 0:
                z = math.exp(-logit)
                score = 1.0 / (1.0 + z)
            else:
                z = math.exp(logit)
                score = z / (1.0 + z)
        else:
            named = self._w_type_boost * type_boost
            penalty = self._penalty_isolated * isolated
            raw = base * self._w_base + jaccard * self._w_jaccard + named - penalty
            score = max(0.0, min(1.0, raw))

        return ScoreBreakdown(
            base=round(base, 4),
            jaccard=round(jaccard, 4),
            type_boost=round(type_boost, 4),
            isolated=round(isolated, 4),
            score=round(score, 4),
        )

    def verify(
        self,
        relation: Relation,
        common_neighbors: int = 0,
        degree_from: int = 1,
        degree_to: int = 1,
    ) -> VerificationResult:
        breakdown = self.score_with_breakdown(relation, common_neighbors, degree_from, degree_to)
        s = breakdown.score
        if s >= self._accept:
            result = VerificationResult(accepted=True, score=s, level="srmkg_high")
        elif s < self._reject:
            result = VerificationResult(accepted=False, score=s, level="srmkg_low")
        else:
            result = VerificationResult(accepted=False, score=s, level="srmkg_borderline")
        # Attach the breakdown so the pipeline can log the training signal.
        result.breakdown = breakdown  # type: ignore[attr-defined]
        return result
