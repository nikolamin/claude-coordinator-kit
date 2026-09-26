# Coordinator kit

Turns a Claude Code or Codex session into a **coordinator**: it plans and dispatches build, research,
design and verification work to agents, keeping durable state so a fresh session can resume.
New products start with an interview; existing approved work enters a continuous operating loop.

Works for both a brand-new project and an existing codebase. On an existing repo, it dispatches
read-only analysis agents to map the code first — languages/frameworks, layout, build/test/CI,
conventions, debt — and asks only what the code and current decisions cannot already answer.

Two install paths exist side by side: a **plugin** (primary, below — install from GitHub, update
centrally) and the original **file-copy install** (a paste-able prompt that copies files into the
project; kept for existing installs and anyone who prefers it — see `FILE-COPY-INSTALL.md`).

## Install the plugin

For **Claude Code**:

```
claude plugin marketplace add nikolamin/claude-coordinator-kit
claude plugin install coordinator-kit@coordinator-kit
```

Installs at **user scope** by default, so it's available in every project on this machine, not
just the one you ran the command from. If the current session was started before you ran this,
run `/reload-plugins` (or restart) — a session only loads plugin state present at its own start.

Confirm it took: `claude plugin list` shows `coordinator-kit`; `claude plugin details
coordinator-kit@coordinator-kit` shows 15 skills, including UX audit.

For **Codex**:

```sh
codex plugin marketplace add nikolamin/claude-coordinator-kit
codex plugin add coordinator-kit@coordinator-kit
```

Start a new Codex task after installation. Use `$bootstrap` to initialize/resume the coordinator
and `$ux-audit onboarding` for the audit command. `codex plugin list` confirms installation.
For development, register this repository's absolute local path instead of the GitHub source.
Both hosts load the same 15 skills on demand, use the same SQLite state and preserve project
instructions. See the [runtime adapter](plugins/coordinator-kit/references/runtime.md) for
host-specific tools, instruction files and hook trust.

## Run it

In the project's root directory, start Claude Code or Codex and say **"bootstrap yourself"** (or
"resume" — same trigger; it's also meant to fire on its own the moment a session starts in a
project with no coordinator work done yet). That loads `coordinator-kit:bootstrap`, which asks
one question for `<NOTIFY_CHANNEL>` if it isn't already known (Telegram bridge, another
mechanism, or plain chat). Fresh setup installs a missing `CLAUDE.md` (Claude Code) or `AGENTS.md`
(Codex) from the plugin's thin
spine and creates the database profile, tasks and other missing coordination records.
Existing instructions and source content are preserved. Scratch stays in `.coordinator-scratch/`;
the bundled CLI creates `.coordinator/coord.db`. Consistent database snapshots are committed
in the designated coordination repo, which may differ from the workspace root.

Then it branches: a **new project** enters the Concept interview, one question at a time;
an **existing codebase** gets read-only analysis of its repositories, build/test/deploy topology,
and existing coordination state. Approved existing work can enter the continuous loop directly.
An **already-bootstrapped project** resumes its actual task store, holds, lanes and inbox ownership;
a short database-backed STATE file is not mistaken for an empty project.

Greenfield Concept and Plan retain approval gates. Execution then uses exclusive work lanes,
independent behavioral verification, revision/environment-specific test evidence, and the
project's authorized push/CI/release flow. Notifications follow the project's preference;
new projects default to meaningful completion and decisions rather than per-agent narration.

Version 0.4.0 adds database-backed coordination and recoverable first-run migration. See the
[release and upgrade notes](plugins/coordinator-kit/CHANGELOG.md). The plugin includes a
Python/SQLite CLI and a SessionStart hook that automatically migrates legacy state on the first
updated-plugin run when enabled and trusted. Bootstrap runs the same migration explicitly,
including when Codex hooks have not yet been trusted. The database replaces writable STATE, plan, decision/question, profile and
log companions. Original bytes are archived and recoverable; old filenames become pointers only
after verified import. Ambiguous requirements/holds stay pending for coordinator reconciliation
before dispatch. Python 3.9+ with sqlite3 is required; no database server or pip install is needed.

For a pre-launch feature/persona audit, run **`/coordinator-kit:ux-audit [scope]`** in Claude Code
or **`$ux-audit [scope]`** in Codex. This five-stage workflow asks
for run-count approval before launching isolated testers and produces a self-contained HTML
report with before/after mockups. See [command usage](plugins/coordinator-kit/README.md#ux-audit-command).

## Optional: memory seed and Telegram bridge

Two pieces of the file-copy install have no plugin equivalent, regardless of which path installed
everything else:

- **`memory-seed/*`** — behavioral-correction files for Claude Code's own auto-memory. No plugin
  primitive seeds a memory directory; a plugin only ships skills, commands, and templates. To use
  it anyway, copy `memory-seed/*.md` into Claude Code's per-project memory directory
  (`~/.claude/projects/<slug>/memory/` on macOS/Linux/WSL2,
  `%USERPROFILE%\.claude\projects\<slug>\memory\` on Windows; `<slug>` is this project's absolute
  path with every `/` or `\` replaced by `-`) — see `FILE-COPY-INSTALL.md` for the full procedure,
  including the conflict check against a rule already seeded.
- **`telegram-bridge/`** — a machine-level Telegram relay daemon. Plugin components run inside a
  Claude Code session; none can start or supervise a persistent background service outside it.
  Install it the same way the file-copy path does — see `FILE-COPY-INSTALL.md`'s "Telegram bridge
  (optional)" section.

## Platforms

The skills and SQLite CLI support macOS, Linux and Windows with Python 3.9+. The automatic
startup hook also needs Bash (Git Bash on Windows, or WSL2). If hooks are disabled or untrusted
or the interpreter is unavailable, bootstrap runs/retries the documented CLI migration before work. The optional Telegram bridge
also runs on all of them — macOS (launchd), Linux (systemd), Windows (Task Scheduler), and WSL2
(Linux path) — see `telegram-bridge/SETUP.md`.

## Update the plugin

In Claude Code:

```
/plugin update coordinator-kit
```

Then `/reload-plugins` (or restart) so a running session picks up the changed skills.

In Codex, refresh the configured Git marketplace and reinstall, then start a new task:

```sh
codex plugin marketplace upgrade coordinator-kit
codex plugin add coordinator-kit@coordinator-kit
```

Both host manifests pin an explicit `version` (`0.6.0`) instead of tracking this repo's HEAD commit,
deliberately: with a pinned version, pushing commits here does nothing for anyone who already
installed the plugin until that string is bumped — which makes the bump itself a review gate,
not silent auto-apply on every update check.

**First run after updating:** start a fresh session so the new SessionStart hook loads. Codex
requires trust for command hooks; use the host's hook interface to review them, or run `$bootstrap`
to perform migration explicitly. In an existing coordinator workspace the migration preserves exact originals,
then retires the old files to database pointers. `bootstrap yourself` reconciles imported records
and resumes from the database. A repeat run is safe; interrupted cutover resumes. Nonstandard
sources can be listed in `.coordinator/migration.json`.

Save/stop older coordinators before upgrading so they no longer write legacy files. Existing
AGENTS.md, CLAUDE.md, PROCESS.md and CHARTER.md are preserved; a spine upgrade remains a targeted edit, not
an overwrite. Database migration supersedes their old state-file editing instructions only.
The root file-copy templates remain unchanged for file-copy-only installs.
See [migration and recovery details](plugins/coordinator-kit/skills/coordination-state/references/database-adapter.md).

## What's in it

15 skills, loaded on demand instead of sitting in every session's always-on context:

- `bootstrap` — fresh-project bootstrap, and the "bootstrap yourself" resume path.
- `stop-and-save` — the "stop and save your step" half of the same protocol.
- `phase-loop` — the full phase loop (Bootstrap through Iterate) and the doc layout.
- `execute-loop` — exclusive lanes, bounded retries, reusable test evidence, push and CI gates.
- `coordination-state` — bundled SQLite CLI, first-run migration, canonical records and recovery.
- `verification-standard` — what makes a verifier's pass/fail judgment actually trustworthy.
- `escalation` — when to escalate to an advice-tier agent, or route to a second opinion.
- `codex-second-opinion` — a genuinely different reviewer model, including optional `codex exec` setup.
- `watchdogs` — never going silently idle: monitor arming, stall detection, session recovery.
- `question-protocol` — the one-at-a-time structure for every founder-facing question.
- `comms-register` — goal-oriented status, quiet notification policies and bridge etiquette.
- `backlog-discipline` — one canonical backlog, source requirements and stale-premise checks.
- `credential-handling` — task-authorized account access, secret handling and user-only steps.
- `agent-brief-hygiene` — source intent, task scope, resource ownership and required evidence.
- `ux-audit` — scoped feature/persona audit, approved isolated runs and an evidence-backed HTML report.

## Uninstall

Claude Code:

```
claude plugin uninstall coordinator-kit@coordinator-kit
claude plugin marketplace remove coordinator-kit
```

Codex:

```sh
codex plugin remove coordinator-kit@coordinator-kit
codex plugin marketplace remove coordinator-kit
```

## Status

The shared plugin exposes 15 skills and a SessionStart migration hook, with separate Claude Code
and Codex manifests and marketplace catalogs. Fixture-based migration/runtime tests cover preservation, repeats, interruption, concurrent
writers and hook behavior. See the [release notes](plugins/coordinator-kit/CHANGELOG.md#validation)
for current results and limitations. Real-model skill auto-routing is a separate
[routing test](plugins/coordinator-kit/routing-test.md).

```text
python3 -m unittest discover -s plugins/coordinator-kit/tests -v
claude plugin validate --strict ./plugins/coordinator-kit
claude --plugin-dir ./plugins/coordinator-kit plugin details coordinator-kit
```

Local preview loads the hook too: use a fixture workspace when testing migration rather than a
live coordinator workspace. The kit's own source checkout is excluded from automatic migration.

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
