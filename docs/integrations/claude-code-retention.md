# Claude Code — retention & auto-save

How to make sure your work keeps flowing into HydraMem across Claude Code
sessions — both **backfilling** existing knowledge and **auto-saving** going
forward.

!!! info "Honest scope"
    Unlike transcript-mining memory tools, HydraMem does **not** parse Claude
    Code's proprietary JSONL session files. It ingests **Markdown** and
    **agent-submitted** knowledge. So "retention" here means: keep your notes
    ingested, and let the agent `remember` decisions. This is deliberate
    (agent-driven, verified storage) — see
    [ADR-0005](https://github.com/xusliebana/hydramem/blob/main/docs/internal/DECISIONS/0005-agent-driven-ingestion.md).

## 1. Backfill existing knowledge

Point HydraMem at any directory of Markdown notes / docs and ingest it:

```bash
hydramem ingest ~/notes        --project myproject
hydramem ingest ./docs         --project myproject
hydramem ingest ./kms          --project myproject   # the scaffolded knowledge dir
```

Re-ingesting is safe — chunks are upserted by content hash (idempotent).

## 2. Auto-save with a Stop hook

Claude Code can run a shell command when the agent stops. Use it to re-ingest your
knowledge directory so freshly written notes land in the palace automatically.

Create `~/.hydramem/hooks/save.sh`:

```bash
#!/usr/bin/env bash
# Re-ingest the project's knowledge dir after each Claude Code turn.
# Honest: this ingests Markdown notes, it does not scrape the chat transcript.
set -euo pipefail
KMS_DIR="${HYDRAMEM_KMS_DIR:-$PWD/kms}"
PROJECT="${HYDRAMEM_PROJECT:-default}"
[ -d "$KMS_DIR" ] || exit 0
nohup hydramem ingest "$KMS_DIR" --project "$PROJECT" >/dev/null 2>&1 &
exit 0
```

```bash
chmod +x ~/.hydramem/hooks/save.sh
```

Wire it in `.claude/settings.local.json` (project) or `~/.claude/settings.json`
(user):

```json
{
  "hooks": {
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "/absolute/path/to/.hydramem/hooks/save.sh",
        "timeout": 30
      }]
    }]
  }
}
```

Restart Claude Code (hooks load at session start).

## 3. The agent-driven path (recommended)

The highest-signal memories come from the agent itself. Add a line to your
project's `CLAUDE.md` / system prompt:

> Before answering questions about past work, search HydraMem
> (`hydra_search_tool`). When we make a decision, call `remember` to persist it.

This captures **verified** decisions, not raw chat noise.

## Verify

```bash
# After a session:
hydramem search "a phrase you discussed" --project myproject
hydramem stats --last-7d
tail -n 20 ~/.hydramem/metrics.db 2>/dev/null || hydramem stats --raw | head
```

## Notes

- `hydramem ingest` is idempotent — re-running is safe.
- Keep private notes private; HydraMem stores everything **locally** by default.
- Want true transcript capture? That's potential future work, tracked honestly —
  not a shipped feature today.

## See also

- [Claude Code](claude-code.md) · [Cursor hooks](cursor.md) · [Configuration](../configuration.md)
