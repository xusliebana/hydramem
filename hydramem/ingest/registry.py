"""Entity disambiguation registry — collapse surface-form variants of the same
entity into one canonical node.

The heuristic extractor emits a fresh node per surface form, so ``HydraMem``,
``hydramem`` and ``Hydra Mem`` become three distinct entities. That fragments
the graph and weakens traversal / SR-MKG scoring. The registry canonicalises
names (case / spacing / punctuation insensitive), assigns one stable id per
canonical key, picks a deterministic *best* display name, and tracks the merged
aliases for auditability.

Conservative by design: it only merges names that are **identical after
normalisation** — no fuzzy / edit-distance matching — so it never silently
fuses genuinely different entities (honesty contract). Disambiguation can be
turned off entirely via ``ingest.entity_disambiguation: false``.
"""

from __future__ import annotations

import hashlib
import re

from hydramem.core.types import Entity

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Preference order when surface forms disagree on the entity type.
_TYPE_PRIORITY = {
    "code": 0,
    "identifier": 1,
    "person": 2,
    "org": 3,
    "tool": 4,
    "concept": 5,
}


def canonical_key(name: str) -> str:
    """Normalise *name* to a match key (lowercase, alphanumeric only).

    ``HydraMem``, ``hydra-mem``, ``Hydra Mem`` and ``HYDRAMEM`` all map to
    ``hydramem``. Returns ``""`` when the name has no alphanumeric content.
    """
    return _NON_ALNUM.sub("", name.lower())


def entity_id(project: str, name: str) -> str:
    """Stable canonical entity id for *name* within *project*."""
    return hashlib.md5(f"{project}:{canonical_key(name)}".encode()).hexdigest()[:12]


def raw_entity_id(project: str, name: str) -> str:
    """Legacy per-surface-form id (used when disambiguation is disabled)."""
    return hashlib.md5(f"{project}:{name}".encode()).hexdigest()[:12]


def _display_sort_key(name: str) -> tuple[int, int, str]:
    uppers = sum(1 for c in name if c.isupper())
    # Most uppercase (proper-noun signal) → shortest → lexicographic.
    return (-uppers, len(name), name)


def best_display(aliases: set[str]) -> str:
    """Pick the most proper-noun-like surface form (deterministic)."""
    return sorted(aliases, key=_display_sort_key)[0]


def best_type(types: set[str]) -> str:
    """Pick the most specific entity type (deterministic)."""
    return sorted(types, key=lambda t: (_TYPE_PRIORITY.get(t, 9), t))[0]


class EntityRegistry:
    """Per-document registry that canonicalises entity surface forms.

    Usage is two-phase so the chosen display name is the global best across the
    whole document, independent of mention order:

        for name in surface_forms:
            registry.register(name, type)
        entity = registry.resolve(name, type)   # canonical id + best display
    """

    def __init__(self, project: str = "default", *, enabled: bool = True) -> None:
        self._project = project
        self._enabled = enabled
        # canonical_key -> {"id": str, "aliases": set[str], "types": set[str]}
        self._buckets: dict[str, dict] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register(self, name: str, type: str = "concept") -> None:
        """Record a surface form so :meth:`resolve` can return the global best."""
        name = (name or "").strip()
        key = canonical_key(name)
        if not key:
            return
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = {
                "id": entity_id(self._project, name),
                "aliases": set(),
                "types": set(),
            }
            self._buckets[key] = bucket
        bucket["aliases"].add(name)
        if type:
            bucket["types"].add(type)

    def resolve(self, name: str, type: str = "concept", project: str | None = None) -> Entity:
        """Return the canonical :class:`Entity` for *name*.

        When disabled, falls back to the legacy per-surface-form id so behaviour
        is unchanged. When enabled and the name was registered, returns the
        shared id plus the deterministic best display name and type.
        """
        proj = project or self._project
        name = (name or "").strip()
        if not self._enabled:
            return Entity(id=raw_entity_id(proj, name), name=name, type=type, project=proj)
        bucket = self._buckets.get(canonical_key(name))
        if bucket is None:
            return Entity(id=entity_id(proj, name), name=name, type=type, project=proj)
        return Entity(
            id=bucket["id"],
            name=best_display(bucket["aliases"]),
            type=best_type(bucket["types"] or {type}),
            project=proj,
        )

    def id_for(self, name: str) -> str | None:
        """Canonical id for *name* if it was registered, else ``None``."""
        bucket = self._buckets.get(canonical_key((name or "").strip()))
        return bucket["id"] if bucket else None

    def aliases(self) -> dict[str, list[str]]:
        """Map canonical id → sorted surface forms (for auditing)."""
        return {b["id"]: sorted(b["aliases"]) for b in self._buckets.values()}

    @property
    def merged_count(self) -> int:
        """How many surface forms were collapsed away (aliases beyond one)."""
        return sum(max(0, len(b["aliases"]) - 1) for b in self._buckets.values())
