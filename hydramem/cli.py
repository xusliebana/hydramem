"""HydraMem CLI – `hydramem stats` and `hydramem telemetry` subcommands.

Usage examples:
    hydramem stats --last-7d
    hydramem stats --days 30 --export md
    hydramem stats --days 30 --export csv
    hydramem garden-status
    hydramem telemetry --show
    hydramem telemetry --wipe
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from hydramem.core.config import hydramem_home

# Lazy import rich to avoid failure if not installed yet
try:
    from rich import box
    from rich.console import Console
    from rich.table import Table

    _RICH = True
except ImportError:  # pragma: no cover
    _RICH = False


CONFIG_PATH = hydramem_home() / "config.json"
_COST_PER_1M = 5.0  # USD per 1M tokens (conservative estimate)

# Embedded default config written by `hydramem init` (config.yml.example is not
# shipped inside the installed package, so the template lives here).
_DEFAULT_CONFIG_YML = """\
# HydraMem configuration
# Docs: https://github.com/xusliebana/hydramem/blob/main/docs/configuration.md
# API keys MUST come from environment variables — never hardcode secrets here.

llm:
  provider: auto            # auto | local | ollama | openai | anthropic
  local:
    model: gemma4:e4b
    endpoint: http://localhost:11434
  external:
    provider: openai        # openai | anthropic
    api_key_env: HYDRAMEM_OPENAI_KEY
    model: gpt-4o-mini

embedding:
  model: nomic-ai/nomic-embed-text-v1.5
  dim: 512                  # Nomic v1.5 (768-d) truncated + renormalised; 256 also fine
  backend: auto             # auto | fastembed | sentence-transformers | stub

storage:
  # Tip: set HYDRAMEM_DATA_DIR (e.g. /data in Docker) to root every store,
  # the metrics DB and the session log under a single directory.
  ladybug_db: ./data/hydramem.graph
  lancedb: ./data/lancedb
  knowledge_dir: ./kms

server:
  host: 0.0.0.0
  port: 3000
"""


# ---------------------------------------------------------------------------
# First-run opt-in prompt
# ---------------------------------------------------------------------------


def _ensure_config() -> dict:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:  # noqa: BLE001
            pass

    cfg: dict = {"telemetry_opt_in": False, "first_run_done": False}

    if sys.stdin.isatty():
        print("\nHydraMem collects ONLY anonymised aggregate metrics (no content, no queries).")
        print("These help improve the project. All data stays local unless you opt in.")
        ans = input("Share anonymous aggregate metrics? [y/N] ").strip().lower()
        cfg["telemetry_opt_in"] = ans in ("y", "yes")
        cfg["first_run_done"] = True
    else:
        cfg["first_run_done"] = True

    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return cfg


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


def _cost(tokens: int) -> float:
    return round(tokens / 1_000_000 * _COST_PER_1M, 4)


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _compute_stats(days: int, project: str | None = None) -> dict:
    from hydramem.telemetry.storage import query_stats

    raw = query_stats(days=days, project=project)
    if not raw:
        return {}

    baseline = int(raw.get("total_baseline") or 0)
    injected = int(raw.get("total_injected") or 0)
    saved = max(0, baseline - injected)
    pct = round(saved / baseline * 100, 1) if baseline else 0.0

    return {
        "period_days": days,
        "period_start": raw.get("period_start", "—"),
        "period_end": raw.get("period_end", "—"),
        "projects": raw.get("projects", "default"),
        "total_calls": int(raw.get("total_calls") or 0),
        "tokens_without_hydramem": baseline,
        "tokens_injected": injected,
        "tokens_saved": saved,
        "savings_pct": pct,
        "cost_saved_usd": _cost(saved),
        "avg_vog_score": round(float(raw.get("avg_vog") or 0.0), 4),
        # NOTE: ``rejected_srmkg`` here aggregates the chunks dropped by the
        # vector-similarity prefilter inside ``verify_chunks`` (see
        # ``hydramem/verification/pipeline.py``). The DB column name is kept for
        # backward compatibility with v0.1.x; the CLI label now reflects the
        # true semantics.
        "rejected_vector_prefilter": int(raw.get("rejected_srmkg") or 0),
        "rejected_srmkg": int(raw.get("rejected_srmkg") or 0),  # DEPRECATED alias
        "rejected_vog": int(raw.get("rejected_vog") or 0),
        "cross_project_hits": int(raw.get("cross_hits") or 0),
        "hallucinations_blocked": int(raw.get("hallucinations_blocked") or 0),
    }


def _load_garden_metrics() -> dict:
    from hydramem.garden.repository import StatusRepository

    status = StatusRepository().load()
    return {
        "garden_last_run": status.get("last_run") or "—",
        "garden_total_runs": int(status.get("total_runs") or 0),
        "garden_relations_proposed": int(status.get("relations_proposed") or 0),
        "garden_relations_accepted": int(status.get("relations_accepted") or 0),
        "garden_relations_rejected": int(status.get("relations_rejected") or 0),
        "garden_entries_filtered_repeat_threshold": int(
            status.get("session_entries_filtered_repeat_threshold") or 0
        ),
        "garden_nodes_pruned": int(status.get("nodes_pruned") or 0),
        "garden_edges_pruned": int(status.get("edges_pruned") or 0),
    }


# ---------------------------------------------------------------------------
# Stats command
# ---------------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> None:
    _ensure_config()

    days = args.days if hasattr(args, "days") and args.days else 7
    project = getattr(args, "project", None)

    stats = _compute_stats(days, project=project)
    if not stats:
        print(f"No telemetry data found for the last {days} days.")
        print("Run `hydramem-server` and make some queries to collect data.")
        return

    stats.update(_load_garden_metrics())

    export_fmt = getattr(args, "export", None)

    if getattr(args, "raw", False):
        # Show the un-aggregated baseline so the savings % is auditable.
        from hydramem.telemetry.storage import _connect, init_db

        init_db()
        sql = (
            "SELECT ts, tool_name, tokens_baseline, tokens_injected,"
            " chunks_total, chunks_rejected_srmkg AS rejected_vector_prefilter,"
            " chunks_rejected_vog, vog_score, latency_ms"
            " FROM events"
            " WHERE ts >= datetime('now', :delta)"
        )
        params: dict[str, str] = {"delta": f"-{days} days"}
        project = getattr(args, "project", None)
        if project:
            sql += " AND project = :project"
            params["project"] = project
        sql += " ORDER BY ts DESC LIMIT 500"
        import sqlite3 as _sql

        with _connect() as conn:
            conn.row_factory = _sql.Row
            rows = conn.execute(sql, params).fetchall()
        print(json.dumps([dict(r) for r in rows], indent=2, default=str))
        return

    if export_fmt == "csv":
        _export_csv(stats)
        return
    if export_fmt == "md":
        _export_md(stats)
        return

    # Rich table output
    if _RICH:
        _print_rich_table(stats, days)
    else:
        _print_plain_table(stats, days)

    # Auto-send aggregate if opted in
    try:
        from hydramem.telemetry.aggregate import send_aggregate_if_opted_in

        send_aggregate_if_opted_in(stats)
    except Exception:  # noqa: BLE001
        pass


def _print_rich_table(stats: dict, days: int) -> None:
    console = Console()
    t = Table(title=f"HydraMem Stats – last {days} days", box=box.ROUNDED, show_header=True)
    t.add_column("Metric", style="bold cyan", no_wrap=True)
    t.add_column("Value", justify="right")

    rows = [
        ("Period", f"{stats['period_start'][:10]} → {stats['period_end'][:10]}"),
        ("Projects", stats["projects"] or "—"),
        ("Tool calls", str(stats["total_calls"])),
        ("─" * 30, "─" * 15),
        ("Tokens (naive RAG)", _fmt_tokens(stats["tokens_without_hydramem"])),
        ("Tokens injected", _fmt_tokens(stats["tokens_injected"])),
        ("Tokens saved", f"[green]{_fmt_tokens(stats['tokens_saved'])}[/green]"),
        ("Savings %", f"[green]{stats['savings_pct']}%[/green]"),
        ("Cost saved (est.)", f"[green]${stats['cost_saved_usd']:.4f}[/green]"),
        ("─" * 30, "─" * 15),
        ("Avg VoG score", f"{stats['avg_vog_score']:.3f}"),
        (
            "Rejected (vector prefilter)",
            str(stats.get("rejected_vector_prefilter", stats.get("rejected_srmkg", 0))),
        ),
        ("Rejected by VoG", str(stats["rejected_vog"])),
        ("Cross-project hits", str(stats["cross_project_hits"])),
        ("Hallucinations blocked", str(stats["hallucinations_blocked"])),
        ("─" * 30, "─" * 15),
        ("Garden last run", str(stats["garden_last_run"])),
        ("Garden total runs", str(stats["garden_total_runs"])),
        (
            "Garden entries filtered",
            str(stats["garden_entries_filtered_repeat_threshold"]),
        ),
        ("Garden nodes pruned", str(stats["garden_nodes_pruned"])),
        ("Garden edges pruned", str(stats["garden_edges_pruned"])),
    ]

    for label, value in rows:
        if label.startswith("─"):
            t.add_section()
        else:
            t.add_row(label, value)

    console.print()
    console.print(t)
    console.print()


def _print_plain_table(stats: dict, days: int) -> None:
    print(f"\nHydraMem Stats – last {days} days")
    print("=" * 50)
    print(f"  Period:               {stats['period_start'][:10]} → {stats['period_end'][:10]}")
    print(f"  Projects:             {stats['projects']}")
    print(f"  Tool calls:           {stats['total_calls']}")
    print(f"  Tokens (naive RAG):   {_fmt_tokens(stats['tokens_without_hydramem'])}")
    print(f"  Tokens injected:      {_fmt_tokens(stats['tokens_injected'])}")
    print(f"  Tokens saved:         {_fmt_tokens(stats['tokens_saved'])} ({stats['savings_pct']}%)")
    print(f"  Cost saved (est.):    ${stats['cost_saved_usd']:.4f}")
    print(f"  Avg VoG score:        {stats['avg_vog_score']:.3f}")
    _vec_pref = stats.get("rejected_vector_prefilter", stats.get("rejected_srmkg", 0))
    print(f"  Rejected vector pref: {_vec_pref}")
    print(f"  Rejected VoG:         {stats['rejected_vog']}")
    print(f"  Cross-project hits:   {stats['cross_project_hits']}")
    print(f"  Hallucinations blkd:  {stats['hallucinations_blocked']}")
    print(f"  Garden last run:      {stats['garden_last_run']}")
    print(f"  Garden total runs:    {stats['garden_total_runs']}")
    print(f"  Garden entries filt:  {stats['garden_entries_filtered_repeat_threshold']}")
    print(f"  Garden nodes pruned:  {stats['garden_nodes_pruned']}")
    print(f"  Garden edges pruned:  {stats['garden_edges_pruned']}")
    print()


def _export_csv(stats: dict) -> None:
    writer = csv.writer(sys.stdout)
    writer.writerow(stats.keys())
    writer.writerow(stats.values())


def _export_md(stats: dict) -> None:
    lines = [
        f"# HydraMem Stats – last {stats['period_days']} days",
        "",
        f"**Period:** {stats['period_start'][:10]} → {stats['period_end'][:10]}  ",
        f"**Projects:** {stats['projects']}  ",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Tool calls | {stats['total_calls']} |",
        f"| Tokens (naive RAG) | {_fmt_tokens(stats['tokens_without_hydramem'])} |",
        f"| Tokens injected | {_fmt_tokens(stats['tokens_injected'])} |",
        f"| **Tokens saved** | **{_fmt_tokens(stats['tokens_saved'])} ({stats['savings_pct']}%)** |",
        f"| Cost saved (est.) | ${stats['cost_saved_usd']:.4f} |",
        f"| Avg VoG score | {stats['avg_vog_score']:.3f} |",
        f"| Rejected (vector prefilter) | "
        f"{stats.get('rejected_vector_prefilter', stats.get('rejected_srmkg', 0))} |",
        f"| Rejected VoG | {stats['rejected_vog']} |",
        f"| Cross-project hits | {stats['cross_project_hits']} |",
        f"| Hallucinations blocked | {stats['hallucinations_blocked']} |",
        f"| Garden last run | {stats['garden_last_run']} |",
        f"| Garden total runs | {stats['garden_total_runs']} |",
        f"| Garden entries filtered | {stats['garden_entries_filtered_repeat_threshold']} |",
        f"| Garden nodes pruned | {stats['garden_nodes_pruned']} |",
        f"| Garden edges pruned | {stats['garden_edges_pruned']} |",
    ]
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Garden status command
# ---------------------------------------------------------------------------


def cmd_garden_status(args: argparse.Namespace) -> None:
    from hydramem.garden.repository import StatusRepository

    status = StatusRepository().load()
    if getattr(args, "json", False):
        print(json.dumps(status, indent=2))
        return

    if _RICH:
        _print_garden_status_rich(status)
    else:
        _print_garden_status_plain(status)


def _print_garden_status_rich(status: dict) -> None:
    console = Console()
    t = Table(title="HydraMem Night Gardener Status", box=box.ROUNDED, show_header=True)
    t.add_column("Metric", style="bold cyan", no_wrap=True)
    t.add_column("Value", justify="right")

    rows = [
        ("Last run", str(status.get("last_run") or "—")),
        ("Is running", str(bool(status.get("is_running", False)))),
        ("Total runs", str(int(status.get("total_runs") or 0))),
        ("─" * 30, "─" * 15),
        ("Relations proposed", str(int(status.get("relations_proposed") or 0))),
        ("Relations accepted", str(int(status.get("relations_accepted") or 0))),
        ("Relations rejected", str(int(status.get("relations_rejected") or 0))),
        ("─" * 30, "─" * 15),
        (
            "Entries filtered by repeat threshold",
            str(int(status.get("session_entries_filtered_repeat_threshold") or 0)),
        ),
        ("Nodes pruned", str(int(status.get("nodes_pruned") or 0))),
        ("Edges pruned", str(int(status.get("edges_pruned") or 0))),
        ("─" * 30, "─" * 15),
        ("Entities boosted", str(int(status.get("entities_boosted") or 0))),
        ("Entities decayed", str(int(status.get("entities_decayed") or 0))),
        ("Prune protected", str(int(status.get("prune_protected") or 0))),
        ("Prune reviews queued", str(int(status.get("prune_reviews_queued") or 0))),
    ]

    for label, value in rows:
        if label.startswith("─"):
            t.add_section()
        else:
            t.add_row(label, value)

    console.print()
    console.print(t)
    console.print()


def _print_garden_status_plain(status: dict) -> None:
    print("\nHydraMem Night Gardener Status")
    print("=" * 50)
    print(f"  Last run:                         {status.get('last_run') or '—'}")
    print(f"  Is running:                       {bool(status.get('is_running', False))}")
    print(f"  Total runs:                       {int(status.get('total_runs') or 0)}")
    print(f"  Relations proposed:               {int(status.get('relations_proposed') or 0)}")
    print(f"  Relations accepted:               {int(status.get('relations_accepted') or 0)}")
    print(f"  Relations rejected:               {int(status.get('relations_rejected') or 0)}")
    print(
        "  Entries filtered repeat thresh:   "
        f"{int(status.get('session_entries_filtered_repeat_threshold') or 0)}"
    )
    print(f"  Nodes pruned:                     {int(status.get('nodes_pruned') or 0)}")
    print(f"  Edges pruned:                     {int(status.get('edges_pruned') or 0)}")
    print(f"  Entities boosted:                 {int(status.get('entities_boosted') or 0)}")
    print(f"  Entities decayed:                 {int(status.get('entities_decayed') or 0)}")
    print(f"  Prune protected:                  {int(status.get('prune_protected') or 0)}")
    print(f"  Prune reviews queued:             {int(status.get('prune_reviews_queued') or 0)}")
    print()


# ---------------------------------------------------------------------------
# Projects command
# ---------------------------------------------------------------------------


def cmd_projects(args: argparse.Namespace) -> None:
    """List all known projects from telemetry events and the knowledge store."""
    from hydramem.telemetry.storage import list_projects

    projects = set(list_projects())

    # Also check the knowledge store for projects that have entities but no
    # telemetry yet (e.g. freshly imported via federation).
    try:
        from hydramem.storage.factory import get_store

        store = get_store()
        if hasattr(store, "list_projects"):
            projects.update(store.list_projects())
    except Exception:  # noqa: BLE001
        pass

    sorted_projects = sorted(projects)

    if getattr(args, "json", False):
        print(json.dumps(sorted_projects, indent=2))
        return

    if not sorted_projects:
        print("No projects found. Ingest some documents or start the MCP server.")
        return

    if _RICH:
        console = Console()
        t = Table(title="HydraMem Projects", box=box.ROUNDED, show_header=True)
        t.add_column("#", style="dim", justify="right")
        t.add_column("Project", style="bold cyan")
        for i, p in enumerate(sorted_projects, 1):
            t.add_row(str(i), p)
        console.print()
        console.print(t)
        console.print()
    else:
        print("\nHydraMem Projects")
        print("=" * 30)
        for i, p in enumerate(sorted_projects, 1):
            print(f"  {i}. {p}")
        print()


# ---------------------------------------------------------------------------
# Telemetry command
# ---------------------------------------------------------------------------


def cmd_telemetry(args: argparse.Namespace) -> None:
    project = getattr(args, "project", None)

    if getattr(args, "show", False):
        _ensure_config()
        stats = _compute_stats(days=30, project=project)
        print(json.dumps(stats, indent=2))

    elif getattr(args, "wipe", False):
        from hydramem.telemetry.storage import DB_PATH

        if DB_PATH.exists():
            confirm = "y"
            if sys.stdin.isatty():
                confirm = input(f"Delete {DB_PATH}? [y/N] ").strip().lower()
            if confirm in ("y", "yes"):
                DB_PATH.unlink()
                print(f"Deleted {DB_PATH}")
            else:
                print("Aborted.")
        else:
            print("No metrics database found.")

    elif getattr(args, "send", False):
        from hydramem.telemetry.aggregate import send_aggregate_if_opted_in

        stats = _compute_stats(days=30, project=project)
        sent = send_aggregate_if_opted_in(stats)
        if sent:
            print("Aggregate metrics sent.")
        else:
            print("Not sent (not opted in or endpoint unreachable).")

    elif getattr(args, "opt_in", False):
        from hydramem.telemetry.aggregate import set_opt_in

        set_opt_in(True)
        print("Opted in to anonymous aggregate telemetry.")

    elif getattr(args, "opt_out", False):
        from hydramem.telemetry.aggregate import set_opt_in

        set_opt_in(False)
        print("Opted out of anonymous aggregate telemetry.")

    else:
        print("Use --show, --wipe, --send, --opt-in, or --opt-out.")


# ---------------------------------------------------------------------------
# New commands: ingest-async, sessions-merge, export/import, dashboard
# ---------------------------------------------------------------------------


def cmd_ingest_async(args: argparse.Namespace) -> None:
    import asyncio

    from hydramem.ingest.async_worker import AsyncIngestWorker

    worker = AsyncIngestWorker(
        max_concurrency=args.concurrency,
        checkpoint_path=Path(args.checkpoint) if args.checkpoint else None,
    )
    progress = asyncio.run(
        worker.ingest_directory(args.directory, project=args.project, recursive=args.recursive)
    )
    print(json.dumps(progress.as_dict(), indent=2, default=str))


def cmd_sessions_merge(args: argparse.Namespace) -> None:
    from hydramem.garden.crdt import merge_session_files

    summary = merge_session_files(args.local, args.remote, out_path=args.out)
    print(json.dumps(summary, indent=2))


def _federation_secret(env_name: str) -> bytes:
    import os

    val = os.getenv(env_name)
    if not val:
        print(
            f"Missing shared secret: set ${env_name} to the HMAC key agreed with the peer.",
            file=sys.stderr,
        )
        sys.exit(2)
    return val.encode()


def cmd_export(args: argparse.Namespace) -> None:
    from hydramem.storage.federation import export_project

    secret = _federation_secret(args.secret_env)
    summary = export_project(
        args.output,
        project=args.project,
        issuer=args.issuer,
        secret=secret,
    )
    print(json.dumps(summary, indent=2))


def cmd_import(args: argparse.Namespace) -> None:
    from hydramem.storage.federation import import_project

    secret = _federation_secret(args.secret_env)
    try:
        summary = import_project(
            args.input,
            secret=secret,
            project=args.project,
            accept_issuers=args.accept_issuer,
        )
    except ValueError as exc:
        print(f"Import rejected: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(summary, indent=2))


def cmd_dashboard(args: argparse.Namespace) -> None:
    from hydramem.dashboard import serve

    serve(host=args.host, port=args.port, days=args.days)


def cmd_calibrate_srmkg(args: argparse.Namespace) -> None:
    from dataclasses import asdict

    from hydramem.verification.calibration import calibrate

    try:
        report = calibrate(
            project=args.project,
            min_samples=args.min_samples,
            test_fraction=args.test_fraction,
            l2=args.l2,
            lr=args.lr,
            epochs=args.epochs,
            save=not args.dry_run,
        )
    except RuntimeError as exc:
        print(f"calibrate-srmkg refused: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# Human-in-the-loop prune review + learned-pruner training
# ---------------------------------------------------------------------------


def cmd_review(args: argparse.Namespace) -> None:
    """Label queued spurious-edge prune candidates (builds the golden dataset)."""
    from hydramem.garden.review import PruneReviewStore

    store = PruneReviewStore()
    project = args.project

    if args.export:
        n = store.export_jsonl(project, args.export)
        print(f"Exported {n} labelled row(s) → {args.export}")
        return

    stats = store.stats(project)
    if args.status:
        print(json.dumps(stats, indent=2))
        return

    pending = store.pending(project, limit=args.limit)
    if not pending:
        print(
            f"No pending prune reviews for project '{project}'. "
            f"(labelled={stats['labeled']}, prune={stats['prune']}, keep={stats['keep']})"
        )
        return

    print(
        f"{len(pending)} candidate(s) to review for '{project}'. For each edge: "
        "[p]rune (spurious), [k]eep (valid), [s]kip, [q]uit.\n"
    )
    labelled = 0
    for row in pending:
        left = row["from_name"] or row["from_id"]
        right = row["to_name"] or row["to_id"]
        print(f"#{row['id']}  {left} ──[{row['rel_type'] or 'rel'}]──▶ {right}")
        print(f"     spuriousness={row['spuriousness']:.2f}  features={row['features']}")
        try:
            ans = input("     prune/keep/skip/quit [p/k/s/q]? ").strip().lower()
        except EOFError:
            break
        if ans in ("q", "quit"):
            break
        if ans in ("p", "prune"):
            store.label(row["id"], "prune")
            labelled += 1
        elif ans in ("k", "keep"):
            store.label(row["id"], "keep")
            labelled += 1

    print(
        f"\nLabelled {labelled} this session. Train the scorer with: "
        f"hydramem train-pruner --project {project}"
    )


def cmd_train_pruner(args: argparse.Namespace) -> None:
    """Train the learned spurious-edge scorer from the labelled golden dataset."""
    from dataclasses import asdict

    from hydramem.garden.prune_trainer import train_pruner

    try:
        report = train_pruner(
            project=args.project,
            min_samples=args.min_samples,
            test_fraction=args.test_fraction,
            l2=args.l2,
            lr=args.lr,
            epochs=args.epochs,
            save=not args.dry_run,
        )
    except RuntimeError as exc:
        print(f"train-pruner refused: {exc}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(asdict(report), indent=2))


# ---------------------------------------------------------------------------
# init / ingest / search / serve — primary workflow verbs
# ---------------------------------------------------------------------------


def _prompt_provider() -> str:
    """Interactive LLM-provider picker used by `hydramem init`."""
    options = {
        "1": ("auto", "Ollama if running, else external API (recommended)"),
        "2": ("local", "Local Ollama only — fully offline"),
        "3": ("openai", "OpenAI API (needs HYDRAMEM_OPENAI_KEY)"),
        "4": ("anthropic", "Anthropic API (needs ANTHROPIC_API_KEY)"),
    }
    print("\nChoose an LLM provider:")
    for key, (name, desc) in options.items():
        print(f"  {key}) {name:<10} {desc}")
    choice = input("Provider [1]: ").strip() or "1"
    return options.get(choice, options["1"])[0]


def cmd_init(args: argparse.Namespace) -> None:
    target = Path(args.path).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    provider = args.provider
    if not provider:
        if sys.stdin.isatty() and not args.no_input:
            provider = _prompt_provider()
        else:
            provider = "auto"

    cfg_path = target / "config.yml"
    if cfg_path.exists() and not args.force:
        print("• config.yml already exists — keeping it (use --force to overwrite)")
    else:
        cfg_path.write_text(
            _DEFAULT_CONFIG_YML.replace("provider: auto", f"provider: {provider}", 1)
        )
        print(f"• wrote {cfg_path}")

    for name in ("kms", "data"):
        (target / name).mkdir(exist_ok=True)
        print(f"• ensured {target / name}/")

    print("\nNext steps:")
    print(f"  cd {target}")
    print("  cp your *.md files into ./kms")
    print("  hydramem ingest ./kms")
    print('  hydramem search "your question"')
    print("  hydramem serve            # start the MCP server")
    print("\nMCP client (stdio) — add to your AI client config:")
    print(
        json.dumps(
            {
                "mcpServers": {
                    "hydramem": {
                        "command": "hydramem",
                        "args": ["serve", "--transport", "stdio"],
                    }
                }
            },
            indent=2,
        )
    )


def cmd_ingest(args: argparse.Namespace) -> None:
    target = Path(args.path).expanduser()
    if not target.exists():
        print(f"Path not found: {target}", file=sys.stderr)
        sys.exit(1)

    from hydramem.ingest.pipeline import IngestionPipeline

    pipeline = IngestionPipeline()
    if target.is_file():
        result = pipeline.ingest_file(str(target), project=args.project)
    else:
        result = pipeline.ingest_directory(
            str(target), project=args.project, recursive=args.recursive
        )
    print(json.dumps(result, indent=2, default=str))


def cmd_search(args: argparse.Namespace) -> None:
    from hydramem.search import SearchService

    svc = SearchService()
    result = svc.hydra_search(args.query, project=args.project, top_k=args.top_k)

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
        return

    print(result.get("final_context") or "(no relevant context found)")

    seen: set[str] = set()
    sources = []
    for chunk in result.get("verified", []):
        src = chunk.get("source") or chunk.get("doc_id") or "?"
        if src not in seen:
            seen.add(src)
            sources.append(src)
    if sources:
        print("\nSources:")
        for src in sources:
            print(f"  - {src}")

    print(
        f"\n[{result.get('chunks_total', 0)} candidates · "
        f"avg VoG {result.get('avg_vog_score', 0.0):.3f} · "
        f"traversal {result.get('traversal', 'bfs')}]"
    )


def cmd_serve(args: argparse.Namespace) -> None:
    import os

    if args.transport:
        os.environ["HYDRAMEM_TRANSPORT"] = args.transport
    if args.host:
        os.environ["MCP_HOST"] = args.host
    if args.port:
        os.environ["MCP_PORT"] = str(args.port)

    from hydramem.server import main as server_main

    server_main()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hydramem",
        description="HydraMem CLI – local knowledge memory: init, ingest, search, serve, stats",
    )
    sub = parser.add_subparsers(dest="command")

    # init / ingest / search / serve — primary workflow verbs
    p_init = sub.add_parser(
        "init", help="Scaffold a workspace (config.yml, kms/, data/) + MCP snippet"
    )
    p_init.add_argument(
        "path", nargs="?", default=".", help="Workspace directory (default: current)"
    )
    p_init.add_argument(
        "--provider",
        default=None,
        choices=["auto", "local", "ollama", "openai", "anthropic"],
        help="LLM provider to write into config.yml (default: prompt or 'auto')",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing config.yml")
    p_init.add_argument(
        "--no-input",
        dest="no_input",
        action="store_true",
        help="Never prompt; use defaults",
    )

    p_ingest = sub.add_parser("ingest", help="Ingest a Markdown file or directory")
    p_ingest.add_argument("path", help="Markdown file or directory to ingest")
    p_ingest.add_argument("--project", default="default")
    p_ingest.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=True,
        help="Do not descend into subdirectories",
    )

    p_search = sub.add_parser("search", help="Hybrid search over the knowledge base")
    p_search.add_argument("query", help="Natural-language query")
    p_search.add_argument("--project", default="default")
    p_search.add_argument("--top-k", dest="top_k", type=int, default=10)
    p_search.add_argument("--json", action="store_true", help="Print the full result as JSON")

    p_serve = sub.add_parser("serve", help="Start the HydraMem MCP server")
    p_serve.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "http", "streamable-http"],
        help="MCP transport (default: streamable-http)",
    )
    p_serve.add_argument("--host", default=None, help="Bind host for HTTP transport")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port for HTTP transport")

    # stats
    p_stats = sub.add_parser("stats", help="Show token-saving statistics")
    p_stats.add_argument(
        "--project",
        default=None,
        help="Filter stats to a specific project (default: all projects)",
    )
    p_stats.add_argument(
        "--days",
        type=int,
        default=7,
        metavar="N",
        help="Number of days to include (default: 7)",
    )
    p_stats.add_argument(
        "--last-7d",
        dest="last_7d",
        action="store_true",
        help="Shorthand for --days 7",
    )
    p_stats.add_argument(
        "--export",
        choices=["md", "csv"],
        default=None,
        help="Export format (md or csv)",
    )
    p_stats.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw per-event baseline / injected token rows (audit mode)",
    )

    # telemetry
    p_tele = sub.add_parser("telemetry", help="Manage telemetry data")
    p_tele.add_argument(
        "--project",
        default=None,
        help="Filter telemetry to a specific project",
    )
    excl = p_tele.add_mutually_exclusive_group()
    excl.add_argument("--show", action="store_true", help="Show aggregated JSON")
    excl.add_argument("--wipe", action="store_true", help="Delete metrics.db")
    excl.add_argument("--send", action="store_true", help="Send aggregate (if opted in)")
    excl.add_argument("--opt-in", dest="opt_in", action="store_true")
    excl.add_argument("--opt-out", dest="opt_out", action="store_true")

    # garden-status
    p_garden = sub.add_parser(
        "garden-status",
        help="Show Night Gardener cumulative status and filtering metrics",
    )
    p_garden.add_argument(
        "--json",
        action="store_true",
        help="Print raw garden status as JSON",
    )

    # projects
    p_projects = sub.add_parser(
        "projects",
        help="List all known projects (from telemetry and the knowledge store)",
    )
    p_projects.add_argument(
        "--json",
        action="store_true",
        help="Print the project list as a JSON array",
    )

    # ingest-async
    p_ing = sub.add_parser(
        "ingest-async",
        help="Resumable async ingest of a directory with on-disk checkpointing",
    )
    p_ing.add_argument("directory", help="Directory containing Markdown files")
    p_ing.add_argument("--project", default="default")
    p_ing.add_argument("--concurrency", type=int, default=4)
    p_ing.add_argument("--no-recursive", dest="recursive", action="store_false", default=True)
    p_ing.add_argument(
        "--checkpoint",
        default=None,
        help="Override the default <directory>/.hydramem-checkpoint.json path",
    )

    # sessions-merge (CRDT)
    p_merge = sub.add_parser(
        "sessions-merge",
        help="CRDT merge of two sessions.json files (LWW union by fingerprint)",
    )
    p_merge.add_argument("local", help="Local sessions.json (modified in place by default)")
    p_merge.add_argument("remote", help="Remote sessions.json to merge in")
    p_merge.add_argument("--out", default=None, help="Optional output path")

    # federation: export / import
    p_export = sub.add_parser(
        "export",
        help="Sign and export a project (entities + relations + chunks)",
    )
    p_export.add_argument("output", help="Output file path")
    p_export.add_argument("--project", default="default")
    p_export.add_argument(
        "--secret-env",
        default="HYDRAMEM_FEDERATION_SECRET",
        help="Env var holding the shared HMAC secret (default: HYDRAMEM_FEDERATION_SECRET)",
    )
    p_export.add_argument("--issuer", default="local")

    p_import = sub.add_parser(
        "import",
        help="Verify a signed export and merge it into the local store",
    )
    p_import.add_argument("input", help="Path to a previously exported file")
    p_import.add_argument("--project", default=None, help="Override target project")
    p_import.add_argument(
        "--secret-env",
        default="HYDRAMEM_FEDERATION_SECRET",
    )
    p_import.add_argument(
        "--accept-issuer",
        action="append",
        default=None,
        help="Whitelist an issuer (repeatable). Default: accept any issuer.",
    )

    # dashboard
    p_dash = sub.add_parser(
        "dashboard",
        help="Run the read-only HTML dashboard on localhost",
    )
    p_dash.add_argument("--host", default="127.0.0.1")
    p_dash.add_argument("--port", type=int, default=8765)
    p_dash.add_argument("--days", type=int, default=7)

    # calibrate-srmkg
    p_cal = sub.add_parser(
        "calibrate-srmkg",
        help="Train a per-project logistic calibration of SR-MKG component weights",
    )
    p_cal.add_argument("--project", default="default")
    p_cal.add_argument("--min-samples", dest="min_samples", type=int, default=50)
    p_cal.add_argument("--test-fraction", dest="test_fraction", type=float, default=0.2)
    p_cal.add_argument("--l2", type=float, default=1.0)
    p_cal.add_argument("--lr", type=float, default=0.1)
    p_cal.add_argument("--epochs", type=int, default=500)
    p_cal.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Train but do not write the weights file",
    )

    # review (human-in-the-loop prune labelling → golden dataset)
    p_review = sub.add_parser(
        "review",
        help="Label queued spurious-edge prune candidates (builds the golden dataset)",
    )
    p_review.add_argument("--project", default="default")
    p_review.add_argument("--limit", type=int, default=20)
    p_review.add_argument(
        "--status", action="store_true", help="Print queue counts as JSON and exit"
    )
    p_review.add_argument(
        "--export", default=None, help="Export the labelled golden dataset to a JSONL path"
    )

    # train-pruner (learn the edge scorer from the labelled golden dataset)
    p_tp = sub.add_parser(
        "train-pruner",
        help="Train the learned spurious-edge scorer from labelled prune reviews",
    )
    p_tp.add_argument("--project", default="default")
    p_tp.add_argument("--min-samples", dest="min_samples", type=int, default=20)
    p_tp.add_argument("--test-fraction", dest="test_fraction", type=float, default=0.2)
    p_tp.add_argument("--l2", type=float, default=1.0)
    p_tp.add_argument("--lr", type=float, default=0.1)
    p_tp.add_argument("--epochs", type=int, default=500)
    p_tp.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Train but do not write the weights file",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Shorthand --last-7d overrides --days
    if hasattr(args, "last_7d") and args.last_7d:
        args.days = 7

    if args.command == "init":
        cmd_init(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "garden-status":
        cmd_garden_status(args)
    elif args.command == "projects":
        cmd_projects(args)
    elif args.command == "telemetry":
        cmd_telemetry(args)
    elif args.command == "ingest-async":
        cmd_ingest_async(args)
    elif args.command == "sessions-merge":
        cmd_sessions_merge(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "dashboard":
        cmd_dashboard(args)
    elif args.command == "calibrate-srmkg":
        cmd_calibrate_srmkg(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "train-pruner":
        cmd_train_pruner(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
