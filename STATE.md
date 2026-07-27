# Coordination State

> Maintained by the coordinator. Updated after every agent run that changes state. Read this first
> when resuming a session.
> Process definition: [PROCESS.md](PROCESS.md)
>
> **Size budget (read-first only works if this file stays readable):** keep **Current** to
> roughly 40 lines of live content and **Agent log** to the most recent ~15 entries at ~10-15
> lines each — the EXAMPLE entry below is sized to that guide, not just its content. Once either
> grows past that, move the older material into `docs/coordination/state-archive/YYYY-MM.md`
> (create it for the month being archived) and leave a one-line pointer in its place. Archive,
> don't delete — trim on every update, not only once it's already unreadable.

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
recovery mechanics, not a decision. Exception: if Durable decisions below records a suspension of
autonomous dispatch still in force, do NOT re-dispatch — report each item's status to the founder
instead and wait for them to explicitly lift the suspension.

Hard cap: ~40 lines of live content (see the size budget in the header above). If it's longer,
you're keeping history here instead of moving it into Agent log below — trim it.
-->

- Phase: Bootstrap. No tasks dispatched yet.

## Phase log

<!--
Lightweight dated list of phase transitions — Bootstrap complete, Concept started/approved,
Objectives done, Plan approved, Execute started, Validate started, Iterate started — one line
each, append-only, newest last. Lets a resumed session see phase timing at a glance without
scanning the full Agent log below.
-->

<!-- Delete the EXAMPLE lines below once real phase transitions start landing. -->
- EXAMPLE — 2026-07-07 Bootstrap complete.
- EXAMPLE — 2026-07-08 Concept started.

## Durable decisions

<!--
Decisions that must survive across sessions and must NOT be silently re-litigated by a future
agent or coordinator turn — naming, architecture choices, scope cuts, anything an ADR in
docs/decisions/ formalized. Also the record of user-approval gates (concept approved, plan
approved, go-live approved) — those are decisions too. One line each, dated, with a pointer to
the ADR if one exists.

Two categories always land here once they exist, each labelled so a resumed session finds them
without scanning:
- **Branching convention** — the push-to-main-triggers-deploy answer from PROCESS.md's Phase
  0/0.5 question, and the resulting branching/worktree convention. Record before the first build
  agent is ever dispatched.
- **Autonomous dispatch suspended** — a founder-recorded suspension of autonomous dispatch (see
  CLAUDE.md). Quote the founder's instruction verbatim, dated. Only an explicit founder
  instruction lifting it removes this entry — a coordinator or agent never lifts it unilaterally.
-->

- (none yet)

## Intake signal sources

<!--
Named during Concept/Objectives, per PROCESS.md's Intake rule: where new work can come from
besides docs/plan.md tasks and Iterate's deltas — a monitor alert, a support inbox, a mid-session
founder message, whatever this project actually has. One line each: source name + where/how it's
checked. Not a gate — a signal from a source not listed here still becomes a plan.md task or a
STATE.md note the same way (CLAUDE.md's Backlog discipline); this list just records what the
project has agreed to watch.
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

Size budget (see the header): keep only the most recent ~15 entries live, ~10-15 lines each — the
EXAMPLE entry below is that length, use it as the length reference too, not just the content one.
When a new entry would push past ~15, move the oldest into
`docs/coordination/state-archive/YYYY-MM.md` (named for the month being archived) and replace them
with one line here, e.g. "Older entries: see docs/coordination/state-archive/YYYY-MM.md through
YYYY-MM.md."
-->

<!-- Delete the EXAMPLE entry below once your first real task closes — it's illustrative only,
     not a live record. Leaving it in place risks a future session mistaking it for real state. -->
- **EXAMPLE — TASK-07 (user auth: email+password login) built + verified PASS, 2024-01-15.**
  Build (`a1b2c3d`): login form, session cookie issuance, rate-limited attempt counter, 14 new
  unit tests + 3 integration tests, all green. Independent verify (verifier tier, per CLAUDE.md's
  Model routing) found a real gap: the rate limiter counted attempts per-IP only, so a distributed
  brute force was untouched, and the "remember me" cookie had no expiry set (effectively
  permanent). Fix (`d4e5f6a`): added per-account attempt counting alongside per-IP, 30-day expiry
  on the remember-me cookie. Re-verify **PASS**: both gaps closed, live click-through in a real
  browser confirmed login/logout/lockout-and-unlock all behave correctly. Disclosed caveat (not
  fixed, intentionally deferred): password reset flow is out of scope for this task, tracked as
  TASK-11 in `docs/plan.md`. **Still open:** none for this task.

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
