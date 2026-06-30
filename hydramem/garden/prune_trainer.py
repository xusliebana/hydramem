"""Train a learned spurious-edge scorer from the human-labelled golden dataset.

Mirrors :mod:`hydramem.verification.calibration`: a pure-NumPy, L2-regularised
logistic regression over the shared ``PRUNE_FEATURES`` — so no scikit-learn or
torch is pulled into the default install, and the weights stay interpretable.
The result is saved to ``~/.hydramem/projects/<p>/prune_weights.json`` and is
picked up automatically by :class:`hydramem.gnn_prune.GNNPruner` (the
``learned`` backend).

Honest by construction: it refuses to fit with too few samples or a single
class (returning a degenerate model would be dishonest, not helpful).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from hydramem.core.logging import get_logger
from hydramem.garden.review import PRUNE_FEATURES, PruneReviewStore, save_prune_weights

logger = get_logger(__name__)

MIN_SAMPLES = 20  # below this we refuse to train


@dataclass
class PruneTrainReport:
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
    """ROC-AUC via Mann–Whitney U (NumPy only)."""
    import numpy as np

    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    diff = pos[:, None] - neg[None, :]
    wins = (diff > 0).sum() + 0.5 * (diff == 0).sum()
    return float(wins / (pos.size * neg.size))


def train_pruner(
    project: str = "default",
    *,
    store: PruneReviewStore | None = None,
    min_samples: int = MIN_SAMPLES,
    test_fraction: float = 0.2,
    l2: float = 1.0,
    lr: float = 0.1,
    epochs: int = 500,
    seed: int = 0,
    save: bool = True,
) -> PruneTrainReport:
    """Fit a logistic edge scorer from the labelled golden dataset and persist it.

    Raises ``RuntimeError`` if there are fewer than ``min_samples`` labels or a
    single class is present.
    """
    import numpy as np

    from hydramem.gnn_prune import edge_feature_vector

    store = store or PruneReviewStore()
    rows = store.labeled(project)
    if len(rows) < min_samples:
        raise RuntimeError(
            f"train-pruner needs ≥{min_samples} labelled examples for project "
            f"'{project}', found {len(rows)}. Label more with `hydramem review`."
        )

    x = np.asarray(
        [edge_feature_vector(r.get("features") or {}) for r in rows], dtype=np.float64
    )
    y = np.asarray(
        [1.0 if r.get("label") == "prune" else 0.0 for r in rows], dtype=np.float64
    )
    if len(set(y.tolist())) < 2:
        raise RuntimeError(
            f"train-pruner needs both 'prune' and 'keep' labels in project "
            f"'{project}' — only one class present."
        )

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(y))
    x, y = x[perm], y[perm]
    n_test = max(1, int(len(y) * test_fraction))
    x_test, y_test = x[:n_test], y[:n_test]
    x_train, y_train = x[n_test:], y[n_test:]

    w = np.zeros(x_train.shape[1], dtype=np.float64)
    b = 0.0
    n = max(len(y_train), 1)
    train_loss = float("inf")
    for _ in range(epochs):
        z = x_train @ w + b
        p = _sigmoid(z)
        eps = 1e-12
        loss = (
            -np.mean(y_train * np.log(p + eps) + (1 - y_train) * np.log(1 - p + eps))
            + 0.5 * l2 * float(np.dot(w, w)) / n
        )
        grad_w = (x_train.T @ (p - y_train)) / n + l2 * w / n
        grad_b = float(np.mean(p - y_train))
        w -= lr * grad_w
        b -= lr * grad_b
        train_loss = float(loss)

    weights = {feat: float(w[i]) for i, feat in enumerate(PRUNE_FEATURES)}
    intercept = float(b)
    auc = _auc(y_test, _sigmoid(x_test @ w + b))

    payload = {
        "weights": weights,
        "intercept": intercept,
        "features": list(PRUNE_FEATURES),
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
        saved_path = str(save_prune_weights(project, payload))
        logger.info(
            "Pruner trained for project=%s n_train=%d auc=%.3f → %s",
            project, len(y_train), auc, saved_path,
        )

    return PruneTrainReport(
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
