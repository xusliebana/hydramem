# Review Protocol

Harness engineering separates the **doer** from the **checker**: agents (and
authors) reliably over-rate their own work. Review every non-trivial change — your
own included — from a fresh-context checker stance.

## Reviewer mindset

- Assume the author was optimistic. Verify claims by **running commands**, not by
  reading the diff alone.
- Distrust "it should work" — ask for the evidence (test output, `nox` logs).
- Smaller surface beats cleverness. Prefer the backward-compatible option.

## Checklist

1. **Goal & scope.** Does the change do what was asked, and nothing more?
   Cross-check [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md).
2. **Public-contract impact.** Any change to entry points, CLI flags, MCP tool
   signatures, the documented Python surface, or config keys? If so: is it
   backward-compatible, or is there a `DeprecationWarning` + `CHANGELOG.md` entry?
   ([CONTRACTS/PUBLIC_API.md](CONTRACTS/PUBLIC_API.md))
3. **Tests.** Are they present, meaningful (not just smoke), and passing?
   Run `nox -s tests api`.
4. **Honesty.** Do docs/metrics/dashboard claims match the implementation? Is the
   shadow-estimator / "tokens saved" number still defensible?
5. **Constraints.** Local-first respected? No CoT capture? No unbounded LLM calls?
   Heavy deps behind extras? ([CONSTRAINTS.md](CONSTRAINTS.md))
6. **Quality gates.** `nox -s lint typecheck build` — clean (typecheck advisory,
   must not regress).
7. **Security.** No secrets in code/logs; inputs validated at boundaries
   ([SECURITY.md](../../SECURITY.md)).

## Verdict

End with one of:

- **Accept** — meets the bar; evidence attached.
- **Revise** — list the specific required fixes.
- **Block** — fundamental issue (broken contract, dishonest claim, failing gate).

## PR summary format

```
## What & why
<1–2 sentences>

## Public API impact
<none | additive | breaking + deprecation + CHANGELOG link>

## Verification
<commands run + result, e.g. `nox -s verify` ✅>

## Risks / follow-ups
<known risks, anything not covered>
```
