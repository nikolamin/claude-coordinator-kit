# Changelog

## 0.11.0

Automatic lane filling. In one measured session a coordinator left thirteen work lanes idle for
hours. Three things combined: dispatched agents were not recorded as lanes with an agent id, so the
idle check counted zero running agents; the idle alarm named lanes but gave no pick and no
free-slot count; and no rule said that an idle wake requires a dispatch. Details:
[lane filling](references/lane-filling.md).

- **Autolane hook (PostToolUse on `Agent`, SubagentStop).** Every background agent dispatch from
  the main session gets an active lane with `agent_id`, transcript path, model and dispatch time.
  - It attaches to the coordinator's own claim for the same task when one has no agent id yet.
  - Otherwise it creates a `shared_checkout` lane, whose unique resource is the agent rather than
    the checkout, so agents sharing a trunk checkout never collide.
  - SubagentStop releases every lane of that agent.
  - The hook parses dict, content-block and text tool responses, skips synchronous and nested
    agents, and fails open. A failure is recorded in `.coordinator/autolane-health.json` and
    reported until a later run succeeds; it is never silent.
- **Brief marker lines.** `coord.py brief-contract --task ID --lane NAME [--checkout PATH]` prints
  the `Task:`, `Lane:` and `Checkout:` lines the hook links agents by.
- **`coord.py idle`.** For each idle work lane (task `data.lane`), it gives one ranked pick: P0
  first; last-resort work (weekly or test-failure tasks, `last_resort: true` or a
  `last_resort_prefixes` id) last; then queue order. It also gives `FREE-SLOTS` = profile
  `capacity.max_agents` minus running agents, 0 under `capacity.min_free_memory_pct` host free
  memory (macOS `memory_pressure`, Linux `/proc/meminfo`).
  - Quiet agents (transcript silent past `quiet_minutes`) and stale claims without an agent id do
    not hold a lane; stale claims are reported as unattached.
  - `idle block|unblock LANE --reason` records why a lane cannot start, with an expiry. `'*'`
    applies it to all lanes.
  - `--lines` prints watch lines; `--check` exits 2 when action is due.
- **`sweep --available-slots auto`.** Takes FREE-SLOTS and its dispatch candidates from the idle
  picks, and adds `lane_hook_failing` / `attach_or_release_lane` items, so `--check-idle` stays
  at exit 2 until each pick is dispatched or blocked.
- **Combined watch.** `scripts/watch.py` reports `IDLE_LANES`, `LANE_HOOK_FAILING` and
  `LANE_UNATTACHED` by default; set `"idle": false` in `watch.json` to turn this off.
- **Rule.** An idle wake means dispatching each pick up to FREE-SLOTS, or recording that lane's
  blocker; never re-arm with neither. This rule is in proactive-cycle, watchdogs, execute-loop and
  the spine template.

Upgrade notes:

- Schema stays 1; no data migration. The lane fields `shared_checkout`, `agent_id`, `lane` and
  `auto_lane`, the task fields `lane` and `last_resort`, and the profile `capacity` block are all
  additive.
- The hook becomes active at the first fresh session after the update, in every workspace that
  has `.coordinator/coord.db`. To turn it off, add `{"autolane": {"mode": "off"}}` to
  `.coordinator/guards.json`. Codex has no matching events, so record `agent_id` on lanes by hand
  there.
- Set `capacity.max_agents` in the workspace profile; the default is 4. Give tasks a `lane` to get
  one pick per work stream; tasks without one fill leftover slots from the `unassigned` pool.
- If the project has its own lane-registration hook or idle alarm, retire it once this version is
  installed. Running both records every agent twice: once under the local id and once as
  `lane-agent-<id>`. The kit hook skips an agent that already has an active lane, so whichever
  runs first wins. Merge the spine template's new idle-wake bullet as a reviewed change.

## 0.10.0

Process fixes from one measured multi-day coordinator session, moved from prose into enforcement
where that is reliable. Details, configuration and limits: [guards](references/guards.md).

- **Dispatch guard (PreToolUse on `Agent`).** In the main session of an established coordinator
  workspace, an Agent call is denied unless it sets `model` and the brief carries the execution
  contract: no delegation, a step cap, the task scratch directory and the wait recipe. The deny
  message names what is missing. `coord.py brief-contract --scratch DIR` prints the contract.
- **Self-execution guard (PreToolUse on `Bash`).** The coordinator session is denied remote
  shells, HTTP and CI probes, git history/remote inspection beyond `git log origin/<branch>..`,
  and reads of agent transcripts or native output files. Subagents and projects without a
  coordinator database are untouched. The spine names the same list.
- **Context guard (warning only).** Warns when the coordinator's context passes 200k tokens
  (estimated from the session transcript, or `context_tokens` on resume) and when a returned
  agent ended over 200k; stop-and-save gains a self-initiated handoff for that case.
- **Verify-cycle cap in the CLI.** `coord.py verify pass|fail|start|status|clear` counts failed
  verify cycles per task. At two (any finding counts; profile `verify_cycle_cap` overrides) the
  task is blocked, another cycle is refused, and only an answered `verify_escalation` question
  permits one more. Sweep and status report it. The cap was previously "per gap" in prose.
- **Target and stop line.** Tasks name a `verification_target`; a PASS for that target means
  deliver now, production readiness is judged at release. A base test run is needed only to
  classify a failing candidate test. The pushing agent reads CI; a separate CI-check agent is
  for a failed run, an environment that did not come up, or a production deploy.
- **Wait recipe.** Briefs no longer demand "one foreground call, however long", which cannot be
  obeyed where the host backgrounds long calls: background launch with an exit marker, then
  bounded polls under 170 s, never ending the turn while a run is live.
- **Smaller agents.** Sizing rule is about 80 tool steps or 200k tokens of agent context (was a
  150-step planning warning), then checkpoint and a fresh agent.
- **Whole-feature dispatch and slots.** All parts of a multi-repository feature are dispatched
  in one turn with the shared contract in each brief; `coord.py slot claim` assigns migration
  numbers and other sequential resources at dispatch.
- **Commitments.** `coord.py commitment add|withdraw|fulfil|list` records what the coordinator
  told the user it would do; active ones show in `summary` and `status` and can be withdrawn only
  with the channel they were stated in.
- **One combined watch.** `scripts/watch.py` replaces per-topic monitors re-armed on a timer:
  silent while benign, one line and exit on an overdue lane `deadline` or a project check from
  `.coordinator/watch.json`.

Upgrade notes:

- Schema stays 1; no data migration. New task fields and commands are additive.
- The guards become active in every established coordinator workspace at the first fresh session
  after the update. Existing briefs that lack the contract are denied with instructions. To phase
  in, create `.coordinator/guards.json` with `"mode": "warn"` for `agent_brief` and
  `coordinator_bash` first. Codex users must trust the new command hooks in the host's hook
  interface; the CLI commands work without them.
- Hooks need Bash and Python 3.9+; without them the guards allow everything.
- An existing project spine is not rewritten. Merge the spine template's new lines (named
  non-exceptions, commitments, context cap, contract and watch bullets) as an explicit reviewed
  change, and replace any local "one blocking foreground call" wording with the wait recipe.
- If the project has its own per-topic monitors, move them into `.coordinator/watch.json` checks
  that print only when action is needed, and record lane deadlines.
- Model routing is unchanged and remains a project decision.

Validation: 132 offline tests pass (106 existing, 15 guard hook tests, 11 CLI/watch tests).
Hook input and output fields were checked against the Claude Code hooks reference; the transcript
layout used for the context estimate is undocumented and treated as best effort. No live host
session exercised the hooks, and the root file-copy templates were not changed.

## 0.9.0

- Bundle the executable Telegram idle-status sender: silent post after 30 quiet minutes,
  edit the same post every 30 minutes, and remove it after a recorded conversation exchange.
- Store configuration, task summaries, exchange receipts, timers and message/action identity in
  SQLite. Preserve schema 1 and first-run migration; add no companion state files.
- Provide configure/preview/tick/run/exchange/disable/reconcile commands and an importable bridge
  adapter. Reuse the existing receiver and supervisor; no additional inbox consumer or daemon
  is installed, and each workspace explicitly enables its authorized private recipient.
- Preserve post identity across restarts, serialize senders, deduplicate exchanges, back off
  known failures and journal network actions. Unknown send outcomes stop for observed recovery
  instead of automatically duplicating the post. Credentials stay in environment injection.

Validation: 106 offline tests pass, including 40 sender/transport checks covering timers,
exchange replay, concurrent ticks, restart/crash recovery, malformed receipts and secret-safe
errors. Independent behavioral review and both host package checks pass. No live Telegram
messages were sent; project bridge integration and activation remain per-workspace setup.

## 0.8.0

- Adopt configurable verification by risk: builder-led routine work, independent high-risk
  checks, one final-candidate suite, and a bounded urgent known-good TEST-revert gate.
- Measure release contents from the actual destination baseline before presenting approval.
  Verify AI target selection and trace permission claims used in decisions.
- Keep feasibility questions separate from implementation authority and avoid unnecessary
  recurring machinery for a one-time requested change.
- Enforce read-only SQLite connections for views/exports/backups, without implicit initialization
  or legacy fallback. Keep schema 1 and existing first-run migration.
- Group active status by task, preserve question channel/owner, and surface duplicate queue
  positions, closed queued tasks and lane/task ownership gaps in the proactive sweep.
- Add transport-aware question-button, delivery-receipt and inbox-replay guidance. Optional idle
  status uses canonical task summaries and remains disabled unless requested; no bridge or
  scheduler is installed. Preserve project-specific instructions, recipients and existing grants.

Validation: 66 offline tests pass, including eight new workflow/storage regressions, a reproduced
queue-conflict failure and its restored pass. Independent scenario review and both host package
checks pass. Real bridge delivery and live-project rollout are outside these fixture checks.

## 0.7.1

- Require an action cycle after requests, replies, agent results and wakeups: actually present
  the next pending question and fill free capacity with authorized work before waiting.
- Surface unknown capacity and unranked/undefined requests in sweep output; require scoped-hold
  review so unrelated restrictions cannot silently hide eligible work.
- Add `sweep --check-idle` with JSON readiness and exit 2 for unresolved actions. Keep the command
  read-only; actual sending/dispatch, authority checks and concrete blocker accounting remain
  coordinator responsibilities. Explicit stops still take precedence.
- Carry the cycle through bootstrap, startup context and the instruction template; once the
  authorized queue is exhausted, ask once for the next goal without repeatedly nudging the user.
- Validate with 58 passing tests, including six new proactive-cycle regressions, and independent
  instruction review covering blocking question prompts and continued independent work.

## 0.7.0

- Define new requests read-only, then prioritize and record their queue position without
  displacing active work. Keep incidental findings out of unrelated investigation/fix chains.
- Add task queue positions, explicit user-initiated actions, user blockers and `awaiting_release`
  with release target/evidence. Preserve existing schema-1 data without reclassifying old tasks.
- Link questions to task ids and advance the single presented decision promptly after resolution;
  verified release work enters the question queue unless the user reserved initiation.
- Add read-only `status` and `sweep` commands for compact progress, missed release decisions,
  idle question slots, stale-work checks and capacity-aware dispatch candidates. Retain holds,
  migration review, dependencies and liveness checks; no automatic messaging or cancellation.
- Adapt concise channel formatting and update both Claude Code and Codex packages. Project
  release routes, recipients, language, accounts and live state remain workspace configuration.

Validation: 52 offline tests pass, including 10 new operational-view regressions and a 64-case
dispatch-eligibility check. Both manifests, all 15 skills and relative links validate. The new
views preserve database contents and archived sources; this does not claim a live-project rollout.

## 0.6.1

- Put the UX audit's scope-first gate in its discovery description as well as its body so Codex
  does not batch workspace inspection with the initial skill read. An empty invocation asks
  for scope before listing files, running bootstrap or dispatching agents.

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
