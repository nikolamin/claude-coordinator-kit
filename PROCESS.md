# Coordination Process

The coordinator (Claude, main session) runs this loop. It never does concept/design/implementation
work itself — it spawns build agents, dispatches independent verifier agents to check output
against acceptance criteria, re-prompts unfinished agents, and escalates only non-trivial
questions to the user. The coordinator itself never performs the verification — that's always a
separate agent dispatch, per `CLAUDE.md`'s Role section. See `CLAUDE.md` for the
standing behavioral rules this loop runs under (model routing, verification standard, comms,
escalation).

## Phases

**0. Bootstrap** — Knowledge-base skeleton (below) created, `docs/coordination/STATE.md`
initialized, committed. First thing any fresh coordinator session does if the skeleton doesn't
exist yet — this is the one named exception to "coordinator never self-executes" (see `CLAUDE.md`
Role section): fixed layout, no judgment, one-time. If the skeleton already exists, don't recreate
it — read `STATE.md`'s Current section and resume from there instead. Bootstrap also decides which
path Phase 0.5/1 takes: if the repo contains real code beyond the fresh doc skeleton (source files,
build config, non-trivial git history), it's an **existing** project — run Phase 0.5 before
interviewing. A genuinely empty/new repo is **greenfield** — skip straight to Concept.

**0.5. Repo analysis (existing projects only)** — Skipped entirely for greenfield projects. For an
existing codebase, map what's already there *before* asking the founder anything, so the interview
can build on the code instead of ignoring it. Per the Role section, the coordinator never explores
the repo itself for this — it dispatches read-only analysis agents (`model: sonnet`; split by area
and run in parallel if the repo is large) to map: languages/frameworks/toolchain, module/
architecture layout, how to build/test/run it, CI/deploy setup, actual test-coverage state,
existing docs, active areas and conventions visible from git history, and notable TODOs/known
debt. Self-contained briefs per agent; each returns a structured summary. One further agent
consolidates all of them into `docs/coordination/repo-map.md` (what exists, how it runs,
conventions, risks/debt), which is committed as the baseline **before** the first interview
question goes out. Existing project docs are linked from the knowledge base rather than
recreated; an existing `CLAUDE.md` is merged (coordinator rules appended/linked in, project
conventions kept), never blindly overwritten; existing conventions win over kit defaults unless
the founder decides otherwise in the interview.

**1. Concept** — Interview the user in the main loop (agents cannot talk to the user), in themed
rounds covering: product vision & goals, user stories/personas, core mechanism/engine, UI/UX,
any public-facing presentation surface, go-to-market/marketing, business model. Within each round,
individual questions are delivered **one at a time**, per `CLAUDE.md`'s Question protocol (context
for why it's being asked, brief reasoning, 2-4 options with trade-offs and a marked recommendation
where one exists) — never a batched list within a round either. On an existing project, questions
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
consequences are surfaced as ADRs in `docs/decisions/` before they're baked into the plan.
**GATE: user approves plan before Execute begins.**

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

## Cross-cutting rules

- `docs/coordination/STATE.md` is updated after every agent action that changes state (build
  lands, verify passes/fails, decision made). Read it first when resuming a session — it is the
  fastest way to reconstruct where things stand.
- Every agent prompt is self-contained; agents do not share the coordinator's conversation or
  memory.
- Agents run via the native `Agent` tool. A CLI-based headless invocation (if your environment has
  one) is reserved for jobs that must outlive the coordinator's own session.
- Default orchestration level: sequential build agent per task + independent verifier agent for
  non-trivial work. Sequential-by-default sidesteps merge conflicts and state-file race
  conditions. Escalate to parallel/fan-out only when tasks are genuinely independent, touch
  disjoint files/resources, and the environment supports running agents concurrently — and even
  then, only one task's outcome may be written to `STATE.md`/`plan.md` at a time (queue the
  edits, don't let two agents' results race on the same file).
- Everything is committed to git so any future session — this one resumed, or a fresh one — can
  pick up mid-loop from `STATE.md` and the repo alone.
- User-approval gates (end of Concept, end of Plan) are the only phase transitions that require
  explicit user sign-off before proceeding. Everything inside Execute/Validate runs autonomously
  per the Execute-loop rules in `CLAUDE.md`.

## Knowledge base layout

```
docs/coordination/STATE.md    # current phase, activity, why, next, agent log, decision log
docs/coordination/PROCESS.md  # this file
docs/coordination/repo-map.md # existing-project baseline from Phase 0.5 (existing projects only)
docs/concept/                 # user stories, engine/mechanism, UI/UX, presentation, marketing, goals
docs/objectives.md            # objectives + validation methods
docs/plan.md                  # milestones, tasks, acceptance criteria
docs/decisions/                # ADRs for architecture/cost/effort choices with lasting consequences
docs/validation/               # validation reports, analytics conclusions
```

Adapt the `docs/concept/` sub-structure to what the project actually needs (not every project has
a "presentation website" or "marketing strategy" concern) — the layout is a starting skeleton, not
a rigid schema. Keep the top-level six (`coordination/`, `concept/`, `objectives.md`, `plan.md`,
`decisions/`, `validation/`) stable so tooling and habits transfer across projects.
