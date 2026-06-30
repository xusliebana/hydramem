"""Configuration — single responsibility: load and expose app settings.

Resolution order for each value: config.yml → env var → built-in default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_SEARCH_PATHS: list[Path] = [
    Path("config.yml"),
    Path("config.yaml"),
    Path.home() / ".hydramem" / "config.yml",
]


def hydramem_home() -> Path:
    """Base directory for local runtime state (metrics DB, session log,
    Night Gardener status, and the runtime ``config.json``).

    When ``HYDRAMEM_DATA_DIR`` is set — e.g. the Docker image points it at
    ``/data`` so a single mounted volume captures everything — all state is
    rooted there. Otherwise the historical ``~/.hydramem`` location is used.
    """
    base = os.getenv("HYDRAMEM_DATA_DIR")
    return Path(base) if base else (Path.home() / ".hydramem")


def _config_search_paths() -> list[Path]:
    """Config files are looked up project-first, then under the state dir."""
    return [
        Path("config.yml"),
        Path("config.yaml"),
        hydramem_home() / "config.yml",
    ]


def _load_yaml(paths: list[Path] | None = None) -> dict[str, Any]:
    """Load the first config file found. Returns empty dict if none exists."""
    for path in paths if paths is not None else _config_search_paths():
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text()) or {}
                return data
            except Exception:  # noqa: BLE001
                pass
    return {}


def _y(cfg: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    """Read a dotted YAML key: _y(cfg, 'llm.local.model')."""
    node: Any = cfg
    for part in dotted_key.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return default
        if node is None:
            return default
    return node if node is not None else default


def load_config(yaml_data: dict[str, Any] | None = None) -> Config:
    """Build a Config from yaml_data (or re-read from disk if None)."""
    cfg = yaml_data if yaml_data is not None else _load_yaml()
    return Config(cfg)


class Config:
    """Immutable application configuration.

    Attributes are resolved from (in order):
      1. YAML file (config.yml / ~/.hydramem/config.yml)
      2. Environment variables
      3. Hardcoded defaults

    Design: plain attributes — no properties, no magic — easy to override in tests.
    """

    def __init__(self, yaml_cfg: dict[str, Any] | None = None) -> None:
        cfg = yaml_cfg or {}

        # ── LLM ──────────────────────────────────────────────────────────────
        explicit_provider = _y(cfg, "llm.provider")
        self.llm_provider: str = self._resolve_provider(explicit_provider)

        self.ollama_host: str = _y(cfg, "llm.local.endpoint") or os.getenv(
            "OLLAMA_HOST", "http://localhost:11434"
        )
        self.ollama_model: str = _y(cfg, "llm.local.model") or os.getenv(
            "OLLAMA_MODEL", "gemma4:e4b"
        )
        self.external_provider: str = _y(cfg, "llm.external.provider") or os.getenv(
            "HYDRAMEM_EXTERNAL_PROVIDER", ""
        )
        self.external_model: str = _y(cfg, "llm.external.model") or os.getenv(
            "HYDRAMEM_EXTERNAL_MODEL", "gpt-4o-mini"
        )
        self.external_api_key_env: str = (
            _y(cfg, "llm.external.api_key_env") or "HYDRAMEM_OPENAI_KEY"
        )

        # ── Embeddings ────────────────────────────────────────────────────────
        self.embedding_model: str = _y(cfg, "embedding.model") or os.getenv(
            "EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5"
        )
        # Nomic Embed Text v1.5 is a Matryoshka model (native 768-d). HydraMem
        # truncates + renormalises every vector to ``embedding.dim``. 512 is a
        # strong quality/size trade-off; 256 also works well for smaller, faster
        # indexes. Must be <= the embedder's native output dimension.
        self.embedding_dim: int = int(_y(cfg, "embedding.dim") or os.getenv("EMBEDDING_DIM", "512"))
        self.embedding_backend: str = (
            _y(cfg, "embedding.backend") or os.getenv("HYDRAMEM_EMBEDDER", "") or "auto"
        )

        # ── Entity extraction ────────────────────────────────────────────────────
        # Backend for named-entity extraction during ingestion:
        #   heuristic → regex (default, zero deps)
        #   gliner    → zero-shot multilingual NER (needs the [gliner] extra;
        #               degrades to heuristic when the model is unavailable).
        self.extraction_backend: str = (
            _y(cfg, "extraction.backend") or os.getenv("HYDRAMEM_EXTRACTOR") or "heuristic"
        ).lower()
        self.gliner_model: str = (
            _y(cfg, "extraction.gliner.model")
            or os.getenv("HYDRAMEM_GLINER_MODEL")
            or "urchade/gliner_multi-v2.1"
        )
        self.gliner_threshold: float = float(
            _y(cfg, "extraction.gliner.threshold") or os.getenv("HYDRAMEM_GLINER_THRESHOLD") or 0.5
        )
        _gliner_labels = _y(cfg, "extraction.gliner.labels")
        self.gliner_labels: list[str] = (
            [str(x) for x in _gliner_labels]
            if isinstance(_gliner_labels, list) and _gliner_labels
            else [
                "person",
                "organization",
                "location",
                "concept",
                "product",
                "technology",
                "event",
                "date",
            ]
        )

        # ── Storage ───────────────────────────────────────────────────────────
        # Resolution order matches the rest of Config: YAML → env var → default.
        # ``ladybug_db_path`` is retained as the canonical key for backwards
        # compatibility; ``grafeo_db_path`` is its modern alias (Grafeo is now
        # the default graph + vector backend, sharing one DB directory).
        #
        # When HYDRAMEM_DATA_DIR is set (e.g. the Docker image points it at
        # /data), the stores live underneath it so a single mounted volume
        # captures all state. Otherwise the project-local ./data layout wins.
        _data_base = os.getenv("HYDRAMEM_DATA_DIR")
        self.ladybug_db_path: str = (
            _y(cfg, "storage.grafeo_db")
            or _y(cfg, "storage.ladybug_db")
            or os.getenv("GRAFEO_DB_PATH")
            or os.getenv("LADYBUG_DB_PATH")
            or (str(Path(_data_base) / "hydramem.graph") if _data_base else "./data/hydramem.graph")
        )
        self.grafeo_db_path: str = self.ladybug_db_path
        self.lancedb_path: str = (
            _y(cfg, "storage.lancedb")
            or os.getenv("LANCEDB_PATH")
            or (str(Path(_data_base) / "lancedb") if _data_base else "./data/lancedb")
        )
        self.knowledge_dir: str = (
            _y(cfg, "storage.knowledge_dir") or os.getenv("KNOWLEDGE_DIR") or "./kms"
        )

        # ── MCP server ────────────────────────────────────────────────────────
        self.mcp_host: str = _y(cfg, "server.host") or os.getenv("MCP_HOST") or "0.0.0.0"
        self.mcp_port: int = int(_y(cfg, "server.port") or os.getenv("MCP_PORT") or 3000)

        # ── Verification thresholds ───────────────────────────────────────────
        self.srmkg_threshold_accept: float = float(
            _y(cfg, "verification.srmkg_threshold_accept") or 0.7
        )
        self.srmkg_threshold_reject: float = float(
            _y(cfg, "verification.srmkg_threshold_reject") or 0.3
        )
        self.vog_max_candidates: int = int(_y(cfg, "verification.vog_max_candidates") or 30)
        _vog_local = _y(cfg, "verification.vog_use_local_llm")
        self.vog_use_local_llm: bool = bool(_vog_local) if _vog_local is not None else True

        # ── SR-MKG weights (heuristic; overridable for tuning/benchmarks) ────
        self.srmkg_weight_base: float = float(_y(cfg, "verification.srmkg_weight_base") or 0.4)
        self.srmkg_weight_jaccard: float = float(
            _y(cfg, "verification.srmkg_weight_jaccard") or 0.4
        )
        self.srmkg_weight_type_boost: float = float(
            _y(cfg, "verification.srmkg_weight_type_boost") or 0.05
        )
        self.srmkg_penalty_isolated: float = float(
            _y(cfg, "verification.srmkg_penalty_isolated") or 0.3
        )

        # Vector-similarity prefilter used inside ``verify_chunks`` (NOT SR-MKG).
        # Documented separately so users do not confuse it with the relation
        # verifier above. See docs/verification.md.
        self.chunk_vector_threshold_accept: float = float(
            _y(cfg, "verification.chunk_vector_threshold_accept") or 0.7
        )
        self.chunk_vector_threshold_reject: float = float(
            _y(cfg, "verification.chunk_vector_threshold_reject") or 0.3
        )

        # ── Night Gardener ────────────────────────────────────────────────────
        _ng_enabled = _y(cfg, "night_gardener.enabled")
        self.gardener_enabled: bool = bool(_ng_enabled) if _ng_enabled is not None else True
        self.gardener_schedule: str = _y(cfg, "night_gardener.schedule") or "0 3 * * *"
        self.gardener_infer_with: str = _y(cfg, "night_gardener.infer_with") or "local"
        self.gardener_verify_with: str = _y(cfg, "night_gardener.verify_with") or "auto"
        self.gardener_min_repeat_count: int = int(_y(cfg, "night_gardener.min_repeat_count") or 2)

        # Consolidation — re-weight memory by retrieval reuse (no LLM in path).
        _consol = _y(cfg, "night_gardener.consolidation.enabled")
        self.consolidation_enabled: bool = bool(_consol) if _consol is not None else True
        self.consolidation_window_days: int = int(
            _y(cfg, "night_gardener.consolidation.window_days") or 30
        )
        self.consolidation_boost_per_session: float = float(
            _y(cfg, "night_gardener.consolidation.boost_per_session") or 0.02
        )
        self.consolidation_decay_after_days: int = int(
            _y(cfg, "night_gardener.consolidation.decay_after_days") or 14
        )
        self.consolidation_decay_per_step: float = float(
            _y(cfg, "night_gardener.consolidation.decay_per_step") or 0.05
        )
        self.consolidation_min_confidence: float = float(
            _y(cfg, "night_gardener.consolidation.min_confidence") or 0.05
        )
        self.consolidation_max_confidence: float = float(
            _y(cfg, "night_gardener.consolidation.max_confidence") or 0.99
        )

        # HITL prune review (active-learning golden dataset for the GNN pruner).
        # Off by default; when on, the Gardener queues a sample of borderline
        # spurious-edge candidates for human labelling (uncertainty sampling).
        _review_on = _y(cfg, "night_gardener.review.enabled")
        self.prune_review_enabled: bool = (
            bool(_review_on)
            if _review_on is not None
            else os.getenv("HYDRAMEM_PRUNE_REVIEW", "0") not in ("0", "false", "False")
        )
        self.prune_review_sample_rate: float = float(
            _y(cfg, "night_gardener.review.sample_rate") or 0.2
        )
        self.prune_review_band: float = float(
            _y(cfg, "night_gardener.review.uncertainty_band") or 0.25
        )
        self.prune_review_max_per_run: int = int(_y(cfg, "night_gardener.review.max_per_run") or 50)
        # Auto-training (step 2): retrain the learned pruner at the end of a
        # cycle once enough labels exist. Opt-in; off by default.
        _auto_train = _y(cfg, "night_gardener.review.auto_train")
        self.prune_review_auto_train: bool = bool(_auto_train) if _auto_train is not None else False

        # Temporal invalidation (Zep/Graphiti-style fact supersession). When a
        # new *functional* relation arrives, older conflicting edges get their
        # validity window closed (valid_to) instead of lingering as stale
        # contradictions. Off by default; only acts on configured relation types.
        _ti = _y(cfg, "night_gardener.temporal_invalidation.enabled")
        self.temporal_invalidation_enabled: bool = bool(_ti) if _ti is not None else False
        _ft = _y(cfg, "night_gardener.temporal_invalidation.functional_types")
        self.functional_relation_types: list[str] = (
            [str(x).lower() for x in _ft] if isinstance(_ft, list) and _ft else []
        )

        # ── Search / retrieval ────────────────────────────────────────────────
        self.search_traversal: str = (
            _y(cfg, "search.traversal") or os.getenv("HYDRAMEM_SEARCH_TRAVERSAL", "bfs")
        ).lower()
        self.ppr_alpha: float = float(_y(cfg, "search.ppr.alpha") or 0.5)
        self.ppr_max_iter: int = int(_y(cfg, "search.ppr.max_iter") or 50)
        self.ppr_tol: float = float(_y(cfg, "search.ppr.tol") or 1e-4)
        self.ppr_top_k: int = int(_y(cfg, "search.ppr.top_k") or 30)
        # Lexical BM25 arm fused with vector + graph via RRF (keyword recall).
        _bm25_on = _y(cfg, "search.bm25.enabled")
        self.search_bm25: bool = (
            bool(_bm25_on)
            if _bm25_on is not None
            else os.getenv("HYDRAMEM_SEARCH_BM25", "1") not in ("0", "false", "False")
        )
        self.bm25_k1: float = float(_y(cfg, "search.bm25.k1") or 1.5)
        self.bm25_b: float = float(_y(cfg, "search.bm25.b") or 0.75)
        self.bm25_top_k: int = int(_y(cfg, "search.bm25.top_k") or 0)
        # Typed retrieval planner (opt-in): zero-shot query classifier → strategy.
        _planner_on = _y(cfg, "search.planner.enabled")
        self.planner_enabled: bool = (
            bool(_planner_on)
            if _planner_on is not None
            else os.getenv("HYDRAMEM_PLANNER", "0") not in ("0", "false", "False")
        )
        self.planner_threshold: float = float(_y(cfg, "search.planner.threshold") or 0.15)

        # ── GNN pruner ────────────────────────────────────────────────────────
        _gnn_lpe = _y(cfg, "gnn.use_laplacian_pe")
        self.gnn_use_laplacian_pe: bool = bool(_gnn_lpe) if _gnn_lpe is not None else True
        self.gnn_lpe_k: int = int(_y(cfg, "gnn.lpe_k") or 32)

        # ── SR-MKG calibration ────────────────────────────────────────────────
        # Per-project learned weights live under
        # ``~/.hydramem/projects/<p>/srmkg_weights.json`` (see
        # ``docs/internal/future_work/learned-srmkg-weights.md``). Logging the raw
        # score components drives the training set.
        _srmkg_log = _y(cfg, "verification.srmkg_log_decisions")
        self.srmkg_log_decisions: bool = bool(_srmkg_log) if _srmkg_log is not None else True

        # ── Agent-driven ingestion limits ────────────────────────────────────
        # Cap how much data an agent (Copilot / opencode / …) can push in a
        # single ``ingest_prechunked`` or ``submit_session_extraction`` call.
        self.ingest_max_chunks: int = int(
            _y(cfg, "ingest.max_chunks") or os.getenv("HYDRAMEM_INGEST_MAX_CHUNKS") or 200
        )
        self.ingest_max_entities: int = int(
            _y(cfg, "ingest.max_entities") or os.getenv("HYDRAMEM_INGEST_MAX_ENTITIES") or 1000
        )
        self.ingest_max_relations: int = int(
            _y(cfg, "ingest.max_relations") or os.getenv("HYDRAMEM_INGEST_MAX_RELATIONS") or 500
        )
        _verify_agent = (
            _y(cfg, "ingest.verify_agent_relations")
            if _y(cfg, "ingest.verify_agent_relations") is not None
            else os.getenv("HYDRAMEM_VERIFY_AGENT_RELATIONS")
        )
        self.ingest_verify_agent_relations: bool = (
            True
            if _verify_agent is None
            else str(_verify_agent).lower() not in ("0", "false", "no")
        )
        # ``agent`` (BYO-extraction first), ``heuristic`` (regex only),
        # or ``auto`` (let the skill decide). Currently informational — the
        # MCP server always exposes both tools; this guides the skill prompt.
        self.ingest_mode: str = (
            _y(cfg, "ingest.mode") or os.getenv("HYDRAMEM_INGEST_MODE") or "auto"
        ).lower()
        # Collapse surface-form variants of the same entity into one canonical
        # node (case/space/punctuation-insensitive). Conservative, no fuzzy.
        _entity_disambig = _y(cfg, "ingest.entity_disambiguation")
        self.ingest_entity_disambiguation: bool = (
            bool(_entity_disambig)
            if _entity_disambig is not None
            else os.getenv("HYDRAMEM_ENTITY_DISAMBIGUATION", "1") not in ("0", "false", "False")
        )

        # ── Derived ───────────────────────────────────────────────────────────
        self.llm_preset: str = (
            self.ollama_model if self.llm_provider in ("ollama", "local") else self.external_model
        )
        self.project: str = os.getenv("HYDRAMEM_PROJECT", "default")

    @staticmethod
    def _resolve_provider(explicit: str | None) -> str:
        """Auto-detect provider when explicit is None or 'auto'."""
        if explicit and explicit not in ("auto", ""):
            return explicit
        env = os.getenv("HYDRAMEM_LLM_PROVIDER", "").lower()
        if env:
            return env
        # Auto-detect by available API keys
        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("HYDRAMEM_ANTHROPIC_KEY"):
            return "anthropic"
        if os.getenv("MISTRAL_API_KEY") or os.getenv("HYDRAMEM_MISTRAL_KEY"):
            return "mistral"
        if os.getenv("OPENAI_API_KEY") or os.getenv("HYDRAMEM_OPENAI_KEY"):
            return "openai"
        return "ollama"

    def ensure_data_dirs(self) -> None:
        """Create storage directories if they don't exist."""
        Path(self.ladybug_db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.lancedb_path).mkdir(parents=True, exist_ok=True)
        Path(self.knowledge_dir).mkdir(parents=True, exist_ok=True)
