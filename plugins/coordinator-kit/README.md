# Coordinator Kit plugin

Version **0.7.1** packages the coordinator workflow for **Claude Code and Codex** as a project
spine and **15 shared on-demand skills**, including the **ux-audit command**.
Each workspace supplies its own model mapping, repository topology, release authority,
notification and persistence policies. The separate root file-copy templates,
memory seed and optional Telegram bridge are unchanged.

## Operating flow

Migrate/ensure the database → reconcile imported records, holds and ownership → intake/check premise → claim an available
lane → build → independent adversarial verify → bounded fix cycles → gate authorized push →
check CI/deployed outcome → record → next authorized work.

New products still use Concept/Objectives/Plan approval gates. Existing approved work enters
continuous operation without repeating those interviews. One writer owns each shared checkout;
parallelism comes from independent repos or permitted isolated worktrees and resources.

Full baseline/candidate suite evidence is reused only for matching revisions and environments;
verifiers independently exercise acceptance criteria. Required live verification remains pending
when blocked. Liveness and recent evidence guide recovery, not elapsed time alone.

## Components

| Skill | Responsibility |
| --- | --- |
| `bootstrap` | Preserve existing state/instructions, initialize missing setup, resume ownership |
| `stop-and-save` | Scoped stop, evidence-preserving handoff and persistence |
| `coordination-state` | Bundled SQLite CLI, migration, tasks/events/decisions/questions, snapshots and recovery |
| `phase-loop` | Greenfield phases and continuous operation |
| `execute-loop` | Exclusive lanes, retry cap, evidence reuse, push/CI/release boundaries |
| `verification-standard` | Independent behavioral, fail-first and live-flow evidence |
| `agent-brief-hygiene` | Source intent, falsifiable premises, bounded work and resource ownership |
| `watchdogs` | Liveness, interrupted trees, receiver ownership and durable obligations |
| `backlog-discipline` | Intake and goal tracking without side backlogs |
| `question-protocol` | One presented decision, exact options and reply correlation |
| `comms-register` | Goal-oriented status and the project's notification preference |
| `escalation` | Repeated gaps and useful second perspectives |
| `codex-second-opinion` | A different reviewer model and optional Codex CLI setup/invocation |
| `credential-handling` | Authorized account access and secret/DB handling |
| `ux-audit` | Scoped feature/persona matrix, isolated browser runs and HTML synthesis |

The package includes an AGENTS.md/CLAUDE.md spine, a JSON operating-profile seed, Python 3.9+
SQLite CLI/schema, and a SessionStart migration hook. On the first updated-plugin startup with trusted hooks it
imports legacy STATE/plan/decision/question/profile/log companions, verifies preserved bytes,
and replaces Markdown sources with database pointers. The database is mandatory for plugin
coordination; original artifacts and instruction files remain available.

Run `scripts/coord.py --help` for the command inventory. `ensure --init` initializes/migrates,
`summary` is the read-first view, `review` handles uncertain legacy material, entity `put/show/list`
commands own state transitions, and agents append `event` evidence. `backup` makes consistent
SQLite snapshots. Full usage: [coordination-state](skills/coordination-state/SKILL.md).

New requests are defined read-only, prioritized and given a visible queue position behind active
work. Incidental findings stay recorded until they belong to authorized work. Verified test work
needing only release approval uses `awaiting_release` and an explicitly linked question; actions
the user wants to initiate stay out of reminders. `status` provides a compact view and `sweep`
finds missed decisions and liveness checks without sending messages or changing records.
These additions reuse the existing database schema; existing records keep their status and history.

The [required coordinator cycle](references/proactive-cycle.md) runs after replies, agent results
and wakeups: ask the next question and fill free capacity with eligible work before waiting.
`sweep --available-slots N --check-idle` exits 2 when follow-up actions still need handling.
Unknown capacity, missing task definitions and scoped holds require follow-through, not a status
summary. Explicit stops and real blockers remain valid reasons to wait.

No server/pip dependency. Automatic startup requires Bash plus Python; bootstrap also runs ensure
explicitly if hooks are disabled or untrusted. Codex requires hook trust separately from plugin
installation; bootstrap still performs the first-run migration. A hook failure is reported, not falsely labelled migrated.
External communication bridges, agent registries and schedulers are configured by each project.
The [runtime adapter](references/runtime.md) maps instruction files, skill invocation, native
subagents and model review to each host. Switching hosts reuses the existing workspace database.

## UX audit command

```text
# Claude Code
/coordinator-kit:ux-audit onboarding and first purchase
/coordinator-kit:ux-audit everything

# Codex
$ux-audit onboarding and first purchase
$ux-audit everything
```

Omit the argument to choose scope interactively. The [skill](skills/ux-audit/SKILL.md) maps
features, derives 3–13 grounded personas, builds a targeted feature/persona matrix, asks for
approval of its exact run count, dispatches isolated browser testers, and synthesizes a
self-contained HTML report with before/after mockups and a second-model design opinion.

Progress, approvals and findings use the coordinator database. Browser/account isolation,
test environment and model choices come from the workspace profile. Abandonment and blocked
runs remain visible; the report distinguishes simulated findings from measured user behaviour
and execution coverage from untested risks. Final artifacts go under
`docs/validation/ux-audit/<audit-id>/` unless the project specifies another deliverable location.
The command produces an audit and proposed fixes; it does not implement them automatically.

## Install and update

Claude Code:

```text
claude plugin marketplace add nikolamin/claude-coordinator-kit
claude plugin install coordinator-kit@coordinator-kit
```

Use `/plugin update coordinator-kit` and reload/restart according to the installed CLI.

Codex:

```sh
codex plugin marketplace add nikolamin/claude-coordinator-kit
codex plugin add coordinator-kit@coordinator-kit
```

Start a new Codex task, then invoke `$bootstrap` or `$ux-audit`. For an update, run
`codex plugin marketplace upgrade coordinator-kit`, reinstall with `codex plugin add`, and
start another task. Local development uses `codex plugin marketplace add /absolute/path/to/claude-coordinator-kit`
instead of the GitHub source. The `.agents/plugins/marketplace.json` catalog points to this package;
`.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` describe their respective hosts.

The manifests pin a version; deliberately bump it when preparing a release. A source checkout
change is not publication or proof that an installed cache has updated.

A fresh session after updating loads the migration hook when enabled and trusted. Normal "bootstrap yourself" ensures and
reconciles the database, then resumes. Existing instruction files are preserved; an explicit spine
upgrade merges a targeted diff while keeping local decisions. Stop old legacy-file writers before
upgrading; existing DB integrations must be repointed during migration review. See the
[release and upgrade notes](CHANGELOG.md).

## Validate locally

```text
python3 -m unittest discover -s plugins/coordinator-kit/tests -v
claude plugin validate --strict ./plugins/coordinator-kit
claude --plugin-dir ./plugins/coordinator-kit
```

Run the tests and validation from the kit repo. The last command loads the plugin without
installing it; use a fixture workspace for migration tests because the hook performs real imports. Skill-frontmatter validation and scenario review are separate from observing real
[routing](routing-test.md). Never report one as proof of the others.
