"""Repository Protocols — Dependency Inversion boundaries for storage.

Callers depend on these protocols, not on concrete backends (DIP).
New backends can be added without modifying callers (OCP).
Each protocol is minimal — clients depend only on what they use (ISP).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hydramem.core.types import Chunk, Entity, Relation


@runtime_checkable
class GraphRepository(Protocol):
    """Persistence contract for the knowledge graph."""

    def add_entity(self, entity: Entity) -> None: ...

    def add_relation(self, relation: Relation) -> None: ...

    def delete_relation(self, from_entity: str, to_entity: str, relation_type: str) -> bool: ...

    def delete_entity(self, entity_id: str) -> bool: ...

    def get_entity_neighbors(self, entity_id: str, hops: int = 1) -> list[dict]: ...

    def get_chunks_near_entity(self, entity_id: str) -> list[Chunk]: ...

    def list_entities(self, project: str = "default") -> list[dict]: ...

    def add_chunk(self, chunk: Chunk) -> None: ...

    def get_all_chunks(self) -> list[Chunk]: ...

    def list_relations(self, project: str = "default") -> list[dict]: ...


@runtime_checkable
class VectorRepository(Protocol):
    """Persistence contract for the vector index."""

    def add(self, chunk: Chunk, embedding: list[float]) -> None: ...

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        project: str = "default",
    ) -> list[Chunk]: ...

    def get_all_raw(self) -> list[dict]: ...
