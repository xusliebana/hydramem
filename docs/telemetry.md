# Telemetry

HydraMem records usage metrics **100 % locally** in `~/.hydramem/metrics.db` (SQLite). No data is ever sent to HydraMem servers unless you explicitly opt in to anonymous aggregate reporting.

---

## What is recorded

Every MCP tool call writes one row to the `events` table:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | UUID |
| `ts` | TEXT | ISO-8601 timestamp (UTC) |
| `project` | TEXT | Project namespace |
| `tool_name` | TEXT | MCP tool that was called |
| `session_id` | TEXT | Server-session UUID |
| `llm_preset` | TEXT | Active LLM provider string |
| `tokens_injected` | INTEGER | Tokens in the context returned |
| `tokens_baseline` | INTEGER | Estimated tokens a naive RAG would inject |
| `chunks_total` | INTEGER | Chunks retrieved |
| `latency_ms` | INTEGER | Tool execution time in milliseconds |
| `relations_verified` | INTEGER | Relations verified in this call |
| `relations_accepted` | INTEGER | Relations accepted |
| `relations_rejected` | INTEGER | Relations rejected |

In addition, query-oriented and reasoning-support tools persist compact local sessions in `~/.hydramem/sessions.json` for Night Gardener. Sessions are grouped by `session_id` and store a list of tool entries such as grounded context snapshots, path traces, relation-verification summaries, and conflict-check results. Entries are deduplicated automatically by their observable context fingerprint, so repeated snapshots are collapsed into one entry with a `repeat_count` instead of being stored twice. They do **not** contain the client's private chain-of-thought.

---

## CLI commands

### Dashboard

```bash
hydramem stats --last-7d
hydramem stats --days 30
```

`hydramem stats` now includes the usual period-based telemetry plus a small cumulative Night Gardener section with the latest run, total runs, repeat-threshold filtering, and pruning totals.

Output:

```
╭─────────────────────────────────────────────────╮
│  HydraMem Stats – last 7 days                   │
├──────────────────────────┬──────────────────────┤
│ Tool calls               │                 142  │
│ Tokens (naive RAG)       │               1.4M   │
│ Tokens injected          │               312K   │
│ Tokens saved             │    1.09M (77.8%)     │
│ Cost saved (est.)        │             $5.45    │
│ Avg VoG score            │              0.887   │
│ Rejected by SR-MKG       │                 89   │
│ Rejected by VoG          │                 12   │
│ Hallucinations blocked   │                  5   │
╰──────────────────────────┴──────────────────────╯
```

### Export

```bash
# Markdown report
hydramem stats --days 30 --export md > report.md

# CSV for analysis
hydramem stats --days 30 --export csv > metrics.csv
```

### Raw inspection

```bash
hydramem telemetry --show      # Print recent events as JSON
hydramem garden-status         # Night Gardener cumulative status
hydramem garden-status --json  # Raw Night Gardener status JSON
```

Use `hydramem garden-status` when you want the dedicated Garden view without the token-savings dashboard.

### Wipe

```bash
hydramem telemetry --wipe      # Delete metrics.db (irreversible)
```

---

## Token savings methodology

HydraMem estimates what a naive RAG system would have injected:

1. **Baseline**: embed the query, retrieve top-20 chunks, count their tokens. This is what a standard RAG pipeline would send to the LLM.
2. **Injected**: count the tokens actually sent (after hybrid search + SR-MKG + VoG filtering).
3. **Saved**: `(baseline − injected) / baseline × 100%`

The cost estimate uses the OpenAI `gpt-4o-mini` pricing as a reference (even if you are using a local model) to give a comparable dollar figure.

---

## Anonymous aggregate telemetry (opt-in)

You can opt in to share **aggregate-only, zero-PII** statistics with the HydraMem project. This helps us understand how the tool is used in practice.

What is sent (totals only, no query content, no filenames, no user data):
- Total tool calls per week
- Average token savings ratio
- LLM provider type (local / openai / anthropic)
- HydraMem version

```bash
hydramem telemetry --opt-in    # Enable anonymous sharing
hydramem telemetry --opt-out   # Disable (default)
```

The opt-in flag is stored in `~/.hydramem/telemetry.json`. No network requests are made until opt-in is set.

---

## Privacy guarantees

| Data | Stored locally | Sent externally |
|------|---------------|-----------------|
| Query content | Yes (grouped session snapshots for Night Gardener) | Never |
| Document text | Yes (chunked in graph DB) | Never |
| File paths | Yes | Never |
| Tool metrics | Yes | Only if opted in (aggregates only) |
| API keys | Never | Never (always read from env vars) |

The telemetry SQLite file is stored in your home directory and is not accessible to other users on the system (permissions: 600).

---

## Inspecting the database directly

```bash
sqlite3 ~/.hydramem/metrics.db

# Last 10 events
SELECT ts, tool_name, tokens_injected, tokens_baseline, latency_ms
FROM events
ORDER BY ts DESC
LIMIT 10;

# Token savings by tool
SELECT tool_name,
       SUM(tokens_baseline) AS baseline,
       SUM(tokens_injected) AS injected,
       ROUND((1.0 - SUM(tokens_injected) * 1.0 / SUM(tokens_baseline)) * 100, 1) AS saved_pct
FROM events
GROUP BY tool_name
ORDER BY baseline DESC;
```
