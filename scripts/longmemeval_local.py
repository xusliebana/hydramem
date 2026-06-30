"""Faithful local LongMemEval retrieval benchmark (per-question haystack).

For each question we ingest ONLY that question's haystack sessions — the native
LongMemEval setting, with real distractors — then measure session-level
Recall@{1,3,5} + MRR for:

  - ``naive_topk``            : dense vector top-k only
  - ``hydra_search_no_garden``: HydraMem hybrid (vector + graph BFS + BM25, RRF)

Real HydraMem primitives, real embedder (loaded once and shared across all
questions), 100% local. By default a *passthrough* verification pipeline is used
so we measure **retrieval** (not VoG) and avoid slow LLM round-trips — Recall is
computed on the retrieved ranking either way. Pass ``--with-vog`` to include
verification.

Honest by construction: no LLM judge here, so only retrieval metrics are
reported (answer accuracy needs the full judged pipeline — a different metric).

Usage:
    uv run python scripts/longmemeval_local.py --n 100 --k 20 \
        --output reports/longmemeval-local.json
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import time
from pathlib import Path


class _PassthroughPipeline:
    """No-op verifier so the benchmark measures retrieval, not VoG."""

    def reset_vog_cap(self) -> None:
        pass

    def verify_chunks(self, chunks: list, query: str = "") -> dict:
        return {
            "filtered": list(chunks), "verified": [], "rejected_vector": [],
            "rejected_srmkg": [], "rejected_vog": [], "vog_scores": [],
        }


def _session_text(turns: list[dict]) -> str:
    return "\n".join(f"{t.get('role', '')}: {t.get('content', '')}" for t in turns)


def _distinct_sessions(retrieved, limit: int) -> list[str]:
    out: list[str] = []
    for c in retrieved:
        src = c.get("source", "") if isinstance(c, dict) else getattr(c, "source", "")
        stem = Path(src).stem if src else ""
        if stem and stem not in out:
            out.append(stem)
        if len(out) >= limit:
            break
    return out


def _metrics(retrieved, gold: set[str]) -> dict:
    sessions = _distinct_sessions(retrieved, 5)
    rank = next((i + 1 for i, s in enumerate(sessions) if s in gold), None)
    return {
        "r@1": 1.0 if rank == 1 else 0.0,
        "r@3": 1.0 if rank and rank <= 3 else 0.0,
        "r@5": 1.0 if rank and rank <= 5 else 0.0,
        "rr": (1.0 / rank) if rank else 0.0,
    }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1))))]


def run(n: int, k: int, *, variant: str = "s", with_vog: bool = False) -> dict:
    from huggingface_hub import hf_hub_download

    from hydramem.core.config import load_config
    from hydramem.ingest.embedder import EmbeddingService
    from hydramem.ingest.pipeline import IngestionPipeline
    from hydramem.search import SearchService
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    path = hf_hub_download(
        "xiaowu0162/longmemeval", f"longmemeval_{variant}", repo_type="dataset"
    )
    data = json.load(open(path))[:n]
    cfg = load_config()
    # Load the embedder ONCE and share it across every question (the model
    # reload per question is what makes a naive driver crawl).
    embedder = EmbeddingService(
        cfg.embedding_model, dim=cfg.embedding_dim,
        backend=getattr(cfg, "embedding_backend", None),
    )

    conds: dict[str, list] = {"naive_topk": [], "hydra_search_no_garden": []}
    lat: dict[str, list] = {"naive_topk": [], "hydra_search_no_garden": []}
    hay: list[int] = []
    t0 = time.time()
    for qi, q in enumerate(data):
        sessions, sids = q["haystack_sessions"], q["haystack_session_ids"]
        gold = set(q["answer_session_ids"])
        hay.append(len(sessions))

        store = KnowledgeStore(
            graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository()
        )
        pipe = IngestionPipeline(store=store, config=cfg, embedder=embedder)
        for sid, turns in zip(sids, sessions, strict=False):
            pipe.ingest_text(_session_text(turns), source=sid, project="lme")
        svc = SearchService(
            store=store, config=cfg, embedder=embedder,
            pipeline=None if with_vog else _PassthroughPipeline(),
        )

        emb = embedder.embed(q["question"], is_query=True)
        s = time.perf_counter()
        naive = store.vector_search(emb, k=k, project="lme")
        lat["naive_topk"].append((time.perf_counter() - s) * 1000)

        s = time.perf_counter()
        hyb = svc.hydra_search(q["question"], project="lme", top_k=k)["chunks"]
        lat["hydra_search_no_garden"].append((time.perf_counter() - s) * 1000)

        conds["naive_topk"].append(_metrics(naive, gold))
        conds["hydra_search_no_garden"].append(_metrics(hyb, gold))
        if (qi + 1) % 10 == 0:
            print(f"  ...{qi + 1}/{len(data)} ({time.time() - t0:.0f}s)", flush=True)

    def agg(name: str, key: str) -> float:
        rows = conds[name]
        return round(sum(m[key] for m in rows) / max(len(rows), 1), 3)

    report = {
        "benchmark": f"longmemeval_{variant}-local",
        "setting": "faithful per-question haystack (native LongMemEval setting)",
        "source": f"huggingface: xiaowu0162/longmemeval (longmemeval_{variant})",
        "embedder": f"{getattr(cfg, 'embedding_backend', '?')}:"
                    f"{getattr(cfg, 'embedding_model', '?')}",
        "questions": len(data),
        "haystack_sessions_per_question": {
            "min": min(hay), "median": int(st.median(hay)), "max": max(hay)},
        "retrieve_k_chunks": k,
        "metric": "session-level Recall over top-5 distinct sessions; MRR",
        "judge": False,
        "verification": "vog" if with_vog else "passthrough (retrieval-only)",
        "elapsed_seconds": round(time.time() - t0, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conditions": {},
    }
    for name, desc in (
        ("naive_topk", "dense vector top-k only"),
        ("hydra_search_no_garden", "HydraMem hybrid: vector + graph BFS + BM25, RRF"),
    ):
        ms = lat[name]
        report["conditions"][name] = {
            "description": desc,
            "recall_at_1": agg(name, "r@1"), "recall_at_3": agg(name, "r@3"),
            "recall_at_5": agg(name, "r@5"), "mrr": agg(name, "rr"),
            "p50_latency_ms": round(_percentile(ms, 50), 1),
            "p95_latency_ms": round(_percentile(ms, 95), 1),
        }
    return report


def _print_table(report: dict) -> None:
    h = report["haystack_sessions_per_question"]
    print(f"\n# {report['benchmark']} — faithful per-question haystack")
    print(f"- questions: {report['questions']} | sessions/q "
          f"{h['min']}/{h['median']}/{h['max']} | embedder {report['embedder']} | "
          f"verify {report['verification']} | {report['elapsed_seconds']}s")
    print("| Condition | R@1 | R@3 | R@5 | MRR | p50 ms | p95 ms |")
    print("|-----------|-----|-----|-----|-----|--------|--------|")
    for name, c in report["conditions"].items():
        print(f"| {name} | {c['recall_at_1']} | {c['recall_at_3']} | {c['recall_at_5']} "
              f"| {c['mrr']} | {c['p50_latency_ms']:.0f} | {c['p95_latency_ms']:.0f} |")


def main() -> None:
    ap = argparse.ArgumentParser(description="Local LongMemEval retrieval benchmark")
    ap.add_argument("--n", type=int, default=50, help="Number of questions")
    ap.add_argument("--k", type=int, default=20, help="Chunks retrieved per query")
    ap.add_argument("--variant", default="s", choices=["s", "oracle", "m"])
    ap.add_argument("--with-vog", dest="with_vog", action="store_true",
                    help="Include VoG verification (slower; needs a local LLM)")
    ap.add_argument("--output", default=None, help="Write the JSON report here")
    args = ap.parse_args()

    report = run(args.n, args.k, variant=args.variant, with_vog=args.with_vog)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {out}")
    _print_table(report)


if __name__ == "__main__":
    main()
