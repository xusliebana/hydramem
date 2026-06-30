"""Per-project calibration of SR-MKG weights.

Learns a logistic regression over the four SR-MKG components — base,
jaccard, type_boost, isolated — from the local ``srmkg_decisions`` table
and writes the result to ``~/.hydramem/projects/<p>/srmkg_weights.json``.

Pure NumPy + tiny gradient-descent optimiser, so we do not pull scikit-learn
into the default install. The objective is the standard L2-regularised
log-loss; weights remain interpretable because the feature space is the
same one the heuristic uses.

See ``docs/internal/future_work/learned-srmkg-weights.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from hydramem.core.logging import get_logger
from hydramem.telemetry.storage import fetch_srmkg_decisions
from hydramem.verification.srmkg import save_project_weights

logger = get_logger(__name__)

MIN_SAMPLES = 50  # below this we refuse to train
_FEATURES = ("base", "jaccard", "type_boost", "isolated")


@dataclass
class CalibrationReport:
    project: str
    n_train: int
    n_test: int
    train_loss: float
    auc: float
    weights: dict[str, float]
    intercept: float
    trained_at: str
    saved_path: str | None = None


def _sigmoid(x):
    import numpy as np

    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))


def _auc(y_true, y_score) -> float:
    """ROC-AUC via Mann–Whitney U. NumPy only."""
    import numpy as np

    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    n_pairs = pos.size * neg.size
    # Vectorised pairwise comparison; small enough for typical N (<10⁵ rows).
    diff = pos[:, None] - neg[None, :]
    wins = (diff > 0).sum() + 0.5 * (diff == 0).sum()
    return float(wins / n_pairs)


def calibrate(
    project: str = "default",
    *,
    min_samples: int = MIN_SAMPLES,
    test_fraction: float = 0.2,
    l2: float = 1.0,
    lr: float = 0.1,
    epochs: int = 500,
    seed: int = 0,
    save: bool = True,
) -> CalibrationReport:
    """Train a logistic regression over SR-MKG components and persist it.

    Raises ``RuntimeError`` if there are fewer than ``min_samples`` decisions
    or only one class is present in the training set — refusing to fit
    degenerate distributions is honesty, not a bug.
    """
    import numpy as np

    rows = fetch_srmkg_decisions(project=project)
    if len(rows) < min_samples:
        raise RuntimeError(
            f"calibrate-srmkg needs ≥{min_samples} decisions for project "
            f"'{project}', found {len(rows)}. Run more verifications first."
        )

    x = np.asarray(
        [[float(r.get(k) or 0.0) for k in _FEATURES] for r in rows],
        dtype=np.float64,
    )
    y = np.asarray([int(r.get("final_label") or 0) for r in rows], dtype=np.float64)

    if len(set(y.tolist())) < 2:
        raise RuntimeError(
            "calibrate-srmkg needs both accepted and rejected examples "
            f"in project '{project}' — only one class present."
        )

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(y))
    x, y = x[perm], y[perm]
    n_test = max(1, int(len(y) * test_fraction))
    x_test, y_test = x[:n_test], y[:n_test]
    x_train, y_train = x[n_test:], y[n_test:]

    # Plain GD on log-loss with L2. Tiny problem, no need for scipy/sklearn.
    w = np.zeros(x_train.shape[1], dtype=np.float64)
    b = 0.0
    n = len(y_train)
    train_loss = float("inf")
    for _ in range(epochs):
        z = x_train @ w + b
        p = _sigmoid(z)
        # log-loss + L2 (excludes intercept)
        eps = 1e-12
        loss = -np.mean(
            y_train * np.log(p + eps) + (1 - y_train) * np.log(1 - p + eps)
        ) + 0.5 * l2 * float(np.dot(w, w)) / max(n, 1)
        grad_w = (x_train.T @ (p - y_train)) / n + l2 * w / max(n, 1)
        grad_b = float(np.mean(p - y_train))
        w -= lr * grad_w
        b -= lr * grad_b
        train_loss = float(loss)

    weights = {feat: float(w[i]) for i, feat in enumerate(_FEATURES)}
    intercept = float(b)
    auc = _auc(y_test, _sigmoid(x_test @ w + b))

    payload = {
        "weights": weights,
        "intercept": intercept,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "train_loss": round(train_loss, 6),
        "auc": round(auc, 4),
        "l2": l2,
        "lr": lr,
        "epochs": epochs,
        "trained_at": datetime.now(UTC).isoformat(),
    }
    saved_path: str | None = None
    if save:
        path = save_project_weights(project, payload)
        saved_path = str(path)
        logger.info(
            "SR-MKG calibrated for project=%s n_train=%d auc=%.3f → %s",
            project,
            len(y_train),
            auc,
            saved_path,
        )

    return CalibrationReport(
        project=project,
        n_train=int(len(y_train)),
        n_test=int(len(y_test)),
        train_loss=train_loss,
        auc=auc,
        weights=weights,
        intercept=intercept,
        trained_at=payload["trained_at"],
        saved_path=saved_path,
    )
