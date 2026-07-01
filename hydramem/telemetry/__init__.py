"""Telemetry package – local-only metrics for HydraMem."""

from hydramem.telemetry.shadow import estimate_naive_rag_tokens
from hydramem.telemetry.storage import init_db, list_projects, log_event

__all__ = ["init_db", "list_projects", "log_event", "estimate_naive_rag_tokens"]
