# Changelog

## 0.6.0

- Support both Claude Code and Codex with native manifests and repository marketplace catalogs.
- Move UX audit into a shared skill: `/coordinator-kit:ux-audit` in Claude Code and `$ux-audit`
  in Codex. Preserve the scope gate, approved run count and all five reference prompts.
- Bootstrap AGENTS.md in Codex or CLAUDE.md in Claude Code only when missing. Preserve both
  existing instruction files and use one workspace database across hosts.
- Recognize AGENTS.md coordinator workspaces for first-run migration, including nested checkouts.
  Keep the explicit bootstrap migration available when command hooks are untrusted or disabled.
- Adapt native subagents, inherited model settings, browser/scheduler capabilities and genuinely
  different reviewer models to the active host. Do not substitute user-owned Codex tasks for workers.
- Add nine isolated compatibility tests covering preserved instructions, cross-host repeats,
  hook payloads/environment, installed paths with spaces and hookless first-run migration.

Validation: all 42 offline tests pass, all 15 skill frontmatters and relative links validate,
and both native manifests validate. Claude Code discovers 15 skills and the SessionStart hook;
Codex recognizes the repository marketplace and package. Full live-project audits, native
hook trust and every-platform execution remain separate from these checks.

## 0.5.0

- Add `/coordinator-kit:ux-audit [scope]` for pre-launch feature-by-persona UX audits.
- Package five detailed prompts: feature mapping, grounded personas, targeted matrix planning,
  isolated browser testing, and HTML synthesis with before/after mockups.
- Preserve scope and run-count approval, source-blind testers, honest abandonment, risk gaps,
  second-model design review and a plan for real post-launch instrumentation.
- Track progress, approvals and resumable run outcomes in the coordinator database; leave
  product changes as sourced proposals. Browser/model configuration remains project-specific.

## 0.4.0

### Database and migration

- Bundle a Python 3.9+ standard-library SQLite CLI and schema. Each workspace owns its
  `.coordinator/coord.db`; the plugin ships no project data.
- Replace writable STATE, plan, decision, question, profile, repository-map and log companions
  with database records. Instruction files and concept/design/validation artifacts remain files.
- Run automatic migration through the SessionStart hook in recognized coordinator workspaces.
  Bootstrap runs the same idempotent ensure command when hooks are unavailable.
- Preserve original bytes, source references and migration archives before retiring Markdown
  files to pointers. Recover interrupted upgrades and concurrent legacy writes.
- Snapshot existing SQLite stores consistently, including committed WAL data. Require explicit
  reconciliation of uncertain requirements, holds, questions and legacy integrations before dispatch.
- Add task, event, decision, question, lane, profile, handoff and guideline records; enforce one
  presented question and one active writer per checkout. Provide backups, search and rendered views.

### Coordination workflow

- Preserve original requirements and cheaply check inherited premises before implementation.
- Assign exclusive checkout lanes and shared-resource ownership before parallel work.
- Reuse full-suite evidence only for matching revisions and environments; retain independent
  acceptance checks, bounded fix cycles and a verified final candidate.
- Recover using current liveness and preserved work, including interrupted mutations.
- Record scoped holds/lifts, durable question correlation and resumable handoffs.
- Keep model mapping, repository topology, release authority, communication preferences and
  persistence policy in each workspace's profile. No project-specific configuration is bundled.
- Add the coordination-state skill; the plugin now contains 14 on-demand skills.

### Upgrade

Save/stop older coordinators, update the plugin and start a fresh session. The hook imports
recognized legacy state; bootstrap reconciles pending sections into canonical records before
resuming work. List nonstandard source paths explicitly in `.coordinator/migration.json`.
Repoint existing database readers/writers during integration review. Do not maintain competing
writable state files. Existing project instructions remain intact; the migration supersedes
their old state-editing protocol. File-copy-only installations change when the plugin is adopted.

See the [migration and recovery reference](skills/coordination-state/references/database-adapter.md)
for discovery, custom paths, failure recovery and backups.

### Validation

The release is checked with the offline database/migration and shell-hook integration suite,
skill-frontmatter checks and Claude Code's strict plugin validation. Tests cover source
preservation, repeats, interruption, concurrent writers, WAL snapshots, path boundaries,
record constraints, backups and startup/resume behavior.

```text
python3 -B -m unittest discover -s plugins/coordinator-kit/tests -v
claude plugin validate --strict ./plugins/coordinator-kit
claude --plugin-dir ./plugins/coordinator-kit plugin details coordinator-kit
```

These checks do not establish real-model [skill routing](routing-test.md), live-project
bootstrap/resume, external bridge integration or execution on every supported platform.
