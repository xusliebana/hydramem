#!/usr/bin/env python3
"""HydraMem Dogfood Script — HydraMem eats its own documentation.

Ingests all Markdown in docs/ and kms/ into HydraMem's own knowledge graph,
then optionally runs a Night Gardener cycle and a self-query smoke test.

Usage:
    uv run python scripts/dogfood.py [--skip-garden] [--project hydramem]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from hydramem.core.logging import get_logger
from hydramem.garden.gardener import NightGardener
from hydramem.ingest.pipeline import IngestionPipeline
from hydramem.search import SearchService

PROJECT_ROOT = Path(__file__).parent.parent

logger = get_logger("hydramem.dogfood")

try:
    from rich import box as rbox
    from rich.console import Console
    from rich.table import Table

    console = Console()
    _RICH = True
except ImportError:
    _RICH = False


def _panel(title: str, subtitle: str = "") -> None:
    if _RICH:
        from rich.panel import Panel

        console.print(
            Panel(subtitle or title, title=title if subtitle else "", border_style="cyan")
        )
    else:
        print(f"\n{'=' * 50}\n{title}\n{'=' * 50}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest HydraMem docs into itself.")
    p.add_argument("--project", default="hydramem")
    p.add_argument("--skip-garden", action="store_true")
    p.add_argument("--dirs", nargs="+", default=["docs", "kms", "README.md"])
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    _panel("HydraMem – Dogfooding Pipeline", "Ingesting own docs into the knowledge base")

    pipeline = IngestionPipeline()
    total_chunks = 0
    total_entities = 0
    files_processed = 0
    t0 = time.time()

    for path_str in args.dirs:
        path = PROJECT_ROOT / path_str
        if not path.exists():
            logger.warning("Path not found, skipping: %s", path)
            continue
        try:
            if path.is_file():
                result = pipeline.ingest_file(str(path), project=args.project)
                total_chunks += result["chunks_added"]
                total_entities += result["entities_added"]
                files_processed += 1
                if _RICH:
                    console.print(
                        f"  ✓  {path}: {result['chunks_added']} chunks, "
                        f"{result['entities_added']} entities"
                    )
            elif path.is_dir():
                result = pipeline.ingest_directory(str(path), project=args.project)
                total_chunks += result["chunks_added"]
                total_entities += result["entities_added"]
                files_processed += result["files_processed"]
                if _RICH:
                    console.print(
                        f"  ✓  {path}: {result['chunks_added']} chunks, "
                        f"{result['entities_added']} entities"
                    )
        except Exception as exc:
            logger.error("Failed to ingest %s: %s", path, exc)

    elapsed = time.time() - t0

    if _RICH:
        t = Table("Metric", "Value", box=rbox.SIMPLE, title="Dogfood Summary")
        t.add_row("Files processed", str(files_processed))
        t.add_row("Chunks added", str(total_chunks))
        t.add_row("Entities extracted", str(total_entities))
        t.add_row("Elapsed", f"{elapsed:.1f}s")
        console.print(t)
    else:
        print(
            f"Files: {files_processed}, Chunks: {total_chunks}, "
            f"Entities: {total_entities}, Elapsed: {elapsed:.1f}s"
        )

    if not args.skip_garden:
        _panel("Night Gardener", "Running autonomous refinement cycle…")
        gardener = NightGardener()
        gstatus = gardener.run(project=args.project)
        logger.info("Gardener: %s", gstatus)

    # Smoke test
    print("\nRunning self-query to verify retrieval…")
    svc = SearchService()
    result = svc.priming_context("What is the Night Gardener?", project=args.project, k=3)
    n = len(result["chunks"])
    print(f"  ✓  Retrieved {n} chunks for test query")
    print("Dogfooding complete. HydraMem now knows itself.")


if __name__ == "__main__":
    main()
