# coordinator-kit (plugin)

Packages the coordinator kit's operating rules as a Claude Code plugin instead of a single
file-copied `CLAUDE.md`: a thin, always-installed spine plus 13 skills loaded on demand. This
plugin is **purely additive**: it changes nothing about the kit's existing file-copy install path
(`CLAUDE.md`, `PROCESS.md`, `STATE.md`, `codex-setup.md`, `memory-seed/`, `telegram-bridge/`),
and it does not yet replace that path — both currently coexist. A founder following the kit's
README today is unaffected by this plugin's existence.

The design problem this solves: a plain dispatched subagent automatically inherits the installed
`CLAUDE.md` hierarchy, but never inherits a plugin skill only the coordinator itself invoked. So
the rules a subagent must have standing in front of it before its brief is even read (Role,
Model routing, Guardrails, a Credential-handling summary) stay in the spine; everything a
dispatched agent never needs for free — because it's the coordinator's own loop mechanics, or
because it's always restated verbatim in a brief anyway — loads as a skill instead of sitting in
every session's always-on context.

## What this plugin currently provides

- `skills/bootstrap/SKILL.md` — fresh-project bootstrap (installs
  `templates/claude-md-spine.md` as the project's `CLAUDE.md`, creates the `docs/` knowledge-base
  skeleton) and the "bootstrap yourself" resume half of the session stop/resume protocol.
- `skills/bootstrap/templates/claude-md-spine.md` — the thin `CLAUDE.md` a plugin-based
  coordinator installs at a project root: Role, Model routing, Execute-loop stop
  conditions/suspension, Guardrails, a Credential-handling summary, Writes-stay-inside-the-
  project, and a pointer to every skill below.
- `skills/stop-and-save/SKILL.md` — the "stop and save your step" half of the same protocol:
  suspending dispatch, closing out in-flight agents, writing the stop note.
- `skills/phase-loop/SKILL.md` — the coordinator's full phase loop (Bootstrap through Iterate)
  and knowledge-base doc layout, repackaged from the kit's `PROCESS.md`.
- `skills/execute-loop/SKILL.md` — the per-task build/verify/commit/dispatch loop: the retry
  cap, the push gate, the CI task-completion gate, and parallel-dispatch defaults.
- `skills/verification-standard/SKILL.md` — what makes a verifier's pass/fail judgment actually
  trustworthy: the non-trivial heuristic, live browser click-through, playtest-to-completion, and
  the rest of the checklist.
- `skills/escalation/SKILL.md` — when to escalate to an advice-tier agent or route to a second,
  differently-trained model opinion, and the no-delegation brief clause.
- `skills/codex-second-opinion/SKILL.md` — install/auth/invocation guide for getting a second,
  differently-trained model opinion via `codex exec`, repackaged from the kit's `codex-setup.md`.
- `skills/watchdogs/SKILL.md` — never going silently idle: monitor arming, stall detection,
  cross-session recovery, and the listener-liveness check.
- `skills/question-protocol/SKILL.md` — the four-part structure and one-at-a-time rule for every
  founder-facing question.
- `skills/comms-register/SKILL.md` — status-update format and notify-channel cadence/etiquette.
- `skills/backlog-discipline/SKILL.md` — `plan.md`/`STATE.md` as the sole backlog, never a side
  list only the coordinator remembers.
- `skills/credential-handling/SKILL.md` — standing authorization, pasted-credential handling,
  the one-honest-bound rule, and never printing or storing a credential.
- `skills/agent-brief-hygiene/SKILL.md` — what every dispatched agent's brief must carry: what a
  subagent inherits automatically versus what only a brief, or a skill it invokes itself, can
  deliver.

None of these skills replace the source file they were generated from; every source file
(`PROCESS.md`, `codex-setup.md`, and the file-copy `CLAUDE.md` itself) stays exactly as it is and
keeps being copied into new projects by the existing install prompt. This plugin is a second,
parallel way to get the same guidance in front of a Claude Code session — not a migration of the
install path itself. Seeding the optional Telegram bridge, `memory-seed/`-style memory files, and
Chrome browser access stay out of this plugin's scope too — a plugin-based bootstrap defers those
one-time, optional install choices to the kit's own README.

## Version-bump rule

`plugin.json` sets an explicit `version` (`0.1.0`) rather than leaving it unset. That is
deliberate, not an oversight: with an explicit `version`, pushing new commits to this repo does
nothing for anyone who already installed the plugin — they only receive an update when this
string is bumped. Left unset, Claude Code would instead use the git commit SHA as the version,
and every commit would count as a new release, auto-delivered on the next update check.

That auto-delivery model is exactly what this kit's own philosophy rejects for `CLAUDE.md`: a kit
update to the coordinator's operating rules gets founder review before it's applied, never a
silent self-merge (see the repo root's `CLAUDE.md` and `UPDATING.md`). Pinning `version` here
keeps plugin updates on the same "founder decides when" footing, rather than quietly reintroducing
auto-apply through the plugin update channel. Bump `version` deliberately, the same way a
`CLAUDE.md` rule change gets deliberate review before it reaches a live project.

## Install locally for testing

From the repo root, point Claude Code at this plugin directory directly — no marketplace add
needed for local testing:

```bash
claude --plugin-dir ./plugins/coordinator-kit
```

Or test the marketplace path (what a real installer would use):

```bash
claude
# inside the session:
/plugin marketplace add /Users/you/path/to/claude-coordinator-kit
/plugin install coordinator-kit@coordinator-kit
```

After either method, run `/reload-plugins` if you edit a file without restarting the session.
Confirm the skills loaded with `/help` (Custom commands tab) or by asking a question that should
trigger one, e.g. "what's the coordinator's phase loop" or "how do I get a codex second opinion."
Every skill from this plugin is namespaced `coordinator-kit:<name>` — e.g.
`coordinator-kit:phase-loop`, `coordinator-kit:execute-loop` — matching its directory name under
`skills/` (see the full list above).
