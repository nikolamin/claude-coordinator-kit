# Coordinator Kit plugin

Version **0.4.0** packages the coordinator workflow as a project spine plus **14 on-demand skills**.
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
| `codex-second-opinion` | Optional Codex CLI setup/invocation |
| `credential-handling` | Authorized account access and secret/DB handling |

The package includes a project CLAUDE.md spine, a JSON operating-profile seed, Python 3.9+
SQLite CLI/schema, and a SessionStart migration hook. On the first updated-plugin startup it
imports legacy STATE/plan/decision/question/profile/log companions, verifies preserved bytes,
and replaces Markdown sources with database pointers. The database is mandatory for plugin
coordination; original artifacts and instruction files remain available.

Run `scripts/coord.py --help` for the command inventory. `ensure --init` initializes/migrates,
`summary` is the read-first view, `review` handles uncertain legacy material, entity `put/show/list`
commands own state transitions, and agents append `event` evidence. `backup` makes consistent
SQLite snapshots. Full usage: [coordination-state](skills/coordination-state/SKILL.md).

No server/pip dependency. Automatic startup requires Bash plus Python; bootstrap also runs ensure
explicitly if hooks are disabled. A hook failure is reported, not falsely labelled migrated.
External communication bridges, agent registries and schedulers are configured by each project.

## Install and update

```text
claude plugin marketplace add nikolamin/claude-coordinator-kit
claude plugin install coordinator-kit@coordinator-kit
```

Use `/plugin update coordinator-kit` and reload/restart according to the installed CLI.
The manifest pins a version; deliberately bump it when preparing a release. A source checkout
change is not publication or proof that an installed cache has updated.

A fresh session after updating loads the migration hook. Normal "bootstrap yourself" ensures and
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
