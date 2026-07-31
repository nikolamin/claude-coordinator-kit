---
description: What every prompt to a dispatched agent must carry, and — the load-bearing
  distinction — what it does not need to re-paste because the installed CLAUDE.md hierarchy
  already reaches a dispatched subagent automatically, versus what a plugin skill's body never
  does. Load this while writing any Agent-tool dispatch — deciding whether to restate a rule or
  just point at it, naming acceptance criteria and the required verification step, adding the
  no-delegation and no-self-backgrounding constraints, requiring a snapshot commit before
  inspecting another agent's worktree, keeping file writes inside the project root, and
  restating credential/guardrail/backlog/push-gate rules that live only in a sibling skill. Also
  load this when dispatching a built-in Explore or Plan agent, or a "fork" agent — their context
  rules differ from an ordinary dispatch (see below). Not for the phase-level or per-task loop
  mechanics themselves (see coordinator-kit:phase-loop and coordinator-kit:execute-loop) — this
  is about what one dispatched prompt must contain, not what happens before or after it.
---

# Agent brief hygiene

## What actually reaches a dispatched subagent

A plain dispatched subagent (not a "fork" of the current session, and not one of the built-in
`Explore`/`Plan` agent types) starts with the full `CLAUDE.md` hierarchy the main conversation
itself loads — user-level, project-level, and any directory-level `CLAUDE.md` files — as part of
its initial context, automatically, with no action required to hand it over. A rule that lives
directly in the installed `CLAUDE.md` (the Role boundary, Model routing, Guardrails, and so on)
is already in front of that subagent before its brief is even read.

What genuinely does not transfer to a dispatched subagent: the coordinator's conversation
history (prior messages, what other agents already found), a skill's body that the coordinator
itself invoked (loading a skill is scoped to the session that invoked it — a subagent doesn't
get it merely because the coordinator does, and won't spontaneously invoke a sibling skill it
doesn't know exists), auto-memory, output style, and the contents of files the coordinator has
already read but the subagent hasn't.

Two dispatch shapes break the general rule above, in opposite directions: a **fork** clones the
parent session's own context, conversation history included, so it needs none of this restated;
the built-in **`Explore`** and **`Plan`** agent types skip `CLAUDE.md` entirely, so treat a
dispatch to either of them like the plugin-only case below for every rule that would otherwise
arrive for free.

## What still needs restating, and why

Two different reasons produce the same-looking instruction — "restate this in the brief" — and
it matters which one applies, because only one of them is actually about inheritance:

- **A rule that lives only in a plugin skill is not inherited at all.** `coordinator-kit`'s
  `credential-handling`, `backlog-discipline`, `comms-register`, and `question-protocol` skills
  (and this one) are not part of the `CLAUDE.md` hierarchy — a subagent gets none of their
  content unless the brief either pastes the operative rule inline or explicitly names the skill
  for the subagent to invoke itself. The same is true of `execute-loop`'s push gate: it is
  task-specific dispatch-loop mechanics, not a standing `CLAUDE.md` rule, so it reaches a build
  agent only if the brief pastes it in. For anything safety-critical (credential handling above
  all), do both: name the skill **and** paste the specific operative rule inline rather than
  trusting that a subagent will think to invoke it.
- **A rule that lives in the installed `CLAUDE.md` already reached the subagent — restating it
  is about salience, not delivery.** `CLAUDE.md` is long; a generic slot like Guardrails is
  filled in with this project's actual specifics (which URL is production, which action is
  irreversible) and a build agent shouldn't have to search a few hundred lines to find the one
  paragraph that applies to its task. Naming the concrete, already-filled-in fact directly in the
  brief is what makes the standing rule actually operative for this one task, not what makes it
  reach the subagent in the first place.

Do not conflate the two: a brief that skips restating a `CLAUDE.md`-resident rule isn't leaking a
secret the way a brief that skips a skill-only rule is — but it can still leave a subagent to
guess which of several similar-sounding rules actually governs its task, which is reason enough
to name the specific one anyway.

## What every brief must carry

Regardless of which case above applies:

- Self-containment with respect to **conversation context only** — prior messages, what other
  agents found, files already read. Name the exact files/paths/commands already known from
  `STATE.md` or a prior agent's report instead of leaving the subagent to go find them; if
  genuinely unknown, let the dispatched agent discover them itself rather than guessing.
- Acceptance criteria and the required verification step, explicit in the brief — these are
  facts about this one task, never standing policy, so nothing above ever supplies them for
  free.
- For infra/execution tasks, the no-delegation constraint from `coordinator-kit:escalation`: "do
  not delegate, execute directly, paste raw command output."
- Any brief touching credentials, auth, secrets, or a database connection restates
  `coordinator-kit:credential-handling`'s rules explicitly, including the never-dump-
  credential-files rule verbatim (never `cat`/`head`/`tail`/`echo` a credential file's contents;
  inspect variable names only, then `source` it and reference `${VAR}` without printing the
  expanded value) — this is the skill-only case above, so restating is the only way it reaches
  the subagent at all. A brief that omitted this has leaked a secret into a persisted transcript;
  a brief that included it was honored.
- Any brief touching one of Guardrails' named production surfaces, irreversible actions, or
  restricted data restates the relevant entry from the installed `CLAUDE.md` explicitly — the
  salience case above: the subagent already has Guardrails, but not which line of it applies here.
- Any build-agent brief whose task feeds a coordinator commit/push restates
  `coordinator-kit:execute-loop`'s push gate explicitly — rebase onto latest main, re-run the
  complete local suite (including DB-gated integration tests against a real local DB, no
  self-skip mode), and report **zero new failures versus the base commit** with the failure sets
  diffed. This is the skill-only case, not salience: the push gate lives in the `execute-loop`
  skill, never the installed `CLAUDE.md`, so pasting it into the brief is the only way it ever
  reaches the build agent at all.
- Any brief dispatching an agent to inspect or mutation-test another agent's worktree must
  require snapshot-committing that worktree first, so a destructive step during inspection can't
  destroy uncommitted work.
- **A hardlink copy of a git worktree carries a `.git` file pointing at the original**, so git
  operations inside the copy mutate the original worktree's index — clone instead of copying when
  an isolated tree is genuinely needed.
- For any task involving a long-running blocking call (a multi-minute build, a live API
  round-trip), forbid "self-backgrounding" explicitly — the agent arming a watcher/background
  monitor for its own work and ending its turn with "standing by" instead of the actual result.
  State it must run the call as one ordinary blocking foreground call, however long it takes, and
  report the real output — nothing re-invokes a subagent that defers to itself.
- Restate the no-side-backlog rule (see `coordinator-kit:backlog-discipline`) in every dispatched
  brief — this is the skill-only case again: a subagent that calls a suggestion-chip/spawn-task
  tool on its own creates a stray chip the coordinator can't see or clean up.
- Every brief (the coordinator's own work included) keeps all file writes inside the project
  root — scratch files, generated reports, temp scripts, downloads — in `.coordinator-scratch/`,
  never `/tmp` or a home-directory path: an out-of-project write trips an allow-click prompt
  invisible on the notify channel and blocks the session. Exempt: paths the kit itself names and
  the founder already approved at install time — the Telegram bridge directory and its files,
  Claude Code's own per-project memory directory, the one-time install or update clone, and temp
  handling inside the kit's own shipped scripts.
