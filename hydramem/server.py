"""HydraMem MCP Server — 18 tools exposed via FastMCP.

Concurrency model
-----------------
This server is **single-tenant by design**. All service objects
(``SearchService``, ``IngestionPipeline``, ``NightGardener``, etc.) are stored
as process-global singletons and the underlying NetworkX/LanceDB sessions are
not threadsafe. Running it behind a multi-worker reverse proxy or sharing it
between several end users is not supported and may corrupt the local graph.
For multi-tenant deployments, run one HydraMem process per tenant with a
distinct ``HYDRAMEM_PROJECT`` and storage directory.

See ``docs/architecture.md#scaling`` for details.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastmcp import FastMCP  # type: ignore

from hydramem.core.config import load_config
from hydramem.core.tokens import count_tokens
from hydramem.core.types import Relation
from hydramem.garden.gardener import NightGardener
from hydramem.gnn_prune import GNNPruner
from hydramem.ingest.pipeline import IngestionPipeline
from hydramem.search import SearchService
from hydramem.storage.factory import get_store
from hydramem.telemetry import estimate_naive_rag_tokens, log_event
from hydramem.verification.conflict import ConflictChecker
from hydramem.verification.pipeline import VerificationPipeline

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

config = load_config()
mcp = FastMCP("HydraMem")
_SESSION_ID: str = str(uuid4())

# Module-level service singletons (lazy — created on first tool call)
_search: SearchService | None = None
_ingest: IngestionPipeline | None = None
_gardener: NightGardener | None = None
_verif: VerificationPipeline | None = None


def _svc_search() -> SearchService:
    global _search
    if _search is None:
        _search = SearchService()
    return _search


def _svc_ingest() -> IngestionPipeline:
    global _ingest
    if _ingest is None:
        _ingest = IngestionPipeline()
    return _ingest


def _svc_gardener() -> NightGardener:
    global _gardener
    if _gardener is None:
        _gardener = NightGardener()
    return _gardener


def _svc_verif() -> VerificationPipeline:
    global _verif
    if _verif is None:
        _verif = VerificationPipeline()
    return _verif


def _project(p: str) -> str:
    return p or os.getenv("HYDRAMEM_PROJECT", "default")


def _session(s: str) -> str:
    return s or _SESSION_ID


def _persist_session_entry(
    *,
    tool_name: str,
    summary: str,
    project: str,
    session_id: str,
    query: str = "",
) -> None:
    """Persist a compact local session entry for Night Gardener.

    HydraMem does not see the agent's private reasoning or final answer, only
    the MCP requests and the grounded evidence returned by the tool. Store a
    compact summary locally so Night Gardener can mine recurring relations.
    """
    normalized_summary = summary.strip()
    if not normalized_summary:
        return

    _svc_gardener().save_session(
        {
            "project": project,
            "session_id": session_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tool_name": tool_name,
            "query": query.strip(),
            "entry": {
                "ts": datetime.now(timezone.utc).isoformat(),
                "tool_name": tool_name,
                "summary": normalized_summary[:4000],
            },
        }
    )


# ---------------------------------------------------------------------------
# Tool 1: priming_context
# ---------------------------------------------------------------------------

@mcp.tool()
def priming_context_tool(
    query: str, k: int = 3, project: str = "", session_id: str = ""
) -> dict:
    """Return top-k chunks + immediate graph neighbours to seed agent context."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_search().priming_context(query, project=proj, k=k)
    _persist_session_entry(
        tool_name="priming_context",
        query=query,
        summary=(
            f"Query: {query.strip()}\n"
            "Grounded context:\n"
            f"{result.get('context', '').strip()}"
        ),
        project=proj,
        session_id=sid,
    )
    log_event(
        project=proj, tool_name="priming_context", session_id=sid,
        llm_preset=config.llm_preset,
        tokens_injected=count_tokens(result["context"]),
        tokens_baseline=estimate_naive_rag_tokens(
            query, get_store().get_all_chunks_for_telemetry()
        ),
        chunks_total=len(result["chunks"]),
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


# ---------------------------------------------------------------------------
# Tool 2: expand_context
# ---------------------------------------------------------------------------

@mcp.tool()
def expand_context_tool(
    entity_ids: list[str], hops: int = 2, project: str = "", session_id: str = ""
) -> dict:
    """Expand context from entity IDs via multi-hop graph traversal."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_search().expand_context(entity_ids, hops=hops, project=proj)
    _persist_session_entry(
        tool_name="expand_context",
        project=proj,
        session_id=sid,
        summary=(
            f"Expand entities: {', '.join(entity_ids)}\n"
            f"Hops: {hops}\n"
            "Grounded context:\n"
            f"{result.get('context', '').strip()}"
        ),
    )
    log_event(
        project=proj, tool_name="expand_context", session_id=sid,
        chunks_total=len(result["chunks"]),
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


# ---------------------------------------------------------------------------
# Tool 3: hydra_search
# ---------------------------------------------------------------------------

@mcp.tool()
def hydra_search_tool(
    query: str,
    k: int = 5,
    hops: int = 2,
    project: str = "",
    session_id: str = "",
    traversal: str = "",
    strategy_override: str = "",
) -> dict:
    """Full hybrid search: vector + graph traversal + SR-MKG + VoG.

    ``traversal``: ``"bfs"`` (default), ``"ppr"`` (Personalized PageRank), or
    ``"hybrid"`` (RRF fusion of vector + BFS + PPR rankings). Empty string
    falls back to the configured ``search.traversal`` default — or, when the
    typed retrieval planner is enabled, to a zero-shot strategy.
    ``strategy_override`` forces a traversal and bypasses the planner.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_search().hydra_search(
        query,
        project=proj,
        max_hops=hops,
        top_k=k,
        traversal=traversal or None,
        strategy_override=strategy_override or None,
    )
    _persist_session_entry(
        tool_name="hydra_search",
        query=query,
        summary=(
            f"Query: {query.strip()}\n"
            "Grounded context:\n"
            f"{result.get('final_context', '').strip()}"
        ),
        project=proj,
        session_id=sid,
    )
    log_event(
        project=proj, tool_name="hydra_search", session_id=sid,
        llm_preset=config.llm_preset,
        tokens_injected=count_tokens(result["final_context"]),
        tokens_baseline=estimate_naive_rag_tokens(
            query, get_store().get_all_chunks_for_telemetry()
        ),
        chunks_total=result["chunks_total"],
        chunks_rejected_srmkg=result.get("rejected_vector", result.get("rejected_srmkg", 0)),
        chunks_rejected_vog=result["rejected_vog"],
        vog_score=result["avg_vog_score"],
        latency_ms=int((time.time() - start) * 1000),
        metadata={"entities": result.get("entities", []), "planner": result.get("planner")},
    )
    return result


# ---------------------------------------------------------------------------
# Tool 4: trace_path
# ---------------------------------------------------------------------------

@mcp.tool()
def trace_path_tool(
    from_entity: str, to_entity: str, project: str = "", session_id: str = ""
) -> dict:
    """Find the shortest graph path between two named entities."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_search().trace_path(from_entity, to_entity, project=proj)
    path_text = " -> ".join(result.get("path", [])) if result.get("path") else "No path found"
    _persist_session_entry(
        tool_name="trace_path",
        project=proj,
        session_id=sid,
        summary=(
            f"Trace path from {from_entity} to {to_entity}\n"
            f"Found: {result.get('found', False)}\n"
            f"Path: {path_text}"
        ),
        query=f"Trace path from {from_entity} to {to_entity}",
    )
    log_event(project=proj, tool_name="trace_path", session_id=sid,
              latency_ms=int((time.time() - start) * 1000))
    return result


# ---------------------------------------------------------------------------
# Tool 5: verify_relation
# ---------------------------------------------------------------------------

@mcp.tool()
def verify_relation_tool(
    from_entity: str,
    to_entity: str,
    relation_type: str,
    source_text: str = "",
    target_text: str = "",
    confidence: float = 0.5,
    project: str = "",
    session_id: str = "",
) -> dict:
    """Apply two-level SR-MKG + VoG verification to a candidate relation."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    rel = Relation(
        from_entity=from_entity, to_entity=to_entity,
        relation_type=relation_type, confidence=confidence,
        source_text=source_text, target_text=target_text, project=proj,
        session_id=sid, origin_tool="verify_relation",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    vr = _svc_verif().verify(rel)
    result = {
        "accepted": vr.accepted, "srmkg_score": vr.score,
        "vog_score": vr.score if vr.level == "vog" else None,
        "level": vr.level,
    }
    _persist_session_entry(
        tool_name="verify_relation",
        project=proj,
        session_id=sid,
        query=f"Verify relation {from_entity} -[{relation_type}]-> {to_entity}",
        summary=(
            f"Candidate relation: {from_entity} -[{relation_type}]-> {to_entity}\n"
            f"Accepted: {vr.accepted}\n"
            f"Level: {vr.level}\n"
            f"Score: {vr.score:.4f}"
        ),
    )
    log_event(
        project=proj, tool_name="verify_relation", session_id=sid,
        llm_preset=config.llm_preset,
        vog_score=vr.score,
        was_hallucination_blocked=0 if vr.accepted else 1,
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


# ---------------------------------------------------------------------------
# Tool 6: ingest_markdown
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_markdown(
    file_path: str, project: str = "", session_id: str = ""
) -> dict:
    """Ingest a single Markdown file into the knowledge base."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_ingest().ingest_file(file_path, project=proj)
    _svc_search().invalidate_cache(proj)
    log_event(
        project=proj, tool_name="ingest_markdown", session_id=sid,
        chunks_total=result.get("chunks_added", 0),
        latency_ms=int((time.time() - start) * 1000),
        metadata={"file": result.get("file"), "doc_id": result.get("doc_id")},
    )
    return result


# ---------------------------------------------------------------------------
# Tool 7: ingest_directory
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_directory_tool(
    directory: str, project: str = "", recursive: bool = True, session_id: str = ""
) -> dict:
    """Ingest all Markdown files in a directory."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_ingest().ingest_directory(directory, project=proj, recursive=recursive)
    _svc_search().invalidate_cache(proj)
    log_event(
        project=proj, tool_name="ingest_directory", session_id=sid,
        chunks_total=result.get("chunks_added", 0),
        latency_ms=int((time.time() - start) * 1000),
        metadata={"files_processed": result.get("files_processed")},
    )
    return result


# ---------------------------------------------------------------------------
# Tool 18: remember  (accumulate knowledge mid-conversation)
# ---------------------------------------------------------------------------

@mcp.tool()
def remember(
    text: str, source: str = "chat-note", project: str = "", session_id: str = ""
) -> dict:
    """Persist a free-text note/fact into the knowledge base during a chat.

    Unlike a plain vector store, the note flows through the full HydraMem
    pipeline — chunked, embedded, entities extracted + canonicalised — so it
    becomes first-class graph knowledge that later search, the verification
    pipeline, and the Night Gardener can all use. Ideal for "remember that we
    decided X" moments without writing a file.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_ingest().ingest_text(text, source=source, project=proj)
    _svc_search().invalidate_cache(proj)
    log_event(
        project=proj, tool_name="remember", session_id=sid,
        chunks_total=result.get("chunks_added", 0),
        latency_ms=int((time.time() - start) * 1000),
        metadata={"source": source, "doc_id": result.get("doc_id")},
    )
    return result


# ---------------------------------------------------------------------------
# Tool 7a: ingest_prechunked  (agent-driven / BYO-extraction)
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_prechunked(
    source: str,
    chunks: list[dict],
    doc_id: str = "",
    project: str = "",
    session_id: str = "",
) -> dict:
    """Ingest a document already chunked + entity/relation-extracted by the agent.

    Preferred over ``ingest_markdown`` when the caller is an LLM-powered agent
    (Copilot, opencode, Claude) that can do semantic chunking and entity
    recognition with its own model — this avoids HydraMem spinning up its own
    LLM and produces higher-quality entities than the regex fallback.

    Payload schema (one element per chunk)::

        {
          "text": "raw chunk text",
          "idx":  0,                                  // optional
          "entities":  [{"name": "...", "type": "..."}],
          "relations": [{"from": "A", "to": "B",
                          "type": "REL", "confidence": 0.8}]   // optional
        }

    Every agent-supplied relation passes through SR-MKG (+ VoG when borderline)
    before being persisted, so hallucinated edges are rejected.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_ingest().ingest_prechunked(
        source=source,
        chunks=chunks,
        doc_id=doc_id or None,
        project=proj,
        session_id=sid,
    )
    _svc_search().invalidate_cache(proj)
    log_event(
        project=proj, tool_name="ingest_prechunked", session_id=sid,
        chunks_total=result.get("chunks_added", 0),
        latency_ms=int((time.time() - start) * 1000),
        metadata={
            "source": source,
            "doc_id": result.get("doc_id"),
            "entities_added": result.get("entities_added", 0),
            "relations_proposed": result.get("relations_proposed", 0),
            "relations_accepted": result.get("relations_accepted", 0),
            "relations_rejected": result.get("relations_rejected", 0),
            "truncated_chunks": result.get("truncated_chunks", 0),
            "truncated_entities": result.get("truncated_entities", 0),
            "truncated_relations": result.get("truncated_relations", 0),
        },
    )
    return result


# ---------------------------------------------------------------------------
# Tool 7b: submit_session_extraction  (agent-closes-session knowledge dump)
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_session_extraction(
    entities: list[dict],
    relations: list[dict],
    session_id: str = "",
    project: str = "",
) -> dict:
    """Persist entities + verified relations extracted by the agent at
    session close.

    No chunks are stored — this is a pure knowledge-graph contribution. Every
    relation goes through SR-MKG (+ VoG when borderline) so hallucinations are
    filtered. Lets a Copilot/opencode session deposit its findings without
    waiting for the offline Night Gardener inference cycle.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_ingest().submit_session_extraction(
        session_id=sid,
        entities=entities,
        relations=relations,
        project=proj,
    )
    log_event(
        project=proj, tool_name="submit_session_extraction", session_id=sid,
        latency_ms=int((time.time() - start) * 1000),
        metadata={
            "entities_added": result.get("entities_added", 0),
            "relations_proposed": result.get("relations_proposed", 0),
            "relations_accepted": result.get("relations_accepted", 0),
            "relations_rejected": result.get("relations_rejected", 0),
        },
    )
    return result


# ---------------------------------------------------------------------------
# Tool 8: list_entities
# ---------------------------------------------------------------------------

@mcp.tool()
def list_entities_tool(project: str = "", session_id: str = "") -> dict:
    """List all entities in the knowledge graph for a given project."""
    proj = _project(project)
    entities = get_store().list_entities(project=proj)
    return {"entities": entities, "count": len(entities), "project": proj}


# ---------------------------------------------------------------------------
# Tool 9: create_relation
# ---------------------------------------------------------------------------

@mcp.tool()
def create_relation(
    from_entity: str,
    to_entity: str,
    relation_type: str,
    confidence: float = 1.0,
    verify: bool = True,
    project: str = "",
    session_id: str = "",
    valid_from: str = "",
    valid_to: str = "",
) -> dict:
    """Manually create a relation edge in the knowledge graph.

    ``valid_from`` / ``valid_to`` (ISO-8601, optional) record temporal validity
    as hyper-relational qualifiers; the edge is stamped ``verifier="manual"``
    (or the actual verifier when ``verify`` runs) for auditable provenance.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    qualifiers: dict[str, str] = {"verifier": "manual"}
    if valid_from:
        qualifiers["valid_from"] = valid_from
    if valid_to:
        qualifiers["valid_to"] = valid_to
    rel = Relation(
        from_entity=from_entity, to_entity=to_entity,
        relation_type=relation_type, confidence=confidence,
        verified=not verify, project=proj,
        session_id=sid, origin_tool="create_relation",
        created_at=datetime.now(timezone.utc).isoformat(),
        qualifiers=qualifiers,
    )
    if verify:
        vr = _svc_verif().verify(rel)
        if not vr.accepted:
            log_event(project=proj, tool_name="create_relation", session_id=sid,
                      was_hallucination_blocked=1,
                      latency_ms=int((time.time() - start) * 1000))
            return {"created": False, "reason": "failed verification",
                    "verification": {"accepted": vr.accepted, "score": vr.score}}
        rel.verified = True
        rel.confidence = vr.score
        _level = getattr(vr, "level", "") or ""
        rel.qualifiers["verifier"] = "vog" if _level.startswith("vog") else "srmkg"

    get_store().add_relation(rel)
    log_event(project=proj, tool_name="create_relation", session_id=sid,
              vog_score=rel.confidence,
              latency_ms=int((time.time() - start) * 1000))
    return {"created": True, "relation": rel.__dict__}


# ---------------------------------------------------------------------------
# Tool 10: delete_relation
# ---------------------------------------------------------------------------

@mcp.tool()
def delete_relation(
    from_entity: str, to_entity: str, relation_type: str,
    project: str = "", session_id: str = ""
) -> dict:
    """Delete a relation edge from the knowledge graph."""
    _project(project)  # honour HYDRAMEM_PROJECT env even if unused below
    deleted = get_store().delete_relation(from_entity, to_entity, relation_type)
    return {"deleted": deleted, "from": from_entity, "to": to_entity}


# ---------------------------------------------------------------------------
# Tool 11: get_entity_neighbors
# ---------------------------------------------------------------------------

@mcp.tool()
def get_entity_neighbors_tool(
    entity_id: str, hops: int = 1, project: str = "", session_id: str = "",
    as_of: str = "",
) -> dict:
    """Return all neighbours of an entity up to N hops away.

    When ``as_of`` (ISO-8601) is set, only neighbours reachable via relations
    whose temporal validity contains that instant are returned.
    """
    proj = _project(project)
    if as_of:
        neighbours = _svc_search().temporal_neighbors(
            entity_id, project=proj, as_of=as_of, hops=hops
        )
    else:
        neighbours = get_store().get_entity_neighbors(entity_id, hops=hops)
    return {
        "entity_id": entity_id, "hops": hops, "as_of": as_of,
        "neighbours": neighbours,
    }


# ---------------------------------------------------------------------------
# Tool 17: query_entity_relations (temporal knowledge-graph query)
# ---------------------------------------------------------------------------

@mcp.tool()
def query_entity_relations(
    entity_id: str, project: str = "", as_of: str = "",
    direction: str = "both", session_id: str = "",
) -> dict:
    """Temporal knowledge-graph query: an entity's relationship facts.

    Returns typed relations with their temporal validity. When ``as_of``
    (ISO-8601 date or datetime) is set, only facts valid at that instant are
    returned; ``direction`` is ``outgoing`` | ``incoming`` | ``both``.
    """
    proj = _project(project)
    facts = _svc_search().entity_relations(
        entity_id, project=proj, as_of=as_of, direction=direction
    )
    return {
        "entity": entity_id, "as_of": as_of, "direction": direction,
        "facts": facts, "count": len(facts),
    }


# ---------------------------------------------------------------------------
# Tool 12: run_night_gardener
# ---------------------------------------------------------------------------

@mcp.tool()
def run_night_gardener(project: str = "", session_id: str = "") -> dict:
    """Run a Night Gardener cycle: infer → verify → prune knowledge graph."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_gardener().run(project=proj)
    _svc_search().invalidate_cache(proj)
    log_event(
        project=proj, tool_name="run_night_gardener", session_id=sid,
        latency_ms=int((time.time() - start) * 1000),
        metadata={
            "relations_accepted": result.get("relations_accepted"),
            "nodes_pruned": result.get("nodes_pruned"),
        },
    )
    return result


# ---------------------------------------------------------------------------
# Tool 13: get_garden_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_garden_status_tool(session_id: str = "") -> dict:
    """Return the current Night Gardener status and cumulative stats."""
    return _svc_gardener().get_status()


# ---------------------------------------------------------------------------
# Tool 14: train_gnn
# ---------------------------------------------------------------------------

@mcp.tool()
def train_gnn_tool(
    project: str = "", dry_run: bool = True, session_id: str = ""
) -> dict:
    """Train LightGNN and optionally apply spurious-edge pruning."""
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    pruner = GNNPruner(get_store())
    result = pruner.analyse(project=proj)
    out = {
        "method": result.method,
        "edges_analysed": result.edges_analysed,
        "suggested_count": result.suggested_count,
        "suggested_edges": [{"from": u, "to": v} for u, v in result.suggested_edges],
    }
    if not dry_run and result.suggested_count > 0:
        out["pruning"] = pruner.apply(result, project=proj, dry_run=False)
    log_event(
        project=proj, tool_name="train_gnn", session_id=sid,
        latency_ms=int((time.time() - start) * 1000),
        metadata={"suggested": result.suggested_count, "dry_run": dry_run},
    )
    return out


# ---------------------------------------------------------------------------
# Tool 15: check_conflict
# ---------------------------------------------------------------------------

@mcp.tool()
def check_conflict_tool(
    entity_a: str, entity_b: str, text_a: str, text_b: str,
    project: str = "", session_id: str = ""
) -> dict:
    """Detect contradictions between two text passages about two entities."""
    from hydramem.llm.factory import create_provider
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    checker = ConflictChecker(create_provider(config))
    result = checker.check(entity_a, entity_b, text_a, text_b)
    _persist_session_entry(
        tool_name="check_conflict",
        project=proj,
        session_id=sid,
        query=f"Check conflict between {entity_a} and {entity_b}",
        summary=(
            f"Conflict check: {entity_a} vs {entity_b}\n"
            f"Conflict: {result.get('conflict', False)}\n"
            f"Confidence: {result.get('confidence', 0.0)}\n"
            f"Explanation: {result.get('explanation', '')}"
        ),
    )
    log_event(
        project=proj, tool_name="check_conflict", session_id=sid,
        llm_preset=config.llm_preset,
        was_hallucination_blocked=1 if result["conflict"] else 0,
        vog_score=result["confidence"],
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


# ---------------------------------------------------------------------------
# Tool 16: get_full_document
# ---------------------------------------------------------------------------

@mcp.tool()
def get_full_document_tool(
    doc_id: str, project: str = "", session_id: str = ""
) -> dict:
    """Retrieve the full text of a document by its doc_id."""
    _project(project)
    text = get_store().get_full_document(doc_id)
    return {"doc_id": doc_id, "text": text, "tokens": count_tokens(text) if text else 0,
            "found": bool(text)}


# ---------------------------------------------------------------------------
# Tool 17: hydramem_stats — agent self-report of token savings
# ---------------------------------------------------------------------------

@mcp.tool()
def hydramem_stats_tool(days: int = 7, session_id: str = "") -> dict:
    """Return aggregated token-savings + Night Gardener metrics.

    Lets MCP clients self-report HydraMem's impact without shelling out to
    the ``hydramem stats`` CLI. Mirrors ``hydramem stats`` JSON output.
    """
    from hydramem.cli import _compute_stats, _load_garden_metrics

    stats = _compute_stats(days=max(1, int(days)))
    if not stats:
        return {"available": False, "period_days": days}
    stats.update(_load_garden_metrics())
    stats["available"] = True
    return stats


# ---------------------------------------------------------------------------
# Tool 18: graph_only_search — native Cypher / graph-only retrieval
# ---------------------------------------------------------------------------

@mcp.tool()
def graph_only_search_tool(
    query: str,
    k: int = 10,
    hops: int = 2,
    project: str = "",
    session_id: str = "",
) -> dict:
    """Pure graph-only search (no vector embeddings).

    Resolves entity names from the query, walks the graph up to ``hops``,
    and returns chunks attached via MENTIONS edges. Useful when the
    embedder is offline or callers need a fully symbolic answer.
    """
    start = time.time()
    proj, sid = _project(project), _session(session_id)
    result = _svc_search().graph_only_search(query, project=proj, max_hops=hops, top_k=k)
    log_event(
        project=proj, tool_name="graph_only_search", session_id=sid,
        chunks_total=len(result.get("chunks", [])),
        latency_ms=int((time.time() - start) * 1000),
    )
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    from hydramem.core.logging import get_logger
    log = get_logger("hydramem")

    transport = os.getenv("HYDRAMEM_TRANSPORT", "streamable-http").lower()
    get_store()  # initialise storage on startup

    if transport in ("stdio", "stdin"):
        log.info("HydraMem MCP server starting on stdio (session=%s)", _SESSION_ID)
        mcp.run(transport="stdio")
        return

    log.info(
        "HydraMem MCP server starting on %s:%s (session=%s, transport=%s)",
        config.mcp_host, config.mcp_port, _SESSION_ID, transport,
    )
    mcp.run(transport=transport, host=config.mcp_host, port=config.mcp_port)


if __name__ == "__main__":
    main()
