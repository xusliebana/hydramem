"""EntityExtractor — single responsibility: extract named entities from text."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from hydramem.core.logging import get_logger
from hydramem.core.types import Entity
from hydramem.ingest.registry import entity_id

logger = get_logger(__name__)

# Default zero-shot label set for the GLiNER backend. Override via
# ``extraction.gliner.labels`` in config.yml.
_DEFAULT_GLINER_LABELS: tuple[str, ...] = (
    "person",
    "organization",
    "location",
    "concept",
    "product",
    "technology",
    "event",
    "date",
)


@runtime_checkable
class EntityExtractorProtocol(Protocol):
    """Minimal contract any extractor must satisfy.

    Lets users swap the default heuristic with an NER model or LLM-assisted
    extractor without modifying ``IngestionPipeline``.
    """

    def extract(self, text: str, doc_id: str, project: str) -> list[Entity]: ...


_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "it",
        "this",
        "that",
        "with",
        "from",
    }
)


class EntityExtractor:
    """Heuristic entity extractor — no LLM required.

    Recognises:
    - Multi-word capitalised phrases (e.g. "Night Gardener")
    - CamelCase identifiers (e.g. "LanceDB", "KnowledgeStore")
    - Backtick code spans (e.g. `` `hydra_search` ``)
    """

    def extract(self, text: str, doc_id: str, project: str) -> list[Entity]:
        """Return a deduplicated list of entities found in *text*."""
        raw: list[Entity] = []
        raw.extend(self._capitalised_phrases(text, doc_id, project))
        raw.extend(self._camel_case(text, doc_id, project))
        raw.extend(self._backtick_spans(text, doc_id, project))
        return self._deduplicate(raw)

    # ── Patterns ──────────────────────────────────────────────────────────────

    def _capitalised_phrases(self, text: str, doc_id: str, project: str) -> list[Entity]:
        entities = []
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text):
            name = m.group(1)
            if any(w.lower() in _STOP_WORDS for w in name.split()):
                continue
            entities.append(
                Entity(
                    id=self._eid(project, name),
                    name=name,
                    type="concept",
                    project=project,
                )
            )
        return entities

    def _camel_case(self, text: str, doc_id: str, project: str) -> list[Entity]:
        entities = []
        for m in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", text):
            name = m.group(1)
            entities.append(
                Entity(
                    id=self._eid(project, name),
                    name=name,
                    type="identifier",
                    project=project,
                )
            )
        return entities

    def _backtick_spans(self, text: str, doc_id: str, project: str) -> list[Entity]:
        entities = []
        for m in re.finditer(r"`([^`]{2,40})`", text):
            name = m.group(1)
            entities.append(
                Entity(
                    id=self._eid(project, name),
                    name=name,
                    type="code",
                    project=project,
                )
            )
        return entities

    @staticmethod
    def _eid(project: str, name: str) -> str:
        return hashlib.md5(f"{project}:{name}".encode()).hexdigest()[:12]

    @staticmethod
    def _deduplicate(entities: list[Entity]) -> list[Entity]:
        seen: set[str] = set()
        out: list[Entity] = []
        for e in entities:
            if e.id not in seen:
                seen.add(e.id)
                out.append(e)
        return out


# ---------------------------------------------------------------------------
# GLiNER backend (zero-shot, multilingual NER)
# ---------------------------------------------------------------------------


class GlinerExtractor:
    """Zero-shot multilingual entity extractor backed by GLiNER.

    Lazy-loads the model on first use. If the optional ``[gliner]`` extra (or
    the model download) is unavailable, it degrades gracefully to the heuristic
    extractor instead of crashing — the local-first contract. Surface forms are
    fed through :func:`hydramem.ingest.registry.entity_id` so ids stay
    consistent with the disambiguation registry.
    """

    def __init__(
        self,
        model: str = "urchade/gliner_multi-v2.1",
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> None:
        self._model_name = model
        self._labels = list(labels) if labels else list(_DEFAULT_GLINER_LABELS)
        self._threshold = threshold
        self._model = None  # lazily loaded GLiNER instance
        self._fallback: EntityExtractor | None = None
        self._degraded = False

    def _ensure_model(self) -> None:
        if self._model is not None or self._degraded:
            return
        try:
            from gliner import GLiNER  # type: ignore[import-untyped]

            self._model = GLiNER.from_pretrained(self._model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GLiNER unavailable (%s); falling back to the heuristic "
                "extractor. Install it with: pip install 'hydramem[gliner]'.",
                exc,
            )
            self._degraded = True
            self._fallback = EntityExtractor()

    def extract(self, text: str, doc_id: str, project: str) -> list[Entity]:
        """Return canonical entities found in *text* (heuristic if degraded)."""
        self._ensure_model()
        if self._degraded:
            return self._fallback.extract(text, doc_id, project)  # type: ignore[union-attr]
        try:
            spans = self._model.predict_entities(  # type: ignore[union-attr]
                text, self._labels, threshold=self._threshold
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("GLiNER inference failed (%s); using heuristic for this chunk", exc)
            if self._fallback is None:
                self._fallback = EntityExtractor()
            return self._fallback.extract(text, doc_id, project)

        seen: set[str] = set()
        out: list[Entity] = []
        for span in spans:
            name = (span.get("text") or "").strip()
            if not name:
                continue
            eid = entity_id(project, name)
            if eid in seen:
                continue
            seen.add(eid)
            out.append(
                Entity(
                    id=eid,
                    name=name,
                    type=(span.get("label") or "concept"),
                    project=project,
                )
            )
        return out


# ---------------------------------------------------------------------------
# Pluggable factory
# ---------------------------------------------------------------------------


def _build_heuristic(config: object | None = None) -> EntityExtractorProtocol:
    return EntityExtractor()


def _build_gliner(config: object | None = None) -> EntityExtractorProtocol:
    model = "urchade/gliner_multi-v2.1"
    labels: list[str] | None = None
    threshold = 0.5
    if config is not None:
        model = getattr(config, "gliner_model", model)
        labels = getattr(config, "gliner_labels", labels)
        threshold = float(getattr(config, "gliner_threshold", threshold))
    return GlinerExtractor(model=model, labels=labels, threshold=threshold)


_REGISTRY: dict[str, Callable[..., EntityExtractorProtocol]] = {
    "heuristic": _build_heuristic,
    "gliner": _build_gliner,
}


def create_extractor(
    name: str | None = None, *, config: object | None = None
) -> EntityExtractorProtocol:
    """Build an extractor by name.

    Resolution: argument → ``HYDRAMEM_EXTRACTOR`` env var → ``"heuristic"``.
    Shipped backends: ``heuristic`` (regex, zero deps) and ``gliner`` (zero-shot
    multilingual NER, needs the ``[gliner]`` extra and degrades to heuristic
    when unavailable). Custom extractors can register by assigning to
    ``_REGISTRY``. *config* is forwarded to backends that need settings.
    """
    chosen = (name or os.getenv("HYDRAMEM_EXTRACTOR") or "heuristic").lower()
    builder = _REGISTRY.get(chosen)
    if builder is None:
        raise ValueError(f"Unknown extractor {chosen!r}. Registered: {sorted(_REGISTRY)}")
    return builder(config)
