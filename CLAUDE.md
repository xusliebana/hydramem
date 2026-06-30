# CLAUDE.md

Claude Code: this repository uses a **portable agent harness**. **Read
[AGENTS.md](AGENTS.md) first** — it is the single source of truth for project
rules, verification commands, and the documentation map. This file only adds
Claude-specific notes.

## Start every session by

1. Reading [AGENTS.md](AGENTS.md) (project map + non-negotiable constraints).
2. Reading `.agent/current.md` if it exists (active task state).
3. Running `bash scripts/init.sh` on a fresh checkout.

## Claude-specific notes

- **Verify before declaring done.** Run `nox -s verify`. Treat yourself as the
  *generator*; then review your own diff with a fresh-context *checker* mindset
  (see [docs/internal/REVIEW.md](docs/internal/REVIEW.md)). Agents tend to praise their own work — don't.
- **One task at a time.** Track progress in `.agent/current.md`; write a summary
  to `.agent/logs/` when a non-trivial task completes.
- **The public API is a contract.** Do not break the console entry points, the
  documented Python surface, or MCP tool signatures without a deprecation cycle
  and a `CHANGELOG.md` entry — see [docs/internal/CONTRACTS/PUBLIC_API.md](docs/internal/CONTRACTS/PUBLIC_API.md).
- **MCP skills** live in `.github/skills/`; reusable command workflows live in
  `.opencode/commands/`.

Everything else: [AGENTS.md](AGENTS.md).
