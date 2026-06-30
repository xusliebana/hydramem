"""Federated knowledge — signed exports / imports between trusted peers.

Goal: let two HydraMem installations exchange a project (entities + relations
+ chunk metadata) over plain files without trusting the transport.

We sign exports with HMAC-SHA256 using a per-peer shared secret. The format
is a small JSON envelope::

    {
        "format": "hydramem-export",
        "version": 1,
        "project": "default",
        "created_at": "2026-05-08T10:00:00+00:00",
        "issuer": "alice",
        "payload": {...},
        "signature": "<hex hmac of canonical JSON of envelope w/o signature>"
    }

HMAC was chosen over Ed25519 to keep the dependency surface at "stdlib only".
The roadmap allows upgrading to asymmetric signatures later — the envelope
carries an ``algo`` field so the verifier can reject anything it does not
support.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hydramem.core.types import Chunk, Entity, Relation
from hydramem.storage.factory import KnowledgeStore, get_store

_FORMAT = "hydramem-export"
_VERSION = 1
_DEFAULT_ALGO = "hmac-sha256"


# ---------------------------------------------------------------------------
# Signing helpers
# ---------------------------------------------------------------------------


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def _sign(payload: dict[str, Any], secret: bytes, algo: str = _DEFAULT_ALGO) -> str:
    if algo != _DEFAULT_ALGO:
        raise ValueError(f"Unsupported signing algorithm: {algo}")
    return hmac.new(secret, _canonical(payload), hashlib.sha256).hexdigest()


def _verify(payload: dict[str, Any], signature: str, secret: bytes, algo: str) -> bool:
    expected = _sign(payload, secret, algo=algo)
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_project(
    out_path: str | Path,
    *,
    project: str = "default",
    issuer: str = "local",
    secret: bytes | str,
    store: KnowledgeStore | None = None,
) -> dict:
    """Export entities + relations + chunks for *project* to a signed JSON file."""
    s = store or get_store()
    payload = {
        "entities": s.list_entities(project=project),
        "relations": s.list_relations(project=project),
        "chunks": [c.__dict__ for c in s.get_all_chunks() if c.project == project],
    }

    envelope: dict[str, Any] = {
        "format": _FORMAT,
        "version": _VERSION,
        "algo": _DEFAULT_ALGO,
        "project": project,
        "issuer": issuer,
        "created_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    secret_bytes = secret.encode() if isinstance(secret, str) else secret
    envelope["signature"] = _sign(
        {k: v for k, v in envelope.items() if k != "signature"}, secret_bytes
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(envelope, indent=2, default=str))

    return {
        "wrote": str(out),
        "entities": len(payload["entities"]),
        "relations": len(payload["relations"]),
        "chunks": len(payload["chunks"]),
    }


def import_project(
    in_path: str | Path,
    *,
    secret: bytes | str,
    project: str | None = None,
    store: KnowledgeStore | None = None,
    accept_issuers: list[str] | None = None,
) -> dict:
    """Verify and import a previously exported project file.

    Raises ``ValueError`` if the envelope is malformed, the signature does
    not match, or the issuer is not in *accept_issuers* (when provided).
    """
    envelope = json.loads(Path(in_path).read_text())
    if envelope.get("format") != _FORMAT:
        raise ValueError(f"Not a HydraMem export: {envelope.get('format')!r}")
    if int(envelope.get("version", 0)) != _VERSION:
        raise ValueError(f"Unsupported export version: {envelope.get('version')}")

    algo = envelope.get("algo", _DEFAULT_ALGO)
    issuer = envelope.get("issuer", "")
    if accept_issuers is not None and issuer not in accept_issuers:
        raise ValueError(f"Issuer {issuer!r} not in accept list {accept_issuers!r}")

    signature = envelope.get("signature", "")
    secret_bytes = secret.encode() if isinstance(secret, str) else secret
    body = {k: v for k, v in envelope.items() if k != "signature"}
    if not _verify(body, signature, secret_bytes, algo):
        raise ValueError("Signature verification failed")

    target_project = project or envelope.get("project", "default")
    payload = envelope.get("payload", {}) or {}

    s = store or get_store()
    imported = {"entities": 0, "relations": 0, "chunks": 0}
    for raw in payload.get("entities", []):
        s.add_entity(
            Entity(
                id=raw["id"],
                name=raw.get("name", ""),
                type=raw.get("type", "concept"),
                project=target_project,
            )
        )
        imported["entities"] += 1

    for raw in payload.get("chunks", []):
        chunk = Chunk(
            id=raw["id"],
            text=raw.get("text", ""),
            source=raw.get("source", ""),
            chunk_idx=int(raw.get("chunk_idx", 0)),
            doc_id=raw.get("doc_id", ""),
            project=target_project,
        )
        # Imported chunks are stored without an embedding because the issuer
        # might have used a different model. The next ingest cycle (or a
        # dedicated re-embed job) will rebuild the vector index.
        try:
            s._graph.add_chunk(chunk)  # type: ignore[attr-defined]
            imported["chunks"] += 1
        except Exception:  # noqa: BLE001
            pass

    for raw in payload.get("relations", []):
        s.add_relation(
            Relation(
                from_entity=raw.get("from") or raw.get("from_entity", ""),
                to_entity=raw.get("to") or raw.get("to_entity", ""),
                relation_type=raw.get("relation_type", "related_to"),
                confidence=float(raw.get("confidence", 0.0) or 0.0),
                verified=bool(raw.get("verified", False)),
                project=target_project,
                session_id=raw.get("session_id", ""),
                origin_tool=raw.get("origin_tool", "federation_import"),
                created_at=raw.get("created_at", ""),
                qualifiers=raw.get("qualifiers") or {},
            )
        )
        imported["relations"] += 1

    return {
        "imported": imported,
        "issuer": issuer,
        "source_project": envelope.get("project"),
        "target_project": target_project,
    }
