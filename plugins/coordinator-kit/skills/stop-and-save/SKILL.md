---
description: Suspend autonomous dispatch and write a durable stop note before a session ends.
  Load this on the founder's literal phrase "stop and save your step" (also "stop and save
  state", "save your step and stop", and close variants). Covers recording the dispatch
  suspension in STATE.md's Durable decisions, closing out every in-flight agent (finished ones
  fold into the Agent log, still-running ones get recorded in STATE.md's Current section using
  the in-flight schema coordinator-kit:watchdogs defines), and writing the stop note itself at
  the top of STATE.md's Current section with all six required items — uncommitted work per repo
  and what each touched file should become, repo state (HEAD, pushed or not) per repo, numbered
  outstanding founder decisions including any pending question's verbatim text, ordered resume
  actions, what landed this session, and session lessons worth keeping — then committing
  STATE.md alone and reporting per coordinator-kit:comms-register. Load this before ending a
  session on the founder's stop instruction. Not for the resume side of this same protocol (see
  coordinator-kit:bootstrap, which reads what this skill wrote on the next "bootstrap yourself").
---

# Stop and save

This skill packages the stop half of `CLAUDE.md`'s Session stop / resume protocol for delivery via
a plugin — everything a session does the moment the founder says "stop and save your step" (or a
close variant), so a later session (this one resumed, or a fresh one) can pick the work back up
without losing anything. The companion resume half — "bootstrap yourself" reading what this skill
wrote — is `coordinator-kit:bootstrap`, not this skill.

## 1. Suspend dispatch

Stop dispatching anything new. Record the instruction verbatim and dated in `STATE.md`'s Durable
decisions, in the "Autonomous dispatch suspended" slot. That rule's semantics — what stays running
while suspended (status reporting, the question queue, scheduled/checkpoint reports), what stops
(new agent/build/investigation dispatch), and that only an explicit founder instruction lifts it —
are already defined in the installed `CLAUDE.md`'s Execute loop stop conditions and in
`coordinator-kit:execute-loop`'s Suspension of autonomous dispatch section; point at those rather
than restating them here.

## 2. Close out every in-flight agent

For each agent currently dispatched, check its actual status:
- **Finished** → close it out normally into `STATE.md`'s Agent log, same as any other completed
  task (build, verify result, commit hash, disclosed caveats).
- **Still running** → record it in `STATE.md`'s Current section using the in-flight schema
  `coordinator-kit:watchdogs` defines, so a fresh session can tell "still genuinely running" from
  "abandoned when the session ended" instead of guessing.

## 3. Write the stop note

Write a stop note at the top of `STATE.md`'s Current section, marked so it is unmissable on
resume (e.g. a heading like `### STOP NOTE — <date>` directly under the section header). It must
carry all six of the following — this is the complete list, not a starting point:

1. **Uncommitted work, per repo: the files, and what each one should become** — not just what
   changed. An agent killed mid-task can leave a file holding either a real fix or a half-applied
   change, and only the stated intent distinguishes the two; without it, a resumed session cannot
   tell which one it's looking at.
2. **Repo state, per repo: HEAD commit, and whether it's pushed to origin.**
3. **Outstanding founder decisions, numbered.** For any pending question, its literal text — the
   one-line context, the coordinator's own reasoning, the 2-4 options with their trade-offs and
   recommendation, and the safe default — per `coordinator-kit:question-protocol`'s four required
   parts, copied verbatim, not paraphrased, so the resumed session re-asks it unchanged instead of
   reconstructing it from memory.
4. **Resume actions, in the order they should happen.**
5. **What landed this session** — so a resumed session doesn't have to re-derive it from `git
   log`.
6. **Session lessons worth keeping** — a correction, a gotcha, anything learned that isn't already
   a durable rule, so a hard-won lesson doesn't die with the session along with everything else
   that wasn't written down.

This note is deliberately denser than `STATE.md`'s normal ~40-line budget for Current, and is
expected to push past it for the gap between this stop and the next resume — that's the one
allowed exception, not a new steady-state size. `coordinator-kit:bootstrap`'s resume path trims it
back down once it has acted on every item.

## 4. Commit and report

Commit `STATE.md` and only `STATE.md` — this is the spine's Role-section bookkeeping exception,
scoped to this one file; sweeping in other changes here would attribute unrelated work to a stop
note commit. Then report in the normal register `coordinator-kit:comms-register` defines: the
current phase, what was in flight and how each item was disposed of, the one pending question if
there is one, and that dispatch is now suspended.
