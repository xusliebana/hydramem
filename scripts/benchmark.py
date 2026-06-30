"""Reproducible benchmark harness for HydraMem (scaffold).

This is intentionally a *skeleton*: it wires the CLI and the high-level shape
of the experiment but does not yet download datasets or call a judge model.
See ``docs/benchmarks.md`` for the contract we want this script to fulfil.

Run with ``uv run python scripts/benchmark.py --help``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ConditionResult:
    name: str
    questions: int = 0
    recall_at_5: float = 0.0
    factual_accuracy: float = 0.0
    hallucination_rate: float = 0.0
    avg_tokens_injected: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    dataset: str
    git_commit: str
    llm_model: str
    judge_model: str
    timestamp: str
    conditions: list[ConditionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset-scale benchmark (LongMemEval / MuSiQue / HotpotQA)
# ---------------------------------------------------------------------------
#
# Datasets are normalized to a single on-disk schema so the evaluator is
# dataset-agnostic and fully offline-testable:
#
#     {"corpus": {doc_id: text, ...},
#      "items": [{"id", "question", "answer", "gold_doc_ids": [doc_id, ...]}]}
#
# Nothing is shipped in the repo; loaders download on demand into a cache dir.
# Datasets without a stable direct-download URL raise an honest error pointing
# the user at ``--from-file`` rather than silently fabricating data.


class BenchmarkDataError(RuntimeError):
    """A dataset could not be obtained locally; use ``--from-file``."""


def _bench_cache_dir() -> Path:
    base = os.getenv("HYDRAMEM_BENCH_CACHE")
    root = Path(base) if base else (Path.home() / ".cache" / "hydramem" / "bench")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "x"


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    import requests  # lazy: only needed for live downloads

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for block in resp.iter_content(chunk_size=1 << 20):
                if block:
                    fh.write(block)
    tmp.replace(dest)
    return dest


def _validate_normalized(data: dict) -> None:
    if not isinstance(data, dict) or "corpus" not in data or "items" not in data:
        raise BenchmarkDataError("Normalized dataset must be an object with 'corpus' and 'items'.")


def _normalize_hotpotqa(raw: list[dict]) -> dict:
    """HotpotQA distractor split → normalized schema (per-question corpus)."""
    corpus: dict[str, str] = {}
    items: list[dict] = []
    for ex in raw:
        qid = _slug(ex.get("_id") or ex.get("id") or len(items))
        gold_titles = {t for t, _ in ex.get("supporting_facts", [])}
        gold_doc_ids: list[str] = []
        for title, sentences in ex.get("context", []):
            doc_id = f"{qid}__{_slug(title)}"
            corpus[doc_id] = " ".join(sentences)
            if title in gold_titles:
                gold_doc_ids.append(doc_id)
        items.append(
            {
                "id": qid,
                "question": ex.get("question", ""),
                "answer": ex.get("answer", ""),
                "gold_doc_ids": gold_doc_ids,
            }
        )
    return {"corpus": corpus, "items": items}


def _load_hotpotqa() -> dict:
    url = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"
    dest = _bench_cache_dir() / "hotpot_dev_distractor_v1.json"
    try:
        _download(url, dest)
    except Exception as exc:  # noqa: BLE001
        raise BenchmarkDataError(
            f"Could not download HotpotQA ({exc}). Fetch it from {url}, normalize "
            f"it, and pass --from-file."
        ) from exc
    return _normalize_hotpotqa(json.loads(dest.read_text()))


def _unavailable_loader(name: str, url: str):
    def _loader() -> dict:
        raise BenchmarkDataError(
            f"{name} has no stable direct-download URL. Download it from {url}, "
            'convert it to the normalized schema ({"corpus": {doc_id: text}, '
            '"items": [{"id","question","answer","gold_doc_ids"}]}), and pass it '
            "via --from-file."
        )

    return _loader


_DATASET_LOADERS = {
    "hotpotqa": _load_hotpotqa,
    "musique": _unavailable_loader("MuSiQue", "https://github.com/StonyBrookNLP/musique"),
    "longmemeval": _unavailable_loader("LongMemEval", "https://github.com/xiaowu0162/LongMemEval"),
}


def _resolve_dataset(args: argparse.Namespace) -> dict:
    """Return a normalized dataset from --from-file, the cache, or a loader."""
    if getattr(args, "from_file", None):
        data = json.loads(Path(args.from_file).read_text())
        _validate_normalized(data)
    else:
        cache = _bench_cache_dir() / f"{args.dataset}.normalized.json"
        if cache.exists() and not getattr(args, "refresh", False):
            data = json.loads(cache.read_text())
        else:
            data = _DATASET_LOADERS[args.dataset]()
            cache.write_text(json.dumps(data))
    limit = getattr(args, "limit", None)
    if limit:
        # Keep the full corpus (all distractors) — limit only the questions.
        data = {"corpus": data["corpus"], "items": data["items"][:limit]}
    return data


# ── Evaluation ────────────────────────────────────────────────────────────


def _count_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:  # noqa: BLE001
        return len(text.split())


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def _run_gardener(store, cfg, project: str, cycles: int, notes: list[str]) -> int:
    """Run N Night-Gardener cycles on *store*; never fakes success (honesty)."""
    try:
        from hydramem.garden.gardener import NightGardener

        gardener = NightGardener(store=store, config=cfg)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"night-gardener unavailable: {exc}")
        return 0
    ran = 0
    for _ in range(cycles):
        try:
            gardener.run(project=project)
            ran += 1
        except Exception as exc:  # noqa: BLE001
            notes.append(f"night-gardener cycle failed: {exc}")
            break
    return ran


def _evaluate(name, retrieve, items, k, judge_provider) -> ConditionResult:
    cr = ConditionResult(name=name, questions=len(items))
    if not items:
        cr.notes.append("no items")
        return cr
    recall = 0.0
    tokens = 0.0
    latencies: list[float] = []
    judged = 0
    answered = 0
    for item in items:
        t0 = time.perf_counter()
        retrieved = retrieve(item["question"])
        latencies.append((time.perf_counter() - t0) * 1000.0)
        metrics = _eval_one(retrieved, set(item.get("gold_doc_ids", [])))
        recall += metrics["hit@5"]
        context = "\n\n".join(_chunk_text(c) for c in retrieved[:k])
        tokens += _count_tokens(context)
        if judge_provider is not None:
            verdict = _judge_answerable(item["question"], context, judge_provider)
            if verdict != "UNAVAILABLE":
                judged += 1
                answered += 1 if verdict == "ANSWERED" else 0
    n = len(items)
    cr.recall_at_5 = round(recall / n, 4)
    cr.avg_tokens_injected = round(tokens / n, 1)
    cr.p50_latency_ms = round(_percentile(latencies, 50), 1)
    cr.p95_latency_ms = round(_percentile(latencies, 95), 1)
    if judge_provider is None:
        cr.notes.append("no judge — retrieval / latency / token metrics only")
    elif judged:
        cr.factual_accuracy = round(answered / judged, 4)
        cr.hallucination_rate = round(1.0 - answered / judged, 4)
        cr.notes.append(f"judge coverage {judged}/{n}")
    else:
        cr.notes.append("judge unavailable — no faithfulness score (honest)")
    return cr


def _run_condition(name, dataset, cfg, *, project, k, cycles, judge_provider) -> ConditionResult:
    """Ingest the corpus into a fresh ephemeral store and evaluate one condition."""
    from hydramem.ingest.pipeline import IngestionPipeline
    from hydramem.search import SearchService
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    store = KnowledgeStore(graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository())
    pipeline = IngestionPipeline(store=store, config=cfg)
    for doc_id, text in dataset["corpus"].items():
        pipeline.ingest_text(text, source=doc_id, project=project)

    svc = SearchService(store=store, config=cfg)
    notes: list[str] = []

    if name == "naive_topk":

        def retrieve(q: str):
            return store.vector_search(svc._embedder.embed(q, is_query=True), k=k, project=project)
    elif name in ("hydra_search_no_garden", "hydra_search_garden"):
        if name == "hydra_search_garden":
            ran = _run_gardener(store, cfg, project, cycles, notes)
            notes.append(f"night-gardener cycles run: {ran}")

        def retrieve(q: str):
            return svc.hydra_search(q, project=project, top_k=k)["chunks"]
    else:
        raise BenchmarkDataError(f"Unknown condition {name!r}")

    cr = _evaluate(name, retrieve, dataset["items"], k, judge_provider)
    cr.notes.extend(notes)
    return cr


def run_dataset(
    dataset: dict,
    *,
    name: str = "custom",
    project: str = "bench_dataset",
    k: int = 5,
    cycles: int = 3,
    conditions: list[str] | None = None,
    judge_provider=None,
) -> BenchmarkReport:
    """Evaluate a normalized dataset across the ablation conditions.

    Conditions: ``naive_topk`` (vector-only), ``hydra_search_no_garden`` (full
    hybrid + verification), ``hydra_search_garden`` (same, after *cycles*
    Night-Gardener runs). Pass a *judge_provider* (``complete(prompt) -> str``)
    to add an LLM-judged faithfulness metric. Honest by construction: an
    unavailable judge yields no score instead of a fabricated one.
    """
    from hydramem.core.config import load_config

    cfg = load_config()
    conditions = conditions or [
        "naive_topk",
        "hydra_search_no_garden",
        "hydra_search_garden",
    ]
    report = BenchmarkReport(
        dataset=name,
        git_commit=_git_commit(),
        llm_model=(
            f"{getattr(cfg, 'embedding_backend', 'auto')}:{getattr(cfg, 'embedding_model', '?')}"
        ),
        judge_model="enabled" if judge_provider is not None else "none",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    for cond in conditions:
        report.conditions.append(
            _run_condition(
                cond,
                dataset,
                cfg,
                project=project,
                k=k,
                cycles=cycles,
                judge_provider=judge_provider,
            )
        )
    return report


# ── Reporting ─────────────────────────────────────────────────────────────


def _narrative(data: dict) -> str:
    conds = {c["name"]: c for c in data["conditions"]}
    naive = conds.get("naive_topk")
    nogarden = conds.get("hydra_search_no_garden")
    garden = conds.get("hydra_search_garden")
    parts: list[str] = []
    if naive and nogarden:
        d = nogarden["recall_at_5"] - naive["recall_at_5"]
        verb = "improves" if d > 0 else ("matches" if d == 0 else "reduces")
        parts.append(f"Hybrid + verification {verb} Recall@5 by {d:+.3f} vs naive top-k.")
    if nogarden and garden:
        d = garden["recall_at_5"] - nogarden["recall_at_5"]
        verb = "lifts" if d > 0 else ("does not move" if d == 0 else "lowers")
        parts.append(f"The Night Gardener {verb} Recall@5 by {d:+.3f} (ON vs OFF).")
    parts.append(
        "Numbers are reported as measured; where a component does not move the "
        "needle this is stated rather than hidden (honesty contract)."
    )
    return " ".join(parts)


def _render_markdown(data: dict) -> str:
    lines = [
        f"# Benchmark report — {data['dataset']}\n",
        f"- Commit: `{data['git_commit']}`",
        f"- Retriever / embedder: `{data['llm_model']}`",
        f"- Judge: `{data['judge_model']}`",
        f"- When: {data['timestamp']}\n",
        "| Condition | Q | R@5 | Faithful | Halluc% | Tok (avg) | p50 ms | p95 ms |",
        "|-----------|---|-----|----------|---------|-----------|--------|--------|",
    ]
    for c in data["conditions"]:
        lines.append(
            f"| {c['name']} | {c['questions']} | {c['recall_at_5']:.3f} |"
            f" {c['factual_accuracy']:.3f} | {c['hallucination_rate'] * 100:.1f} |"
            f" {c['avg_tokens_injected']:.0f} | {c['p50_latency_ms']:.0f} |"
            f" {c['p95_latency_ms']:.0f} |"
        )
    lines.append("")
    lines.append(_narrative(data))
    return "\n".join(lines)


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        data = _resolve_dataset(args)
    except BenchmarkDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    cache = _bench_cache_dir() / f"{args.dataset}.normalized.json"
    cache.write_text(json.dumps(data))
    print(
        f"Prepared {args.dataset}: {len(data['items'])} questions, "
        f"{len(data['corpus'])} corpus docs → {cache}"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        dataset = _resolve_dataset(args)
    except BenchmarkDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    judge_provider = None
    if getattr(args, "judge", False):
        from hydramem.llm.factory import create_provider

        judge_provider = create_provider()
    report = run_dataset(
        dataset,
        name=args.dataset,
        project=args.project,
        k=args.k,
        cycles=args.cycles,
        conditions=args.conditions,
        judge_provider=judge_provider,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(report), indent=2))
    print(f"Wrote report to {out}\n")
    print(_render_markdown(asdict(report)))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.report).read_text())
    print(_render_markdown(data))
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    try:
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Self-contained offline retrieval benchmark (no downloads, no LLM judge)
# ---------------------------------------------------------------------------


class _PassthroughPipeline:
    """Verification no-op so the benchmark measures *retrieval*, not VoG."""

    def reset_vog_cap(self) -> None:  # noqa: D401
        pass

    def verify_chunks(self, chunks: list, query: str = "") -> dict:
        return {
            "filtered": list(chunks),
            "verified": [],
            "rejected_vector": [],
            "rejected_srmkg": [],
            "rejected_vog": [],
            "vog_scores": [],
        }


def _doc_stem(chunk_like) -> str:
    src = (
        chunk_like.get("source", "")
        if isinstance(chunk_like, dict)
        else getattr(chunk_like, "source", "")
    )
    return Path(src).stem if src else ""


def _eval_one(retrieved: list, relevant: set[str]) -> dict:
    """Rank-based metrics for one query against its relevant doc stems."""
    stems: list[str] = []
    for chunk in retrieved:
        stem = _doc_stem(chunk)
        if stem and stem not in stems:
            stems.append(stem)
    rank = next((i + 1 for i, s in enumerate(stems) if s in relevant), None)
    return {
        "hit@1": 1.0 if rank == 1 else 0.0,
        "hit@3": 1.0 if rank is not None and rank <= 3 else 0.0,
        "hit@5": 1.0 if rank is not None and rank <= 5 else 0.0,
        "rr": (1.0 / rank) if rank else 0.0,
    }


_JUDGE_PROMPT = """\
You are a retrieval grader. Decide whether the CONTEXT contains the information
needed to answer the QUESTION.

QUESTION: {query}

CONTEXT:
\"\"\"
{context}
\"\"\"

Answer with exactly one of:
  ANSWERED  - the context clearly contains the answer.
  PARTIAL   - related but insufficient.
  NO        - the context does not answer the question.
"""


def _chunk_text(chunk_like) -> str:
    return (
        chunk_like.get("text", "")
        if isinstance(chunk_like, dict)
        else getattr(chunk_like, "text", "")
    )


def _judge_answerable(query: str, context: str, provider) -> str:
    """Ask an LLM whether *context* answers *query*.

    Honest contract (mirrors VoG): empty context -> NO; an unavailable / empty
    LLM -> UNAVAILABLE, never a fabricated score. Returns one of
    ANSWERED / PARTIAL / NO / UNAVAILABLE.
    """
    if not (context or "").strip():
        return "NO"
    try:
        answer = provider.complete(_JUDGE_PROMPT.format(query=query, context=context[:2000]))
    except Exception:
        answer = ""
    if not answer:
        return "UNAVAILABLE"
    upper = answer.upper()
    if "ANSWERED" in upper:
        return "ANSWERED"
    if "PARTIAL" in upper:
        return "PARTIAL"
    return "NO"


def run_local(data_dir: Path, k: int = 5, judge_provider=None) -> dict:
    """Run the shipped, self-contained retrieval benchmark. Returns a report.

    Ingests the fixture corpus into an isolated in-memory store and measures
    Recall@{1,3,5} + MRR for three ablation conditions (vector-only, hybrid
    without BM25, full hybrid). No network, no dataset download. Pass a
    *judge_provider* (any object with ``complete(prompt) -> str``) to layer on
    an LLM-judged answerability metric. Honest by construction: it is a small
    sanity benchmark, **not** a SOTA dataset claim.
    """
    from hydramem.core.config import load_config
    from hydramem.ingest.pipeline import IngestionPipeline
    from hydramem.search import SearchService
    from hydramem.storage.factory import KnowledgeStore
    from hydramem.storage.graph.networkx_repo import NetworkXGraphRepository
    from hydramem.storage.vector.memory_repo import InMemoryVectorRepository

    queries = json.loads((data_dir / "queries.json").read_text())
    corpus_dir = data_dir / "corpus"

    cfg = load_config()
    store = KnowledgeStore(graph=NetworkXGraphRepository(), vector=InMemoryVectorRepository())
    pipeline = IngestionPipeline(store=store, config=cfg)
    project = "bench_local"
    for md in sorted(corpus_dir.glob("*.md")):
        pipeline.ingest_file(str(md), project=project)

    svc = SearchService(store=store, config=cfg, pipeline=_PassthroughPipeline())

    def _vector_only(query: str) -> list:
        return store.vector_search(svc._embedder.embed(query, is_query=True), k=k, project=project)

    def _hybrid(query: str, *, bm25: bool) -> list:
        svc._bm25_enabled = bm25
        return svc.hydra_search(query, project=project, top_k=k, traversal="bfs")["chunks"]

    conditions = {
        "vector_only": _vector_only,
        "hybrid_no_bm25": lambda q: _hybrid(q, bm25=False),
        "hybrid_full": lambda q: _hybrid(q, bm25=True),
    }

    report: dict = {
        "benchmark": "local-fixture",
        "git_commit": _git_commit(),
        "embedder_backend": getattr(cfg, "embedding_backend", "auto"),
        "embedding_model": getattr(cfg, "embedding_model", "?"),
        "k": k,
        "questions": len(queries),
        "judge": {"enabled": judge_provider is not None},
        "conditions": {},
    }
    n = len(queries) or 1
    for name, fn in conditions.items():
        agg = {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0, "mrr": 0.0}
        judged = 0
        answered = 0
        for q in queries:
            retrieved = fn(q["query"])
            metrics = _eval_one(retrieved, set(q["relevant"]))
            agg["recall_at_1"] += metrics["hit@1"]
            agg["recall_at_3"] += metrics["hit@3"]
            agg["recall_at_5"] += metrics["hit@5"]
            agg["mrr"] += metrics["rr"]
            if judge_provider is not None:
                context = "\n\n".join(_chunk_text(c) for c in retrieved[:k])
                verdict = _judge_answerable(q["query"], context, judge_provider)
                if verdict != "UNAVAILABLE":
                    judged += 1
                    if verdict == "ANSWERED":
                        answered += 1
        cond = {key: round(val / n, 4) for key, val in agg.items()}
        if judge_provider is not None:
            cond["judge_coverage"] = round(judged / n, 4)
            cond["judge_answered"] = round(answered / judged, 4) if judged else None
        report["conditions"][name] = cond
    return report


def cmd_local(args: argparse.Namespace) -> int:
    data_dir = Path(args.data) if args.data else (Path(__file__).parent / "bench_data")
    judge_provider = None
    if args.judge:
        from hydramem.llm.factory import create_provider

        judge_provider = create_provider()
    report = run_local(data_dir, k=args.k, judge_provider=judge_provider)
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {out}")
    print(
        f"\nLocal retrieval benchmark — {report['questions']} questions, "
        f"k={report['k']}, embedder={report['embedder_backend']} "
        f"({report['embedding_model']})"
    )
    judging = report["judge"]["enabled"]
    if judging:
        print("\n| Condition | R@1 | R@3 | R@5 | MRR | Judge answered (coverage) |")
        print("|-----------|-----|-----|-----|-----|---------------------------|")
    else:
        print("\n| Condition | R@1 | R@3 | R@5 | MRR |")
        print("|-----------|-----|-----|-----|-----|")
    for name, m in report["conditions"].items():
        row = (
            f"| {name} | {m['recall_at_1']:.3f} | {m['recall_at_3']:.3f} |"
            f" {m['recall_at_5']:.3f} | {m['mrr']:.3f} |"
        )
        if judging:
            ja = m.get("judge_answered")
            cov = m.get("judge_coverage", 0.0)
            ja_str = f"{ja:.3f}" if ja is not None else "n/a (no LLM)"
            row += f" {ja_str} ({cov:.2f}) |"
        print(row)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="Download + normalize a dataset into the bench cache")
    p_ing.add_argument("--dataset", choices=["musique", "longmemeval", "hotpotqa"], required=True)
    p_ing.add_argument("--project", default="bench")
    p_ing.add_argument(
        "--from-file",
        dest="from_file",
        default=None,
        help="Use a pre-built normalized dataset JSON (offline / reproducible)",
    )
    p_ing.add_argument("--limit", type=int, default=None, help="Cap the number of questions")
    p_ing.add_argument("--refresh", action="store_true", help="Ignore the cache and re-download")
    p_ing.set_defaults(func=cmd_ingest)

    p_run = sub.add_parser("run", help="Run benchmark conditions on a dataset")
    p_run.add_argument("--dataset", choices=["musique", "longmemeval", "hotpotqa"], required=True)
    p_run.add_argument("--project", default="bench_dataset")
    p_run.add_argument(
        "--conditions",
        nargs="+",
        default=["naive_topk", "hydra_search_no_garden", "hydra_search_garden"],
    )
    p_run.add_argument("-k", type=int, default=5, help="Top-k cutoff (default: 5)")
    p_run.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Night Gardener cycles for the garden condition (default: 3)",
    )
    p_run.add_argument(
        "--judge",
        action="store_true",
        help="Add an LLM-judged faithfulness metric (honest 'no LLM' fallback)",
    )
    p_run.add_argument(
        "--from-file",
        dest="from_file",
        default=None,
        help="Use a pre-built normalized dataset JSON (offline / reproducible)",
    )
    p_run.add_argument("--limit", type=int, default=None, help="Cap the number of questions")
    p_run.add_argument("--refresh", action="store_true", help="Ignore the cache and re-download")
    p_run.add_argument("--output", default="reports/run.json")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report", help="Render a Markdown summary")
    p_rep.add_argument("report")
    p_rep.set_defaults(func=cmd_report)

    p_local = sub.add_parser(
        "local",
        help="Self-contained offline retrieval benchmark (no downloads, no judge)",
    )
    p_local.add_argument(
        "--data",
        default=None,
        help="Override fixture dir (default: scripts/bench_data)",
    )
    p_local.add_argument("-k", type=int, default=5, help="Top-k cutoff (default: 5)")
    p_local.add_argument(
        "--judge",
        action="store_true",
        help="Add an LLM-judged answerability metric (uses the configured LLM; "
        "honestly reports 'no LLM' when unavailable)",
    )
    p_local.add_argument("--json", default=None, help="Also write the raw report JSON to this path")
    p_local.set_defaults(func=cmd_local)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
