---
name: phase-loop
description: Choose between greenfield project phases and continuous coordinator operation, define plan/validation gates, and locate the knowledge base. Use for lifecycle or planning questions; per-task delivery is in execute-loop and initialization is in bootstrap.
---

# Phase loop and continuous operation

The coordinator owns the board and delegates research, design, implementation and verification.
Run database ensure and read summary/profile before selecting a lifecycle. Existing approved work does
not need a new concept interview just because the coordinator/plugin was installed or resumed.

## New product or a genuinely new scope

0. **Bootstrap** — use `coordinator-kit:bootstrap` to preserve existing instructions/state and
   create only missing files. Record repository ownership, branch/deploy effects and permissions
   before building. A multi-repo workspace needs one lane/topology entry per checkout.
1. **Repo analysis, when code exists** — dispatched read-only agents map what is already there;
   consolidate a repo map before asking questions the code could answer. Link existing docs.
2. **Concept** — ask unresolved product questions one at a time (vision, users, mechanism,
   UI/UX and relevant business constraints). Preserve raw answers; a dispatched agent synthesizes
   them into concept docs. **The founder approves the concept before Objectives.**
3. **Objectives** — an agent drafts measurable priorities and defines how each will be validated.
   Do not defer the meaning of success until after implementation.
4. **Plan** — an agent creates bounded tasks with goal, original source, dependencies, acceptance
   criteria, verification method, target environment, priority and next step. Record lasting
   architecture/cost choices as sourced decision records. **The founder approves the plan before Execute.** Existing
   explicit task/plan authorization counts; do not ask for the same permission again.
5. **Execute** — follow `coordinator-kit:execute-loop`: claim lane → premise check → build →
   independent verify → bounded fix cycles → final push gate → authorized push → CI/deployed
   outcome → record → next authorized task. Record intermediate stages without claiming the
   whole user goal is done.
6. **Validate** — a separate agent exercises each objective's defined method and writes evidence
   to `docs/validation/`. Prepare a reviewable launch if relevant; actual public/production
   release follows the project's authority rules.
7. **Iterate** — an agent proposes deltas from measured validation. The founder approves scope
   changes; resume at the affected phase rather than restarting the entire sequence.

## Ongoing operation

Resume → intake → prioritize/decide → dispatch available lanes → verify/deliver → record → repeat.
Sources can include founder messages, support/monitor signals, existing tickets and agent findings.
Every signal enters the canonical store (`coordinator-kit:backlog-discipline`). Record original
intent and provenance, check stale premises, distinguish tracking from permission to act.

Use the approved scope and dependency/priority order. Ask only for unresolved founder-only choices,
one at a time; independent work continues. Exhausted backlog does not authorize inventing new
scope: use only documented fallback activities. Model aliases, concurrency limits, schedules and
notification policy come from this project's profile. Preserve its recorded choices.

## Cross-cutting rules

- `coordinator-kit:coordination-state` owns record structure, database migration and history.
  The bundled database replaces state/plan/decision companions; never keep competing editable task lists.
- The coordinator owns statuses, priorities and questions; agents append reports/events and
  return evidence. Record each meaningful transition, then read back/persist it.
- `coordinator-kit:agent-brief-hygiene` defines context, ownership and output bounds. Native agents
  are the ordinary execution path. Use a durable job only when work must outlive a session and
  its scheduler/authority exists; do not substitute a detached process for a task result.
- `coordinator-kit:execute-loop` owns exclusive lanes and evidence reuse. Separate worktrees
  still share services, ports and the stash stack; isolation is established, not assumed.
- `coordinator-kit:watchdogs` owns recovery and listener liveness. A completed batch is followed
  by the next approved task or an explicit idle state, not an unexplained abandoned loop.
- `coordinator-kit:comms-register` controls reporting. Do not reintroduce timer reports when the
  founder chose event-driven or decisions-only notifications.

## Knowledge base

`.coordinator/coord.db` owns goals, tasks, events, decisions, questions, lanes, profiles, guidelines
and handoffs. The bundled CLI's summary/search/read commands replace reading growing state files.
First-run migration imports legacy STATE.md, plan.md, objectives and decision/profile companions,
then retires them to compatibility pointers after verified archival; details are in
`coordinator-kit:coordination-state`. Existing concept/design/validation artifacts stay linked
from records. AGENTS.md, CLAUDE.md, PROCESS.md and CHARTER.md remain instructions, not operational state.

Use docs/concept/ and docs/validation/ for substantial artifacts when needed. Temporary task
logs go in .coordinator-scratch/. Rendered database views are disposable reports; consistent
SQLite backups and the migration archives carry the durable record. No writable parallel plan
or question queue is maintained. File-copy-only installations retain their separate workflow
until adopted by the updated plugin's first-run migration.
