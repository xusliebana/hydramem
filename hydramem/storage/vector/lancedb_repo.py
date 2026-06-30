"""LanceDB vector repository — embedded, serverless, persistent."""

from __future__ import annotations

from typing import Any

from hydramem.core.logging import get_logger
from hydramem.core.types import Chunk

logger = get_logger(__name__)


def _build_schema(dim: int) -> Any:
    import pyarrow as pa  # type: ignore

    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("source", pa.string()),
            pa.field("chunk_idx", pa.int64()),
            pa.field("doc_id", pa.string()),
            pa.field("project", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


class LanceDBVectorRepository:
    """Persistent vector store backed by LanceDB."""

    def __init__(self, path: str, dim: int = 384) -> None:
        import lancedb  # type: ignore

        self._dim = dim
        db = lancedb.connect(path)
        schema = _build_schema(dim)
        try:
            self._table = db.open_table("chunks")
        except Exception:  # noqa: BLE001 — table does not exist yet
            self._table = db.create_table("chunks", schema=schema)
        logger.info("LanceDBVectorRepository: connected @ %s", path)

    def add(self, chunk: Chunk, embedding: list[float]) -> None:
        row = {
            "id": chunk.id,
            "text": chunk.text,
            "source": chunk.source,
            "chunk_idx": chunk.chunk_idx,
            "doc_id": chunk.doc_id,
            "project": chunk.project,
            "vector": [float(x) for x in embedding],
        }
        try:
            self._table.add([row])
        except Exception as exc:
            logger.debug("LanceDBVectorRepository.add: %s", exc)

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        project: str = "default",
    ) -> list[Chunk]:
        try:
            rows = (
                self._table.search(query_vector)
                .limit(k * 3)  # over-fetch; filter by project below
                .to_list()
            )
            results = []
            for row in rows:
                if row.get("project") == project:
                    results.append(
                        Chunk(
                            id=row["id"],
                            text=row["text"],
                            source=row["source"],
                            chunk_idx=row.get("chunk_idx", 0),
                            doc_id=row.get("doc_id", ""),
                            project=row["project"],
                            similarity=1.0 - float(row.get("_distance", 0.0)),
                        )
                    )
            return results[:k]
        except Exception as exc:
            logger.debug("LanceDBVectorRepository.search: %s", exc)
            return []

    def get_all_raw(self) -> list[dict]:
        try:
            return self._table.to_pandas().to_dict(orient="records")
        except Exception as exc:
            logger.debug("LanceDBVectorRepository.get_all_raw: %s", exc)
            return []
