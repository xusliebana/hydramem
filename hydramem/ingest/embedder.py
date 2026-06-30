"""EmbeddingService — single responsibility: generate vector embeddings.

Backend selection (in order):

1. **fastembed** (ONNX, ~80 MB, no torch dependency) — default when installed.
2. **sentence-transformers** (PyTorch, ~2 GB) — fallback for users that
   already have it or need a model not packaged by fastembed.
3. **stub** (deterministic hash-based embedding) — last-resort fallback so
   tests and offline installs never crash. Quality is intentionally poor.

The backend is detected lazily on the first ``embed*`` call so import-time
cost stays minimal.
"""

from __future__ import annotations

import hashlib
import math
import os

from hydramem.core.logging import get_logger

logger = get_logger(__name__)


def _force_backend() -> str:
    """Read the HYDRAMEM_EMBEDDER env var at call time (not import time)."""
    return os.getenv("HYDRAMEM_EMBEDDER", "").lower()


# Nomic-style task instruction prefixes (asymmetric query/document encoding).
# Nomic Embed is trained so queries and passages live in a shared space only
# when these prefixes are prepended. See https://docs.nomic.ai.
_QUERY_PREFIX = "search_query: "
_DOCUMENT_PREFIX = "search_document: "


class EmbeddingService:
    """Generates dense embeddings using the best available local backend."""

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        dim: int = 512,
        backend: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._dim = dim
        # Nomic-style models use asymmetric task prefixes (search_query: /
        # search_document:). Enabled automatically from the model name.
        self._prefix_enabled = "nomic" in model_name.lower()
        # Explicit backend override (config-driven). ``None`` / ``"auto"``
        # fall back to env-var detection inside :meth:`_load`.
        self._forced_backend = (backend or "").lower() or None
        self._backend: str | None = None
        self._model: object | None = None  # lazy

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        if self._model is not None or self._backend == "stub":
            return

        backend = self._forced_backend or _force_backend()
        if backend == "auto":
            backend = ""
        if backend == "stub":
            self._backend = "stub"
            return
        if backend in ("", "fastembed"):
            try:
                from fastembed import TextEmbedding  # type: ignore

                # fastembed uses its own model registry; map common defaults.
                fe_name = (
                    "BAAI/bge-small-en-v1.5"
                    if self._model_name == "all-MiniLM-L6-v2"
                    else self._model_name
                )
                self._model = TextEmbedding(model_name=fe_name)
                self._backend = "fastembed"
                logger.info("EmbeddingService: backend=fastembed model=%s", fe_name)
                return
            except Exception as exc:  # noqa: BLE001
                if backend == "fastembed":
                    raise
                logger.debug("fastembed unavailable (%s), trying sentence-transformers", exc)

        if backend in ("", "st", "sentence-transformers"):
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                # Modern embedders such as Nomic Embed ship custom modelling code
                # and require trust_remote_code=True to load.
                st_kwargs = (
                    {"trust_remote_code": True} if "nomic" in self._model_name.lower() else {}
                )
                self._model = SentenceTransformer(self._model_name, **st_kwargs)
                self._backend = "sentence-transformers"
                logger.info(
                    "EmbeddingService: backend=sentence-transformers model=%s",
                    self._model_name,
                )
                return
            except Exception as exc:  # noqa: BLE001
                if backend in ("st", "sentence-transformers"):
                    raise
                logger.warning(
                    "sentence-transformers unavailable (%s); using deterministic stub embedder "
                    "— install `hydramem[fastembed]` for real embeddings.",
                    exc,
                )

        # Last-resort stub: deterministic, no quality guarantees.
        self._model = None
        self._backend = "stub"

    # ----------------------------------------------------------------- embed
    def _maybe_prefix(self, text: str, prefix: str) -> str:
        """Prepend a Nomic task prefix — only for instruction-tuned models on a
        real backend. Never for the deterministic stub, where a prefix would
        merely shift the hash and break query↔document matching.
        """
        if self._prefix_enabled and self._backend in ("fastembed", "sentence-transformers"):
            return prefix + text
        return text

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        """Return a float vector for *text* (truncated to ``dim`` if longer).

        Set ``is_query=True`` when embedding a search query so Nomic-style models
        receive the ``search_query:`` prefix; everything else is treated as a
        document (``search_document:``).
        """
        self._load()
        text = self._maybe_prefix(text, _QUERY_PREFIX if is_query else _DOCUMENT_PREFIX)
        if self._backend == "fastembed":
            vec = list(next(iter(self._model.embed([text]))).tolist())  # type: ignore[union-attr]
            return _truncate_norm(vec, self._dim)
        if self._backend == "sentence-transformers":
            vec = self._model.encode(text, convert_to_numpy=True).tolist()  # type: ignore[union-attr]
            return _truncate_norm(vec, self._dim)
        return _stub_embed(text, self._dim)

    def embed_batch(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """Batch-embed multiple texts — ~10× faster than calling :meth:`embed`.

        Defaults to document encoding (``search_document:`` for Nomic models).
        """
        if not texts:
            return []
        self._load()
        prefix = _QUERY_PREFIX if is_query else _DOCUMENT_PREFIX
        prepared = [self._maybe_prefix(t, prefix) for t in texts]
        if self._backend == "fastembed":
            return [
                _truncate_norm(list(v.tolist()), self._dim)  # type: ignore[union-attr]
                for v in self._model.embed(prepared)  # type: ignore[union-attr]
            ]
        if self._backend == "sentence-transformers":
            vecs = self._model.encode(prepared, convert_to_numpy=True).tolist()  # type: ignore[union-attr]
            return [_truncate_norm(v, self._dim) for v in vecs]
        return [_stub_embed(t, self._dim) for t in texts]

    @property
    def backend(self) -> str:
        """Name of the backend currently in use (only valid after first call)."""
        if self._backend is None:
            self._load()
        return self._backend or "stub"


def _truncate_norm(vec: list[float], dim: int) -> list[float]:
    """Matryoshka truncation: slice to *dim* and L2-renormalise.

    Nomic Embed Text v1.5 (native 768-d) and other Matryoshka-trained models
    retain most of their quality when truncated to a shorter prefix. Slicing to
    ``dim`` and renormalising yields valid unit vectors for cosine search. When
    the model already emits ``<= dim`` values this is a no-op.
    """
    if dim <= 0 or len(vec) <= dim:
        return vec
    sliced = vec[:dim]
    norm = math.sqrt(sum(x * x for x in sliced)) or 1.0
    return [x / norm for x in sliced]


def _stub_embed(text: str, dim: int) -> list[float]:
    """Deterministic SHA-256-derived pseudo-embedding (offline last-resort)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Spread bytes across the requested dim and L2-normalise so cosine similarity
    # behaves vaguely sensibly for tests.
    raw = [(digest[i % len(digest)] - 128) / 128.0 for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]
