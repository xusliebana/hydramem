"""Smoke + signal test for the self-contained retrieval benchmark.

Runs entirely offline with the stub embedder, so it doubles as a regression
guard that the benchmark harness keeps working.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_benchmark():
    path = Path(__file__).resolve().parent.parent / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("hydra_benchmark", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so the module's dataclasses can resolve __module__.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_local_benchmark_runs_and_bm25_helps(monkeypatch):
    # Force the offline stub embedder so the test never downloads a model.
    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")

    bench = _load_benchmark()
    data_dir = Path(__file__).resolve().parent.parent / "scripts" / "bench_data"
    report = bench.run_local(data_dir, k=5)

    assert report["questions"] == 10
    conds = report["conditions"]
    assert set(conds) == {"vector_only", "hybrid_no_bm25", "hybrid_full"}

    # Every metric is a valid fraction.
    for cond in conds.values():
        for key in ("recall_at_1", "recall_at_3", "recall_at_5", "mrr"):
            assert 0.0 <= cond[key] <= 1.0

    # The keyword-aligned fixture is recalled by BM25 even with the offline
    # stub embedder (near-random dense vectors), and the full hybrid ranks the
    # relevant doc better than dense-only — an honest, reproducible signal that
    # the lexical arm earns its place.
    full = conds["hybrid_full"]
    assert full["recall_at_5"] >= 0.7
    assert full["mrr"] >= 0.4
    assert full["mrr"] > conds["vector_only"]["mrr"]


def test_local_benchmark_llm_judge_with_mock(monkeypatch):
    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")
    bench = _load_benchmark()
    data_dir = Path(__file__).resolve().parent.parent / "scripts" / "bench_data"

    class _MockJudge:
        def complete(self, prompt):
            return "ANSWERED\nCONFIDENCE: 0.9"

    report = bench.run_local(data_dir, k=5, judge_provider=_MockJudge())
    assert report["judge"]["enabled"] is True
    for cond in report["conditions"].values():
        assert cond["judge_coverage"] == 1.0          # mock answers every query
        assert cond["judge_answered"] == 1.0          # all judged ANSWERED


def test_local_benchmark_judge_unavailable_is_honest(monkeypatch):
    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")
    bench = _load_benchmark()
    data_dir = Path(__file__).resolve().parent.parent / "scripts" / "bench_data"

    class _DeadJudge:
        def complete(self, prompt):
            return ""   # LLM unavailable

    report = bench.run_local(data_dir, k=5, judge_provider=_DeadJudge())
    for cond in report["conditions"].values():
        assert cond["judge_coverage"] == 0.0
        assert cond["judge_answered"] is None         # honest: no fabricated score


# ---------------------------------------------------------------------------
# Dataset-scale benchmark (offline, synthetic normalized dataset)
# ---------------------------------------------------------------------------

_SYNTHETIC_DATASET = {
    "corpus": {
        "doc_apple": "The Granny Smith apple is a green cultivar grown in orchards.",
        "doc_moon": "The Apollo program landed astronauts on the Moon in 1969.",
        "doc_python": "Python is a programming language created by Guido van Rossum.",
        "distractor_fruit": "Bananas are tropical fruits rich in potassium.",
        "distractor_ocean": "The Pacific Ocean is the largest ocean on Earth.",
    },
    "items": [
        {"id": "q1", "question": "Which green apple cultivar is grown in orchards?",
         "answer": "Granny Smith", "gold_doc_ids": ["doc_apple"]},
        {"id": "q2", "question": "Which program landed astronauts on the Moon?",
         "answer": "Apollo", "gold_doc_ids": ["doc_moon"]},
        {"id": "q3", "question": "Who created the Python programming language?",
         "answer": "Guido van Rossum", "gold_doc_ids": ["doc_python"]},
    ],
}


def test_dataset_benchmark_runs_offline(monkeypatch, tmp_path):
    import dataclasses

    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")
    # Isolate Night-Gardener disk state (status / sessions) to a temp dir.
    monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path / "ng"))

    bench = _load_benchmark()
    report = bench.run_dataset(_SYNTHETIC_DATASET, name="synthetic", k=5, cycles=1)
    data = dataclasses.asdict(report)

    assert data["dataset"] == "synthetic"
    names = [c["name"] for c in data["conditions"]]
    assert names == ["naive_topk", "hydra_search_no_garden", "hydra_search_garden"]
    for cond in data["conditions"]:
        assert cond["questions"] == 3
        assert 0.0 <= cond["recall_at_5"] <= 1.0
        assert cond["avg_tokens_injected"] >= 0.0
        assert cond["p95_latency_ms"] >= 0.0

    # The lexical (BM25) arm recalls keyword-aligned gold docs even with the
    # offline stub embedder — an honest, reproducible signal.
    hybrid = next(c for c in data["conditions"] if c["name"] == "hydra_search_no_garden")
    assert hybrid["recall_at_5"] >= 0.6


def test_dataset_benchmark_judge_mock(monkeypatch, tmp_path):
    monkeypatch.setenv("HYDRAMEM_EMBEDDER", "stub")
    monkeypatch.setenv("HYDRAMEM_DATA_DIR", str(tmp_path / "ng"))
    bench = _load_benchmark()

    class _MockJudge:
        def complete(self, prompt):
            return "ANSWERED"

    report = bench.run_dataset(
        _SYNTHETIC_DATASET, name="synthetic", k=5,
        conditions=["naive_topk"], judge_provider=_MockJudge(),
    )
    cond = report.conditions[0]
    assert cond.factual_accuracy == 1.0          # mock answers everything
    assert cond.hallucination_rate == 0.0


def test_resolve_dataset_from_file(monkeypatch, tmp_path):
    import argparse

    bench = _load_benchmark()
    path = tmp_path / "norm.json"
    path.write_text(__import__("json").dumps(_SYNTHETIC_DATASET))
    args = argparse.Namespace(
        from_file=str(path), dataset="musique", limit=2, refresh=False
    )
    data = bench._resolve_dataset(args)
    assert len(data["items"]) == 2                # limited
    assert len(data["corpus"]) == 5              # corpus kept whole (distractors)


def test_render_markdown_and_narrative():
    bench = _load_benchmark()
    report = bench.BenchmarkReport(
        dataset="synthetic", git_commit="abc123", llm_model="stub:x",
        judge_model="none", timestamp="2026-06-30T00:00:00Z",
    )
    report.conditions = [
        bench.ConditionResult(name="naive_topk", questions=3, recall_at_5=0.3),
        bench.ConditionResult(name="hydra_search_no_garden", questions=3, recall_at_5=0.6),
        bench.ConditionResult(name="hydra_search_garden", questions=3, recall_at_5=0.6),
    ]
    md = bench._render_markdown(__import__("dataclasses").asdict(report))
    assert "# Benchmark report — synthetic" in md
    assert "naive_topk" in md
    assert "Recall@5 by +0.300" in md            # hybrid vs naive narrative


def test_unavailable_dataset_loader_is_honest():
    bench = _load_benchmark()
    import pytest

    with pytest.raises(bench.BenchmarkDataError):
        bench._DATASET_LOADERS["musique"]()
