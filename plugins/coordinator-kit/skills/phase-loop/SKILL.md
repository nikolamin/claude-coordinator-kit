---
description: The coordinator's full phase loop (Bootstrap, Repo analysis, Concept, Objectives,
  Plan, Execute, Validate, Iterate) and the knowledge-base doc layout it reads/writes
  (docs/coordination/STATE.md, docs/plan.md, docs/concept/, docs/decisions/, docs/validation/).
  Load this when running or resuming a coordinator session that needs to know which phase it is
  in, what the next phase does, whether a repo is greenfield or existing (Phase 0.5), how the
  Concept interview or Execute loop is structured, how STATE.md/plan.md/repo-map.md relate, or how
  cross-cutting rules like Intake, worktree-per-task dispatch, and the listener-liveness check
  apply. Also load it when deciding "what phase are we in" or "what happens next in the loop."
---

# Phase loop

This skill packages the coordinator's phase loop for delivery via a plugin. It is the same
content as the kit's `PROCESS.md`, which a file-copy install places at
`docs/coordination/PROCESS.md`. If this project used that file-copy install, `docs/coordination/
STATE.md`, `docs/coordination/PROCESS.md`, and `docs/coordination/codex-setup.md` are already
present under `docs/coordination/` and this skill's instructions describe exactly what's already
on disk there — read `STATE.md` first when resuming, it's the fastest way to reconstruct where
things stand. See `CLAUDE.md` (if installed at the project root) for the standing behavioral rules
this loop runs under: model routing, verification standard, comms register, escalation.

The coordinator (Claude, main session) runs this loop. It never does concept/design/implementation
work itself — it spawns build agents, dispatches independent verifier agents to check output
against acceptance criteria, re-prompts unfinished agents, and escalates only non-trivial
questions to the user. The coordinator itself never performs the verification — that's always a
separate agent dispatch, per `CLAUDE.md`'s Role section.

## Phases

**0. Bootstrap** — Knowledge-base skeleton (below) created, `docs/coordination/STATE.md`
initialized, `.coordinator-scratch/` created at the project root and gitignored — append the entry
to the project's `.gitignore`, creating that file if it doesn't exist yet (see `CLAUDE.md`'s Agent
brief hygiene section) — committed. First thing any fresh coordinator session does if the skeleton
doesn't exist yet — this is the one named exception to "coordinator never self-executes" (see
`CLAUDE.md` Role section): fixed layout, no judgment, one-time. If the skeleton already exists,
don't recreate it — read `STATE.md`'s Current section and resume from there instead, but first
check whether `.coordinator-scratch/` exists and is gitignored; if either is missing (an
already-bootstrapped project, or one installed from an earlier kit version), create/gitignore it
now as the same one-time catch-up `CLAUDE.md`'s Role section names, commit that `.gitignore` change
as its own small commit, then resume. Bootstrap also decides which path Phase 0.5/1 takes: if the
repo contains real code beyond the fresh doc skeleton (source files, build config, non-trivial git
history), it's an **existing** project — run Phase 0.5 before
interviewing. A genuinely empty/new repo is **greenfield** — skip straight to Concept. Either path,
ask the founder one early question before the first build agent is ever dispatched: does a push to
the project's main branch trigger a deploy? A greenfield repo has no Phase 0.5 to carry this, so
ask it here, during Bootstrap, before Concept starts; an existing project asks it as part of Phase
0.5 below. Record the answer as a durable decision in `docs/coordination/STATE.md` and state the
resulting branching/worktree convention plainly at that point.

**0.5. Repo analysis (existing projects only)** — Skipped entirely for greenfield projects. For an
existing codebase, map what's already there *before* asking the founder anything, so the interview
can build on the code instead of ignoring it. Before that mapping starts, ask the founder the
push-to-deploy question named in Phase 0 above (does a push to the main branch trigger a deploy?),
record the answer as a durable decision in `docs/coordination/STATE.md`, and state the resulting
branching/worktree convention plainly — this determines whether the worktree default in
Cross-cutting rules applies as-is or inverted for this project. Per the Role section, the
coordinator never explores the repo itself for this — it dispatches read-only analysis agents
(`sonnet` — the build tier per `CLAUDE.md`'s Model routing section, which explicitly covers
read-only analysis/research agents; split by area and run in parallel if the repo is large) to
map: languages/frameworks/toolchain, module/architecture layout, how to build/test/run
it, CI/deploy setup, actual test-coverage state, existing docs, active areas and conventions
visible from git history, and notable TODOs/known debt. Self-contained briefs per agent; each
returns a structured summary. One further agent consolidates all of them into
`docs/coordination/repo-map.md` (what exists, how it runs, conventions, risks/debt), which is
committed as the baseline **before** the first interview question goes out. Existing project docs
are linked from the knowledge base rather than recreated; an existing `CLAUDE.md` is merged
(coordinator rules appended/linked in, project conventions kept), never blindly overwritten;
existing conventions win over kit defaults unless the founder decides otherwise in the interview.
This phase is also where `CLAUDE.md`'s Guardrails section gets filled in for an existing codebase
(see `CLAUDE.md`).

**1. Concept** — Interview the user in the main loop (agents cannot talk to the user), in themed
rounds covering: product vision & goals, user stories/personas, core mechanism/engine, UI/UX,
any public-facing presentation surface, go-to-market/marketing, business model. Within each round,
individual questions are delivered **one at a time**, in full per `CLAUDE.md`'s Question protocol —
never a batched list within a round either. On an existing project, questions
are tailored by `docs/coordination/repo-map.md` from Phase 0.5: ask only what the code can't
answer, and reference the relevant finding directly (e.g. "the repo already does X this way — keep,
extend, or replace?") instead of asking from a blank slate. The coordinator's role here is
narrow: ask questions and record raw answers — it does not itself synthesize, design, or decide. A
dispatched agent synthesizes each round's answers into concept docs under `docs/concept/` before
the next round starts. **GATE: user approves concept before moving to Objectives.**

**2. Objectives** — Agent drafts measurable, prioritized objectives from the concept. Every
objective gets its validation method defined here, not later. Runs autonomously; ambiguities
escalated to the user.

**3. Plan** — Agent produces a milestone plan; each task sized for a single agent run with
acceptance criteria + a named verification step. Architecture/cost/effort decisions with lasting
consequences are surfaced as ADRs in `docs/decisions/` before they're baked into the plan. This
phase is also when `CLAUDE.md`'s Guardrails section gets filled in for a greenfield project (an
existing codebase already got this at Phase 0.5 — see `CLAUDE.md`). **GATE: user approves plan
before Execute begins.**

Minimum fields per task entry in `docs/plan.md` (a checklist item is enough, no rigid schema
required): id, one-line description, depends-on (other task ids, or none), acceptance criteria,
verification step, status (not started / in progress / verify-failed / done). The dependency
field is what lets the coordinator find "the next unblocked task" without asking the user.

**4. Execute** — Per task: spawn build agent → independent verifier agent (for non-trivial tasks)
→ re-prompt/respawn until acceptance criteria are met → update state → commit → immediately
dispatch the next unblocked task. Only non-trivial/irreversible/costly questions reach the user;
see `CLAUDE.md`'s Execute loop and Verification standard for the mechanics — they apply to every
task in this phase by default, don't re-ask the user per task.

**5. Validate** — Per objective, a validator agent checks the method defined in Phase 2. Where
applicable: prepare and verify a live launch (staging deploy, dry run, agent-played end-to-end
check) and collect feedback/analytics — but an actual **public** go-live is a user-only action
per `CLAUDE.md`'s Role boundary; validation prepares and recommends, it doesn't flip that switch
itself. Conclusions written to `docs/validation/`.

**6. Iterate** — A retro agent processes validation conclusions into proposed deltas to concept/
objectives. User approves deltas; the loop resumes at the affected phase — not always from the
top. A validation finding might only require redoing Plan for one milestone, not a full re-concept.

**Beyond Iterate — continuous operation.** A project may keep running past Phase 6 into ongoing
operation once no single active plan bounds its scope anymore. That's not a seventh phase: the
phase loop simply stops advancing, Intake (below) becomes the primary way work enters
`docs/plan.md`, and the coordinator's Execute loop, verification standard, and reporting cadence
continue unchanged — unless the founder has recorded a suspension of autonomous dispatch, a
durable decision per `CLAUDE.md`, tracked in `STATE.md`'s Durable decisions section.

## Cross-cutting rules

- `docs/coordination/STATE.md` is updated after every agent action that changes state (build
  lands, verify passes/fails, decision made). Read it first when resuming a session — it is the
  fastest way to reconstruct where things stand.
- **Intake**: `docs/plan.md` isn't the only door work enters through. The project names its own
  signal sources (a monitor alert, a support inbox, a mid-session founder message — whatever this
  project actually has) during Concept/Objectives and records them in `docs/coordination/STATE.md`.
  A new signal becomes either a new `docs/plan.md` task or a note on existing work in `STATE.md` —
  never a side list only the coordinator remembers (`CLAUDE.md`'s Backlog discipline, applied at
  the point work arrives rather than after it's already a task). Execute (Phase 4) pulls from
  `docs/plan.md` the same way regardless of which phase or signal produced an entry: a bug report
  that turns into a fix is dispatched exactly like a Plan-phase milestone.
- Every agent prompt is self-contained; agents do not share the coordinator's conversation or
  memory.
- Agents run via the native `Agent` tool. For anything that needs to keep listening across a
  session — a relay inbox, a long-running watch — the primary pattern is an in-session
  Monitor-hosted poller (see `CLAUDE.md`'s Watchdogs and Comms register sections for concrete
  examples), so its output lands back in this same context instead of off to the side. A
  CLI-based headless/detached invocation (if your environment has one) is the narrower case,
  reserved for jobs that must genuinely outlive the coordinator's own session.
- **Listener-liveness check**: such a poller can die silently while every producer upstream stays
  perfectly healthy — so during any idle or quiet stretch (every 2-3 idle ticks), a health check
  compares the watched file's own tail — last line, or mtime/line count — against the last message
  the session actually processed. A mismatch means the in-session listener is dead, however green
  the producers look: checking them (the daemon, the launchd/cron job, the sender's log) proves
  delivery **to the file**, never delivery **to the session**, and will happily confirm "silence is
  genuine" when three messages are sitting unread. On a mismatch, re-arm the listener **and** work
  the backlog — acknowledge and answer the missed messages — not just re-arm.
- Orchestration: dispatch unblocked tasks that touch disjoint files/resources in parallel by
  default (see `CLAUDE.md`'s Execute loop) — sidestep merge conflicts with **git worktrees**, the
  default isolation mechanism for concurrent same-repo work (each parallel build agent works in
  its own worktree, not the shared working tree). This is a default, not a universal: a
  trunk-based / continuous-deploy project may need the opposite convention entirely, per the
  push-to-deploy question in Phase 0/0.5 above and the branching convention recorded from it in
  `STATE.md` — don't assume the default applies. Many harnesses support worktree isolation
  natively (e.g. a worktree-isolation flag on agent dispatch) — use it when available rather than
  hand-rolling worktree management. Fall back to sequential dispatch when tasks share
  files/resources or a dependency forces an order. Either way, only one task's outcome may be
  written to `STATE.md`/`plan.md` at a time (queue the edits, don't let two agents' results race
  on the same file). Worktrees isolate the file tree only — a shared external service (a test
  database, a fixed listen port, a shared schema) is a separate collision class that survives
  worktree isolation untouched; treat tasks that would share one of those as not actually disjoint
  (give each agent a private instance, or fall back to sequential dispatch for them — see
  `CLAUDE.md`'s Execute loop).
- Any task that ends in a commit, in a shared (non-worktree) checkout, follows the shared-checkout
  git hygiene in `CLAUDE.md`'s Execute loop step 5 — check `git status` before committing and
  commit only the intended paths, check what's actually ahead of origin before pushing, and never
  run a destructive git operation on a tree that may hold another agent's uncommitted work.
- Everything is committed to git so any future session — this one resumed, or a fresh one — can
  pick up mid-loop from `STATE.md` and the repo alone.
- User-approval gates (end of Concept, end of Plan) are the only phase transitions that require
  explicit user sign-off before proceeding. Everything inside Execute/Validate runs autonomously
  per the Execute-loop rules in `CLAUDE.md`.

## Knowledge base layout

```
docs/coordination/STATE.md        # current phase, activity, why, next, agent log, decision log
docs/coordination/PROCESS.md      # this phase loop, file-copy installed (this skill packages the
                                   # same content for plugin delivery)
docs/coordination/repo-map.md     # existing-project baseline from Phase 0.5 (existing projects only)
docs/coordination/codex-setup.md  # codex exec setup/invocation for CLAUDE.md's Escalation 2nd opinion
docs/coordination/kit-version.md  # installer-written (not Bootstrap): kit commit + install status
docs/coordination/state-archive/YYYY-MM.md  # STATE.md rollover target once Current/Agent log exceed the size budget
docs/concept/                     # user stories, engine/mechanism, UI/UX, presentation, marketing, goals
docs/objectives.md                # objectives + validation methods
docs/plan.md                      # milestones, tasks, acceptance criteria
docs/decisions/                   # ADRs for architecture/cost/effort choices with lasting consequences
docs/validation/                  # validation reports, analytics conclusions
docs/playbooks/                   # optional: recurring scheduled procedures (see note below)
```

`.coordinator-scratch/` sits at the project root, outside this `docs/` tree — Bootstrap creates
and gitignores it per `CLAUDE.md`'s Agent brief hygiene section.

`STATE.md`, `PROCESS.md`, and `codex-setup.md` land in `docs/coordination/` by being copied from
the kit at install time (see `FILE-COPY-INSTALL.md`'s install steps) — Bootstrap confirms they're
present and initializes `STATE.md`'s live content, it does not create these three from an empty
template.
Everything else in this layout, from `repo-map.md` onward, is created empty (or populated) by
whichever phase first needs it.

Adapt the `docs/concept/` sub-structure to what the project actually needs (not every project has
a "presentation website" or "marketing strategy" concern) — the layout is a starting skeleton, not
a rigid schema. Keep the top-level six (`coordination/`, `concept/`, `objectives.md`, `plan.md`,
`decisions/`, `validation/`) stable so tooling and habits transfer across projects.

`docs/playbooks/` is optional, not part of that stable six: create it only when a project actually
has a recurring scheduled procedure worth checking in — a prompt a scheduled task executes,
distinct from an instruction file like `CLAUDE.md` that's loaded every session. The kit's optional
Telegram bridge already ships a significance-gated activity digest, so a playbook isn't the only
way to get a recurring report out of a project — reach for this directory only when that isn't
enough.
