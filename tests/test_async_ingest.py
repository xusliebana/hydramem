"""Tests for the AsyncIngestWorker checkpointing flow."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hydramem.ingest.async_worker import AsyncIngestWorker, _file_fingerprint


class _FakePipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ingest_file(self, path: str, project: str = "default") -> dict:
        self.calls.append(path)
        return {"chunks_added": 2, "entities_added": 1}


def _write(p: Path, body: str) -> Path:
    p.write_text(body)
    return p


def test_async_worker_processes_all_files(tmp_path):
    _write(tmp_path / "a.md", "# A")
    _write(tmp_path / "b.md", "# B")
    pipe = _FakePipeline()
    worker = AsyncIngestWorker(pipeline=pipe, max_concurrency=2)

    progress = asyncio.run(worker.ingest_directory(tmp_path, project="t"))

    assert progress.files_total == 2
    assert progress.files_processed == 2
    assert progress.files_skipped == 0
    assert sorted(Path(p).name for p in pipe.calls) == ["a.md", "b.md"]
    assert (tmp_path / ".hydramem-checkpoint.json").exists()


def test_async_worker_resumes_from_checkpoint(tmp_path):
    _write(tmp_path / "a.md", "# A")
    _write(tmp_path / "b.md", "# B")
    pipe = _FakePipeline()
    worker = AsyncIngestWorker(pipeline=pipe, max_concurrency=2)

    asyncio.run(worker.ingest_directory(tmp_path, project="t"))
    pipe.calls.clear()
    progress = asyncio.run(worker.ingest_directory(tmp_path, project="t"))

    assert progress.files_processed == 0
    assert progress.files_skipped == 2
    assert pipe.calls == []


def test_async_worker_reprocesses_changed_files(tmp_path):
    a = _write(tmp_path / "a.md", "# A")
    pipe = _FakePipeline()
    worker = AsyncIngestWorker(pipeline=pipe, max_concurrency=1)
    asyncio.run(worker.ingest_directory(tmp_path, project="t"))

    a.write_text("# A v2 with more content")
    pipe.calls.clear()
    progress = asyncio.run(worker.ingest_directory(tmp_path, project="t"))

    assert progress.files_processed == 1
    assert progress.files_skipped == 0


def test_file_fingerprint_changes_with_content(tmp_path):
    a = _write(tmp_path / "x.md", "hello")
    fp1 = _file_fingerprint(a)
    a.write_text("hello world")
    fp2 = _file_fingerprint(a)
    assert fp1 != fp2


def test_async_worker_missing_dir(tmp_path):
    worker = AsyncIngestWorker(pipeline=_FakePipeline())
    with pytest.raises(FileNotFoundError):
        asyncio.run(worker.ingest_directory(tmp_path / "nope"))
