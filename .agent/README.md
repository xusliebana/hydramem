# `.agent/` — local runtime workspace

This directory holds the agent's **runtime state** for the current task/session.
It is **gitignored except for the templates below**. See the workflow in
[../AGENTS.md](../AGENTS.md).

## Files

| File | Tracked? | Purpose |
|---|---|---|
| `README.md` | yes | this file |
| `current.example.md` | yes | template for `current.md` |
| `log-template.md` | yes | template for `logs/<date>-<slug>.md` |
| `tasks.example.json` | yes | template/schema for `tasks.json` |
| `current.md` | no | the active task: goal, plan, files, commands, next steps |
| `tasks.json` | no | local task list (`pending` / `in_progress` / `blocked` / `done`) |
| `handoff.md` | no | short note for the next session |
| `logs/` | no | one summarized log per completed task/session |

## How to use

1. **Start of session:** read `current.md` (if present) and `handoff.md`.
2. **Non-trivial task:** `cp current.example.md current.md` and fill it in; keep it
   updated as you work. Only **one** task `in_progress` at a time.
3. **End of session:** write `logs/<date>-<slug>.md` (from `log-template.md`),
   update `handoff.md`, record the `nox -s verify` result, and leave a clean tree.

> Long-lived plans and backlog belong in `docs/` (e.g.
> [../docs/internal/next-session.md](../docs/internal/next-session.md), [../docs/roadmap.md](../docs/roadmap.md)),
> not here. `.agent/` is ephemeral working state.
