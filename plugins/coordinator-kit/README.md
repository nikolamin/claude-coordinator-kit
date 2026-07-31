# coordinator-kit (plugin)

Phase 1 of migrating the coordinator kit from a file-copy install to a Claude Code plugin. This
plugin is **purely additive**: it packages two pieces of existing kit content as skills so the
plugin mechanics can be proven end to end. It changes nothing about the kit's existing file-copy
install path (`CLAUDE.md`, `PROCESS.md`, `STATE.md`, `codex-setup.md`, `memory-seed/`,
`telegram-bridge/`), and it does not yet replace that path — both currently coexist. A founder
following the kit's README today is unaffected by this plugin's existence.

## What this plugin currently provides

- `skills/phase-loop/SKILL.md` — the coordinator's full phase loop (Bootstrap through Iterate)
  and knowledge-base doc layout, repackaged from the kit's `PROCESS.md`.
- `skills/codex-second-opinion/SKILL.md` — install/auth/invocation guide for getting a second,
  differently-trained model opinion via `codex exec`, repackaged from the kit's `codex-setup.md`.

Neither skill replaces the source file it was generated from; both source files (`PROCESS.md`,
`codex-setup.md`) stay exactly as they are and keep being copied into new projects by the
existing install prompt. This plugin is a second, parallel way to get the same guidance in front
of a Claude Code session — not a migration of the install path itself. That migration, along with
`CLAUDE.md`, `memory-seed/`, and `telegram-bridge/`, is out of scope for this phase.

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
Skills from this plugin are namespaced `coordinator-kit:phase-loop` and
`coordinator-kit:codex-second-opinion`.
