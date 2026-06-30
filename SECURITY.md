# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | ✅        |
| 0.1.x   | ❌        |

## Reporting a vulnerability

If you discover a security issue, **please do not open a public GitHub issue**.
Instead use one of these private channels:

1. GitHub's "Report a vulnerability" form (preferred):
   https://github.com/xusliebana/hydramem/security/advisories/new
2. Email **security@hydramem.dev** with as much detail as you can share
   (reproduction steps, impact, suggested fix).

We will acknowledge receipt within **3 business days** and aim to publish a
fix within **30 days** for high-severity issues.

## Scope

In scope:

- Code and configuration in this repository.
- Default storage paths under `~/.hydramem/`.
- The MCP server endpoints exposed by `hydramem/server.py`.

Out of scope:

- Vulnerabilities in upstream dependencies (please report there directly).
- Issues that require local code execution as the same user that runs the
  HydraMem process (HydraMem is not a sandbox).
- The deliberately optional aggregate telemetry endpoint (audit it before
  opting in).

## Hardening notes

- The MCP server binds to `0.0.0.0` by default for convenience. If you do not
  need network access, set `MCP_HOST=127.0.0.1`.
- Telemetry is opt-in and stored locally. `hydramem telemetry --wipe` clears
  the database irrevocably.
- HydraMem never sends content (queries, chunks, sessions) to any remote
  service unless you explicitly configure an external LLM provider.
