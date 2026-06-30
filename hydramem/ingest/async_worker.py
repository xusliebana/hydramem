"""AsyncIngestWorker — bounded-concurrency ingest with on-disk checkpointing.

Designed for corpora that exceed the size where a synchronous walk is
practical (>50k documents per the roadmap). Every successfully ingested file
is recorded in a JSON checkpoint so re-running the worker resumes from where
it stopped instead of re-processing everything.

Concurrency is bounded with a semaphore and the underlying synchronous
``IngestionPipeline.ingest_file`` call is dispatched to a thread so the loop
never blocks on the tokenizer or embedder.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from hydramem.core.logging import get_logger
from hydramem.ingest.pipeline import IngestionPipeline

logger = get_logger(__name__)

_DEFAULT_CHECKPOINT_NAME = ".hydramem-checkpoint.json"


@dataclass
class IngestProgress:
    files_total: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    chunks_added: int = 0
    entities_added: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def as_dict(self) -> dict:
        return {**self.__dict__}


class AsyncIngestWorker:
    """Resumable async ingest of a Markdown corpus.

    Public methods are awaitable. The worker is stateless across runs apart
    from the on-disk checkpoint, so it is safe to crash and restart.
    """

    def __init__(
        self,
        pipeline: IngestionPipeline | None = None,
        *,
        max_concurrency: int = 4,
        checkpoint_path: Path | None = None,
    ) -> None:
        self._pipeline = pipeline or IngestionPipeline()
        self._sem = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._checkpoint_path = checkpoint_path

    # ── Public API ────────────────────────────────────────────────────────────

    async def ingest_directory(
        self,
        directory: str | Path,
        *,
        project: str = "default",
        recursive: bool = True,
        glob: str | None = None,
    ) -> IngestProgress:
        """Ingest every Markdown file under *directory*, resuming if possible."""
        root = Path(directory)
        if not root.exists():
            raise FileNotFoundError(f"Directory not found: {root}")

        pattern = glob or ("**/*.md" if recursive else "*.md")
        files = sorted(root.glob(pattern))
        checkpoint = self._load_checkpoint(root)
        progress = IngestProgress(files_total=len(files))

        async def _run(path: Path) -> None:
            digest = _file_fingerprint(path)
            if checkpoint.get(str(path)) == digest:
                progress.files_skipped += 1
                return
            async with self._sem:
                try:
                    result = await asyncio.to_thread(self._pipeline.ingest_file, str(path), project)
                except Exception as exc:  # noqa: BLE001
                    logger.error("AsyncIngestWorker failed on %s: %s", path, exc)
                    progress.files_failed += 1
                    return
                progress.chunks_added += int(result.get("chunks_added", 0))
                progress.entities_added += int(result.get("entities_added", 0))
                progress.files_processed += 1
                checkpoint[str(path)] = digest
                # Flush checkpoint every successful file so a crash never
                # loses more than one document of progress.
                self._save_checkpoint(root, checkpoint)

        await asyncio.gather(*(_run(p) for p in files))
        progress.finished_at = time.time()
        return progress

    # ── Checkpointing ─────────────────────────────────────────────────────────

    def _checkpoint_for(self, root: Path) -> Path:
        return self._checkpoint_path or (root / _DEFAULT_CHECKPOINT_NAME)

    def _load_checkpoint(self, root: Path) -> dict[str, str]:
        path = self._checkpoint_for(root)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Checkpoint %s unreadable (%s); starting fresh", path, exc)
            return {}

    def _save_checkpoint(self, root: Path, data: dict[str, str]) -> None:
        path = self._checkpoint_for(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
        tmp.replace(path)


def _file_fingerprint(path: Path) -> str:
    """Return a cheap stable digest combining size + content hash."""
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"{path.stat().st_size}:{h.hexdigest()}"
