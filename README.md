# Coordinator kit

Turns a Claude Code session into a pure **coordinator**: it interviews you, plans, then dispatches
every build/research/design/verification step to `Agent` sub-dispatches, keeping a durable,
git-committed record of state so any session — this one resumed, or a fresh one — can pick up
where it left off.

Works for both a brand-new project and an existing codebase. On an existing repo, it dispatches
read-only analysis agents to map the code first — languages/frameworks, layout, build/test/CI,
conventions, debt — before interviewing you, so the interview only asks what the code can't
already answer.

Two install paths exist side by side: a **plugin** (primary, below — install from GitHub, update
centrally) and the original **file-copy install** (a paste-able prompt that copies files into the
project; kept for existing installs and anyone who prefers it — see `FILE-COPY-INSTALL.md`).

## Install the plugin

```
claude plugin marketplace add nikolamin/claude-coordinator-kit
claude plugin install coordinator-kit@coordinator-kit
```

Installs at **user scope** by default, so it's available in every project on this machine, not
just the one you ran the command from. If the current session was started before you ran this,
run `/reload-plugins` (or restart) — a session only loads plugin state present at its own start.

Confirm it took: `claude plugin list` shows `coordinator-kit`; `claude plugin details
coordinator-kit@coordinator-kit` shows all 13 skills, at roughly 3,900 always-on tokens, versus
the file-copy path's ~545-line `CLAUDE.md` paid in full every turn.

## Run it

In the project's root directory, start Claude Code and say **"bootstrap yourself"** (or
"resume" — same trigger; it's also meant to fire on its own the moment a session starts in a
project with no coordinator work done yet). That loads `coordinator-kit:bootstrap`, which asks
one question for `<NOTIFY_CHANNEL>` if it isn't already known (Telegram bridge, another
mechanism, or plain chat), installs this project's own `CLAUDE.md` from the plugin's thin spine
template (not this repo's root `CLAUDE.md` — that one belongs to the file-copy path), and creates
the `docs/` knowledge-base skeleton (`docs/coordination/STATE.md`, `docs/concept/`,
`docs/objectives.md`, `docs/plan.md`, `docs/decisions/`, `docs/validation/`) plus
`.coordinator-scratch/` (gitignored), then commits it.

Then it branches: a **new project** goes straight into the Concept interview, one question at a
time; an **existing codebase** gets read-only analysis agents first, committed to
`docs/coordination/repo-map.md`, before the interview is tailored to what they found; an
**already-bootstrapped project** resumes instead on the same phrase — reads `STATE.md`'s Current
section, re-arms monitors, works any stop note a previous session left.

From there, answer the interview across as many turns as it takes; a dispatched agent writes each
round into `docs/concept/`, and you approve before Objectives, then Plan (another approval gate),
then Execute runs autonomously with checkpoint pings.

This flow is not yet verified end to end on a real project — see Status below.

## Optional: memory seed and Telegram bridge

Two pieces of the file-copy install have no plugin equivalent, regardless of which path installed
everything else:

- **`memory-seed/*`** — behavioral-correction files for Claude Code's own auto-memory. No plugin
  primitive seeds a memory directory; a plugin only ships skills, commands, and templates. To use
  it anyway, copy `memory-seed/*.md` into `~/.claude/projects/<slug>/memory/` (`<slug>` is this
  project's absolute path with every `/` replaced by `-`) — see `FILE-COPY-INSTALL.md` for the
  full procedure, including the conflict check against a rule already seeded.
- **`telegram-bridge/`** — a machine-level Telegram relay daemon. Plugin components run inside a
  Claude Code session; none can start or supervise a persistent background service outside it.
  Install it the same way the file-copy path does — see `FILE-COPY-INSTALL.md`'s "Telegram bridge
  (optional)" section.

## Update the plugin

```
/plugin update coordinator-kit
```

Then `/reload-plugins` (or restart) so a running session picks up the changed skills.

`plugin.json` pins an explicit `version` (`0.1.0`) instead of tracking this repo's HEAD commit,
deliberately: with a pinned version, pushing commits here does nothing for anyone who already
installed the plugin until that string is bumped — which makes the bump itself a review gate,
not silent auto-apply on every update check.

**If the update changed the spine** (`plugins/coordinator-kit/skills/bootstrap/templates/
claude-md-spine.md` — the `CLAUDE.md` a plugin-based coordinator installs at your project root), a
project that already bootstrapped is still running its old copy: updating the plugin alone
doesn't touch a file it already wrote into your project. Getting the new spine into a live
project takes the same three-session dance the file-copy path uses (see `FILE-COPY-INSTALL.md`'s
"Updating" section for the reasoning) — `CLAUDE.md` is both the file being changed and the running
session's own operating instructions, loaded once at session start, so no single session can both
write the new file and run under it:
1. Tell the running session **"stop and save your step"**.
2. New session: re-run bootstrap (or hand-copy the new spine over the project's `CLAUDE.md`
   yourself).
3. Fresh session: **"bootstrap yourself"** to resume from the saved step.

## What's in it

13 skills, loaded on demand instead of sitting in every session's always-on context:

- `bootstrap` — fresh-project bootstrap, and the "bootstrap yourself" resume path.
- `stop-and-save` — the "stop and save your step" half of the same protocol.
- `phase-loop` — the full phase loop (Bootstrap through Iterate) and the doc layout.
- `execute-loop` — build/verify/commit loop: retry cap, push gate, CI gate, parallel defaults.
- `verification-standard` — what makes a verifier's pass/fail judgment actually trustworthy.
- `escalation` — when to escalate to an advice-tier agent, or route to a second opinion.
- `codex-second-opinion` — install/auth/invocation for a second opinion via `codex exec`.
- `watchdogs` — never going silently idle: monitor arming, stall detection, session recovery.
- `question-protocol` — the one-at-a-time structure for every founder-facing question.
- `comms-register` — status-update format and notify-channel cadence/etiquette.
- `backlog-discipline` — `plan.md`/`STATE.md` as the sole backlog, never a side list.
- `credential-handling` — standing authorization, pasted-credential handling, one-honest-bound.
- `agent-brief-hygiene` — what a dispatched agent's brief must carry, since it inherits nothing.

## Uninstall

```
claude plugin uninstall coordinator-kit@coordinator-kit
claude plugin marketplace remove coordinator-kit
```

## Status

Verified with real command output: `marketplace add`, `install`, `list`, and `details` (all 13
skills listed, ~3,896 always-on tokens).

Not yet verified: whether each skill actually fires at the right moment in practice — the routing
test in `plugins/coordinator-kit/routing-test.md` has never been run — and whether `bootstrap`
works end to end on a real project. `claude --plugin-dir ./plugins/coordinator-kit` loads the
plugin in place for testing, without installing it — run the routing test yourself with that if
you want either claim verified before relying on it.

## File-copy install

The original install path: paste a prompt (or follow manual steps) that copies `CLAUDE.md`,
`PROCESS.md`, `STATE.md`, and `codex-setup.md` directly into a project, `memory-seed/*` into a
Claude Code memory directory, and `telegram-bridge/` outside the project — instead of installing
a plugin. Still fully supported: use it for an existing file-copy install, or if you'd rather have
plain copied files than a plugin. Full instructions — the paste-able install prompt, the manual
checklist, customization notes, updating, and the optional Telegram bridge — live in
`FILE-COPY-INSTALL.md`.

## License — MIT

See `LICENSE`.
