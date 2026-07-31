---
description: Where a newly discovered follow-up or an outside signal goes — docs/plan.md and
  docs/coordination/STATE.md are the single source of truth for pending work, never a
  suggestion-chip tool or any side backlog only the coordinator remembers. Load this the moment
  something new surfaces that isn't already tracked — a follow-up noticed mid-work (a bug seen in
  passing, a piece of debt, an idea for later), or a signal arriving from outside the
  coordinator's own work entirely — a crash report, a support ticket, a monitor alert, a
  mid-session founder message. It becomes a new docs/plan.md task, or a note on existing work in
  STATE.md — nothing else. Also load this before writing a dispatched agent's brief, to restate
  the same no-side-backlog rule for that agent (a subagent's own call to a suggestion-chip/
  spawn-task tool creates a stray chip the coordinator cannot see or clean up). Not for the
  routine mechanics of editing plan.md/STATE.md once you already know an item belongs there —
  only for the "where does this go" decision itself.
---

# Backlog discipline

`docs/plan.md` and `docs/coordination/STATE.md` are the single source of truth for pending work.
Do not use suggestion-chip tools or any side backlog. A follow-up discovered mid-work becomes a
new task in `docs/plan.md`, or a note on existing work in `docs/coordination/STATE.md` — never a
separate list only the coordinator remembers. The same applies to signals arriving from outside
the coordinator's own work — crash reports, support tickets, monitor alerts, mid-session founder
messages — per the Intake rule in `coordinator-kit:phase-loop`'s Cross-cutting rules: they become
a plan task or a STATE.md note too, never a side list of their own.

This rule also has to travel with every dispatched agent, not just live in the coordinator's own
head: a subagent that calls a suggestion-chip/spawn-task tool on its own creates a stray chip the
coordinator cannot see or clean up. Restate it explicitly in the brief of any dispatched agent
whose task could plausibly turn up a follow-up worth flagging — see
`coordinator-kit:agent-brief-hygiene` for where this fits alongside the rest of what a brief must
carry.
