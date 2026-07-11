# Coordination State

> Maintained by the coordinator. Updated after every agent run that changes state. Read this first
> when resuming a session.
> Process definition: [PROCESS.md](PROCESS.md)

## Current

<!--
What phase the project is in, what's actively running right now, and what's next. This is the
first thing a resumed session reads — keep it current, not historical. When a task closes, its
detail moves into "Agent log" below and this section is trimmed back down to "what's live now."

For any agent currently in flight, record enough for a within-session watchdog wakeup OR a
resumed session to audit it and tell "still running" from "silently lost" instead of guessing
(see CLAUDE.md's Watchdogs / never stall section — this is exactly the data it reads):
- task/agent id
- what it's doing (one line)
- model tier
- dispatched at (timestamp)
- rough expected duration
- watchdog armed (y/n) — whether a fallback scheduled wakeup is set for this agent

A resumed session re-dispatches (per CLAUDE.md's autonomy-on-recovery rule) anything still listed
here that the previous session never closed out — don't ask the founder first, that's routine
recovery mechanics, not a decision.
-->

- Phase: Bootstrap. No tasks dispatched yet.

## Durable decisions

<!--
Decisions that must survive across sessions and must NOT be silently re-litigated by a future
agent or coordinator turn — naming, architecture choices, scope cuts, anything an ADR in
docs/decisions/ formalized. Also the record of user-approval gates (concept approved, plan
approved, go-live approved) — those are decisions too. One line each, dated, with a pointer to
the ADR if one exists.
-->

- (none yet)

## Infrastructure

<!--
Live URLs, deploy targets, credentials' *location* (never the credentials themselves), server
access patterns, CI/deploy pipeline state. This is the section a future infra task checks before
assuming anything needs to be provisioned fresh.
-->

- (none yet)

## Agent log

<!--
One entry per closed task, newest first. Register: what was built, the commit hash, what the
verifier found (PASS on first pass is rare and worth noting when true — more often verification
finds something, gets fixed, and re-verifies), and any caveat that was disclosed rather than
silently fixed or silently hidden. This is the audit trail — write it so a future session trusts
it without re-deriving the work.
-->

<!-- Delete the EXAMPLE entry below once your first real task closes — it's illustrative only,
     not a live record. Leaving it in place risks a future session mistaking it for real state. -->
- **EXAMPLE — TASK-07 (user auth: email+password login) built + verified PASS, 2024-01-15.**
  Build (`a1b2c3d`): login form, session cookie issuance, rate-limited attempt counter, 14 new
  unit tests + 3 integration tests, all green. Independent verify (`opus`) found a real gap:
  the rate limiter counted attempts per-IP only, so a distributed brute force was untouched, and
  the "remember me" cookie had no expiry set (effectively permanent). Fix (`d4e5f6a`): added
  per-account attempt counting alongside per-IP, 30-day expiry on the remember-me cookie. Re-verify
  **PASS**: both gaps closed, live click-through in a real browser confirmed login/logout/lockout-
  and-unlock all behave correctly. Disclosed caveat (not fixed, intentionally deferred): password
  reset flow is out of scope for this task, tracked as TASK-11 in `docs/plan.md`. **Still open:**
  none for this task.

## Open items

<!--
Cross-task open questions, deferred work, and anything that needs a decision before it can become
a plan task. Distinct from docs/plan.md's task backlog — this is shorter-lived, more like a
running list of loose threads the coordinator doesn't want to lose track of between sessions.
Rule of thumb: if it's already actionable as a standalone task with acceptance criteria, it goes
in docs/plan.md instead; if it's a note, caveat, or open question tied to work already tracked
elsewhere, it stays here until it either resolves or graduates into a plan task.
-->

- (none yet)
