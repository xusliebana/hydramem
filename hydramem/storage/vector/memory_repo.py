"""In-memory vector repository — pure-Python fallback (no persistence)."""

from __future__ import annotations

import math

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk

logger = get_logger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorRepository:
    """Ephemeral vector store backed by a simple list + cosine similarity scan.

    Suitable for testing and single-session use.  Does not persist across restarts.
    """

    def __init__(self) -> None:
        self._store: list[dict] = []  # [{chunk, vector}]
        logger.info("InMemoryVectorRepository: using in-memory fallback")

    def add(self, chunk: Chunk, embedding: list[float]) -> None:
        self._store.append({"chunk": chunk, "vector": embedding})

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        project: str = "default",
    ) -> list[Chunk]:
        scored = [
            (item["chunk"], _cosine_similarity(query_vector, item["vector"]))
            for item in self._store
            if item["chunk"].project == project
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for chunk, sim in scored[:k]:
            chunk.similarity = sim
            results.append(chunk)
        return results

    def get_all_raw(self) -> list[dict]:
        return [
            {
                "id": item["chunk"].id,
                "text": item["chunk"].text,
                "source": item["chunk"].source,
                "project": item["chunk"].project,
            }
            for item in self._store
        ]
