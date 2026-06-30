"""Typed retrieval planner — classify a query, pick a retrieval strategy.

A tiny **zero-shot** classifier (cosine of the query embedding against per-class
prompt centroids) chooses a retrieval strategy with no training data and no LLM
call (~ a handful of embed calls, cached). Below a confidence threshold the
planner returns ``None`` so the caller falls through to the configured default —
honesty contract: a low-confidence guess is never dressed up as certainty.

``hydra_search`` consumes ``traversal``, ``top_k``, ``skip_vog`` and ``bm25``.
Temporal ``as_of`` routing is a documented follow-up (see
``docs/internal/future_work/typed-retrieval-planner.md``); the temporal class still
selects a sensible default strategy today.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RetrievalStrategy:
    """A concrete retrieval plan chosen for a query."""

    name: str
    traversal: str = "bfs"          # bfs | ppr | hybrid
    top_k: int = 10
    skip_vog: bool = False          # cheap path for factoid lookups
    bm25: bool = True               # lexical arm on/off
    confidence: float = 0.0


class QueryPlanner(ABC):
    """Strategy selector contract (DIP — callers depend on this, not the impl)."""

    @abstractmethod
    def plan(
        self, query: str, *, default_top_k: int = 10
    ) -> RetrievalStrategy | None:
        """Return a strategy, or ``None`` to fall through to the default."""


# Natural-language prototypes each query is matched against (zero-shot).
_CLASS_PROMPTS: dict[str, list[str]] = {
    "factoid": [
        "what is", "who is", "define this term",
        "a short factual question with a single direct answer",
    ],
    "multi_hop": [
        "how does one thing relate to another through an intermediate",
        "a multi-hop reasoning question spanning several documents",
        "connect facts across multiple sources to answer",
    ],
    "temporal": [
        "what was true at a particular point in time",
        "the state before or after a given date",
        "how something changed over time",
    ],
    "comparative": [
        "compare two things", "the difference between X and Y",
        "which of two options is better and why",
    ],
}

# Map each class to a retrieval strategy (see module docstring for the levers).
_CLASS_STRATEGY: dict[str, dict] = {
    "factoid": {"traversal": "bfs", "skip_vog": True, "bm25": True},
    "multi_hop": {"traversal": "hybrid", "skip_vog": False, "bm25": True},
    "temporal": {"traversal": "bfs", "skip_vog": False, "bm25": True},
    "comparative": {"traversal": "ppr", "skip_vog": False, "bm25": True},
}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _centroid(vecs: list[list[float]]) -> list[float]:
    if not vecs:
        return []
    n = len(vecs)
    dim = len(vecs[0])
    return [sum(v[i] for v in vecs) / n for i in range(dim)]


class ZeroShotPlanner(QueryPlanner):
    """Cosine-prototype query classifier over the existing embedder.

    Class centroids are embedded once and cached. The chosen class is the
    highest-cosine prototype; if that similarity is below *threshold* the
    planner returns ``None`` (fall through to the default strategy).
    """

    def __init__(self, embedder, *, threshold: float = 0.15) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._proto: dict[str, list[float]] | None = None

    def _ensure_prototypes(self) -> None:
        if self._proto is not None:
            return
        proto: dict[str, list[float]] = {}
        for cls, prompts in _CLASS_PROMPTS.items():
            proto[cls] = _centroid([self._embedder.embed(p) for p in prompts])
        self._proto = proto

    def plan(
        self, query: str, *, default_top_k: int = 10
    ) -> RetrievalStrategy | None:
        try:
            self._ensure_prototypes()
            qv = self._embedder.embed(query, is_query=True)
        except Exception:  # noqa: BLE001
            return None
        assert self._proto is not None
        best_cls: str | None = None
        best_sim = -1.0
        for cls, pv in self._proto.items():
            sim = _cosine(qv, pv)
            if sim > best_sim:
                best_cls, best_sim = cls, sim
        if best_cls is None or best_sim < self._threshold:
            return None
        spec = _CLASS_STRATEGY[best_cls]
        return RetrievalStrategy(
            name=best_cls,
            top_k=default_top_k,
            confidence=round(best_sim, 4),
            **spec,
        )
