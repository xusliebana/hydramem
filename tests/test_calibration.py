"""Tests for SR-MKG learned-weights calibration."""

from __future__ import annotations

import json

import pytest

from hydramem.core.types import Relation
from hydramem.verification import calibration as cal_mod
from hydramem.verification import srmkg as srmkg_mod
from hydramem.verification.srmkg import SRMKGScorer


@pytest.fixture
def sandbox(tmp_path, monkeypatch, tmp_metrics_db):
    """Redirect both telemetry DB and weights dir to a tmp location."""
    weights_dir = tmp_path / "projects"
    monkeypatch.setattr(srmkg_mod, "WEIGHTS_DIR", weights_dir)
    yield weights_dir


def _seed_decisions(n_pos: int, n_neg: int, project: str = "default") -> None:
    from hydramem.telemetry.storage import log_srmkg_decision

    # Positive examples: high jaccard / type_boost, low isolated.
    for _ in range(n_pos):
        log_srmkg_decision(
            project=project,
            relation_type="causes",
            base=0.8,
            jaccard=0.7,
            type_boost=1.0,
            isolated=0.0,
            score=0.85,
            final_label=1,
            source="vog",
        )
    # Negative examples: low everything, high isolated.
    for _ in range(n_neg):
        log_srmkg_decision(
            project=project,
            relation_type="related_to",
            base=0.2,
            jaccard=0.05,
            type_boost=0.0,
            isolated=1.0,
            score=0.1,
            final_label=0,
            source="srmkg",
        )


def test_calibrate_refuses_below_min_samples(sandbox):
    _seed_decisions(2, 2, project="default")
    with pytest.raises(RuntimeError):
        cal_mod.calibrate(project="default", min_samples=50)


def test_calibrate_refuses_single_class(sandbox):
    _seed_decisions(60, 0, project="solo")
    with pytest.raises(RuntimeError):
        cal_mod.calibrate(project="solo", min_samples=10)


def test_calibrate_writes_weights_and_improves_separation(sandbox):
    _seed_decisions(40, 40, project="default")
    report = cal_mod.calibrate(project="default", min_samples=50, epochs=300, lr=0.2)
    assert report.saved_path is not None
    payload = json.loads((sandbox / "default" / "srmkg_weights.json").read_text())
    assert set(payload["weights"].keys()) == {"base", "jaccard", "type_boost", "isolated"}
    # With cleanly separated classes the AUC should be ≈ 1.0.
    assert report.auc >= 0.95


def test_scorer_uses_learned_weights_when_present(sandbox):
    _seed_decisions(40, 40, project="default")
    cal_mod.calibrate(project="default", min_samples=50, epochs=300, lr=0.2)

    scorer = SRMKGScorer(project="default")
    assert scorer.is_calibrated

    # A clearly positive-looking relation should score well above 0.5.
    pos = Relation(from_entity="a", to_entity="b", relation_type="causes", confidence=0.9)
    pos_score = scorer.score(pos, common_neighbors=5, degree_from=6, degree_to=6)
    assert pos_score >= 0.5

    # A clearly negative-looking, isolated relation should score below 0.5.
    neg = Relation(from_entity="x", to_entity="y", relation_type="related_to", confidence=0.1)
    neg_score = scorer.score(neg, common_neighbors=0, degree_from=0, degree_to=0)
    assert neg_score < pos_score
