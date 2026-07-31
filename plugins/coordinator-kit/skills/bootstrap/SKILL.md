---
description: Bootstrap a coordinator project for the first time, or resume one that already has
  state. Load this the moment a session starts in a project root with no coordinator work done
  yet, on the founder's literal phrase "bootstrap yourself" or "resume" (or a close variant), or
  whenever it's unclear whether this project has already been bootstrapped in an earlier session.
  Covers both paths in full — a never-bootstrapped project (resolve <NOTIFY_CHANNEL>, install this
  project's CLAUDE.md from this skill's own templates/claude-md-spine.md, create the
  docs/coordination/STATE.md skeleton plus docs/concept/, docs/objectives.md, docs/plan.md,
  docs/decisions/, docs/validation/, create and gitignore .coordinator-scratch/, commit, decide
  greenfield vs. existing via repo-analysis agents, then hand off into the Concept interview) and
  an already-bootstrapped project (apply the resume test, read STATE.md's Current section
  including any stop note left by coordinator-kit:stop-and-save, re-arm every monitor one at a
  time recording each new id, reconcile what arrived during the gap, work the stop note's items in
  order, and trim it back out). Load this before running Bootstrap and before acting on a resume
  instruction — not for what happens once Concept starts (see coordinator-kit:phase-loop) or for
  the founder-triggered stop half of this same protocol (see coordinator-kit:stop-and-save).
---

# Bootstrap and resume

This skill packages the fresh-install half and the "bootstrap yourself" resume half of
`CLAUDE.md`'s Session stop / resume protocol for delivery via a plugin, and adds the
plugin-specific fresh-install procedure that install replaces: a plugin-based coordinator does not
git-clone the kit and copy `PROCESS.md`/`STATE.md`/`codex-setup.md` into `docs/coordination/` the
way the file-copy install's `kickoff-prompt.md` does. The phase loop and the codex second-opinion
guidance are already on this machine as `coordinator-kit:phase-loop` and
`coordinator-kit:codex-second-opinion`, loaded on demand — nothing to copy. The one file this
skill does install is `CLAUDE.md` itself, from `templates/claude-md-spine.md` next to this file,
because that one has to physically live in the project root for Claude Code to load it every
session. `docs/coordination/STATE.md` is also created directly (below) — it is this project's own
live state, not kit content, so there is no template file to copy for it either.

Out of scope for this skill: installing the optional Telegram bridge, seeding
`memory-seed/`-style memory files, and asking about Chrome browser access. Those are one-time,
optional install choices independent of the plugin's own skills — if this project wants them,
follow the kit's README rather than expecting this skill to drive that interview.

## Which path applies: the resume test

Before doing anything else, apply **the resume test**: this is a resume, not a fresh bootstrap, if
`docs/coordination/STATE.md` already exists and either its `## Current` section reads as anything
other than the single line `- Phase: Bootstrap. No tasks dispatched yet.`, or its `## Agent log`
holds any entry beyond one illustrative EXAMPLE entry. A missing or freshly-stubbed `STATE.md`
reads as a brand-new project; a mature project must never be treated as if none of its work
happened, so check the actual file content, not just whether it exists.

## Fresh project: Bootstrap

1. **Resolve `<NOTIFY_CHANNEL>`.** Check `templates/claude-md-spine.md` (before it's copied) or
   the project's own `CLAUDE.md` if one is already present: if `<NOTIFY_CHANNEL>` is still the
   literal placeholder, ask the founder one question — Telegram bridge, a different existing
   mechanism, or "just tell me in chat" — per `coordinator-kit:question-protocol`, and wait for
   the answer before continuing. If the founder picks the Telegram bridge, also ask for
   `<BRIDGE_DIR>`, the bridge's absolute install path on this machine (it's a machine-level
   service, not per-project). If a resolved value is already present, confirm it back in one line
   and move on — don't ask again.
2. **Install the spine.** Copy this skill's `templates/claude-md-spine.md` to the project root as
   `CLAUDE.md`, substituting every `<PROJECT>` with the project's name (ask the founder if not
   already known), every `<NOTIFY_CHANNEL>` with the value from step 1, and every `<BRIDGE_DIR>`
   with the bridge's path if one was given. If no bridge was chosen, edit out the two
   `<BRIDGE_DIR>` mentions instead (the Credential section's `.env` example, and the
   Writes-stay-inside-the-project exemption's bridge clause) rather than leaving them dangling.
   Grep the installed file for any remaining `<PROJECT>`, `<NOTIFY_CHANNEL>`, or `<BRIDGE_DIR>`
   afterward (without suppressing stderr) to confirm zero matches remain.
3. **Create the knowledge-base skeleton:** `docs/coordination/STATE.md` (initialized per below),
   `docs/concept/`, `docs/objectives.md`, `docs/plan.md`, `docs/decisions/`, `docs/validation/`.
   Empty/stub files are fine except `STATE.md`. Don't pre-create `docs/playbooks/` — per
   `coordinator-kit:phase-loop` it's optional, created later only once a recurring scheduled
   procedure is actually worth checking in.

   Initialize `STATE.md` with these sections, in this order: `## Current` holding only the single
   line `- Phase: Bootstrap. No tasks dispatched yet.`; `## Phase log` (empty, append-only, one
   dated line per phase transition); `## Durable decisions` (empty for now — the push-to-deploy
   answer from `coordinator-kit:phase-loop`'s Phase 0 question lands here as soon as it's asked,
   before the first build agent is ever dispatched); `## Intake signal sources` (empty until named
   during Concept/Objectives); `## Infrastructure` (empty); `## Agent log` holding one short,
   clearly-marked illustrative EXAMPLE entry (delete it once the first real task closes — the
   resume test above depends on this file having exactly one entry until then); `## Open items`
   (empty).
4. **Create `.coordinator-scratch/`** at the project root and append it to the project's
   `.gitignore` (creating that file if it doesn't exist yet) — every scratch file, generated
   report, or temp script this coordinator ever writes goes here, per the spine's
   Writes-stay-inside-the-project rule.
5. **Commit the skeleton.** This is the one-time bootstrap exception in the spine's Role section —
   do it directly, don't dispatch an agent for it. If the commit or push fails, stop and tell the
   founder rather than working around it.
6. **Confirm bootstrap is done**, in the register `coordinator-kit:comms-register` defines — lead
   with the fact, no elaboration.
7. **Decide greenfield vs. existing**, per `coordinator-kit:phase-loop`'s Phase 0.5: a repo that's
   just the doc skeleton just created, with no real code and no meaningful git history, is
   greenfield — skip straight to Concept. Otherwise, before asking the founder anything, dispatch
   read-only repo-analysis agents (`sonnet`, per the spine's Model routing) to map the codebase and
   commit their consolidated findings to `docs/coordination/repo-map.md` before the first
   interview question goes out. Either path, ask the founder the push-to-deploy question named in
   step 3 above now if it hasn't been asked yet, and record the answer as a durable decision.
8. **Go straight into the Concept interview** (`coordinator-kit:phase-loop`, one question at a
   time per `coordinator-kit:question-protocol`) in the same turn — don't wait to be prompted
   again.

## Already-bootstrapped project: resume ("bootstrap yourself")

1. The resume test above already fired — this is what put this project on this path.
2. **Catch up `.coordinator-scratch/`** if this is a resume of a project bootstrapped before it
   existed: if missing, create it, append it to `.gitignore` (creating that file if absent), and
   commit that alone — the same one-time catch-up the spine's Role section authorizes.
3. **Read `STATE.md`'s Current section first**, including any stop note that
   `coordinator-kit:stop-and-save` left at the top of it.
4. **Re-arm every monitor, one at a time, recording each new id** — the notify-channel listener
   and the fallback wakeup, using the in-flight schema `coordinator-kit:watchdogs` defines. Every
   task/monitor id is reissued on restart, so a carried-over old id is always stale. Missing either
   monitor leaves the project silent and unnoticed.
5. **Work through the stop note's six items, one action each, if a stop note is present:**
   - **Uncommitted work, per repo:** check what the tree actually holds now against what the note
     said each file should become, and resolve any difference — don't assume the note's stated
     intent actually landed.
   - **Repo state (HEAD, pushed or not):** re-check it directly rather than trusting the recorded
     value — something may have landed, or failed to, while the session was down.
   - **Outstanding founder decisions:** re-ask each pending question's literal text, unchanged, per
     `coordinator-kit:question-protocol` — that's why the note preserved it verbatim, not a
     paraphrase.
   - **Resume actions:** carry them out, in the order the note gives.
   - **What landed this session:** fold it into the Agent log as closed history rather than
     leaving it sitting in Current.
   - **Session lessons worth keeping:** fold each into a durable rule, a Durable decisions entry,
     or a memory file if it isn't captured as one yet, so it survives past this note.
6. **Reconcile anything beyond the note itself:** founder messages that arrived on the notify
   channel while the session was down, and agents that died with the previous session — handle
   per `coordinator-kit:watchdogs`'s cross-session recovery, including its deference to any
   recorded suspension of autonomous dispatch (`coordinator-kit:execute-loop`'s Suspension of
   autonomous dispatch section) — don't re-dispatch anything if a suspension is still in force;
   report status instead and wait.
7. **Trim the stop note back out of Current** now that steps 5-6 are done. A stop note still
   sitting there past this point means the resume didn't finish, not a new steady state. Replace
   it with a short resume note: monitors re-armed with their new ids, the in-flight table, and
   whatever arrived during the gap.
