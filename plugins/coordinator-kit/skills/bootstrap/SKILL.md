---
name: bootstrap
description: Initialize or resume a coordinator through the bundled database, automatically migrate legacy STATE/plan/decision companions on first updated-plugin use, reconcile imported records, and restore agent/inbox ownership without replacing project instructions.
---

# Bootstrap, migration and resume

Read the [runtime adapter](../../references/runtime.md) for the active host. Use AGENTS.md
for Codex and CLAUDE.md for Claude Code; both hosts share the same workspace database.

The canonical state is `<workspace>/.coordinator/coord.db`. Load `coordinator-kit:coordination-state`
and run the bundled `scripts/coord.py --root <workspace> ensure --init` before coordination.
The SessionStart hook does this automatically when supported, enabled and trusted;
repeat ensure safely when entering bootstrap or when hook execution is unavailable. This is the
first-run migration supplied by the plugin, not a task to defer or an optional Markdown backend.

## First updated-plugin run

1. Resolve the existing workspace (including multi-repo parents). Preserve AGENTS.md/CLAUDE.md/CHARTER.md/
   PROCESS.md and project constraints. Treat their instructions to write old state companions as
   superseded by this database migration; other authority and behavioral rules remain in force.
2. Run ensure. It imports exact source bytes and recognizable records, archives originals,
   verifies the import and retires Markdown sources to pointers. It never overwrites uncertain
   state with a fresh skeleton. On failure, fix the stated cause and rerun; do not dispatch from
   a partially migrated or alternate Markdown backlog.
3. Run `summary` and `review list`. Read each pending section, reconcile original requirements,
   hold/lift sources, questions, infrastructure/profile, plan dependencies and stop notes into
   canonical records, then resolve it with record references or a justified historical label.
   Reconcile imported needs_review records too. Existing SQLite sources also require repointing
   legacy coordinator/bridge integrations; their original DB files are preserved untouched.
4. Continue only after `summary.ready_for_dispatch` is true, then apply the actual task/hold
   authorization. Migration readiness is not production permission. Record plugin version 0.6.1
   and the adopted spine version separately in the workspace profile.

Existing work remains existing even if all old state filenames now contain short pointers.
Do not restart the concept interview or initialize a Git repo at a multi-repo workspace root.
For nonstandard source locations, use `.coordinator/migration.json` per the state skill.

## Fresh project / missing setup

1. Initialize the database using ensure --init. If no legacy sources exist, it starts empty.
   Resolve project name and notification preference from existing context; ask only unknown
   user choices, one at a time. The plugin does not grant new communication authority.
2. Install [the spine](templates/coordinator-spine.md) into the active host's instruction file
   only when it is missing; substitute
   PROJECT/NOTIFY_CHANNEL/BRIDGE_DIR placeholders and remove unused bridge clauses. Read back
   to confirm all placeholders resolved. Preserve existing instruction files; an explicitly requested
   spine upgrade uses a targeted, authorized diff and a fresh session, never template overwrite.
3. Populate `profile put workspace --data FILE` using the fields in
   [the profile seed](templates/operating-profile.json), replacing empty values with established
   facts or leaving them explicitly unresolved. Store current phase/goals in profile/task records;
   do not recreate STATE.md, plan.md, objectives.md or decision queues as writable companions.
   Concept/design and validation evidence can remain under docs/concept/ and docs/validation/.
4. Create task-owned `.coordinator-scratch/` output as needed and gitignore it in its actual owning
   repo. Persist the database and migration archives; use `backup NEW_PATH` for a consistent
   snapshot in the designated coordination repo before committing bookkeeping. Do not copy a
   live SQLite file or claim a commit at a workspace root that is not a repository.
5. Delegate read-only repo analysis if needed: checkout topology, branches/deploy triggers,
   local/CI commands, runtime side effects, shared services, guardrails and supported model
   aliases. Put the resulting map in profile records with evidence references. Resolve only
   remaining choices; branch policy and mutation authority must be known before build dispatch.
6. A new product enters `coordinator-kit:phase-loop`'s Concept interview; existing approved work
   enters the continuous loop. Missing configuration is filled without restarting the lifecycle.

## Resume / "bootstrap yourself"

1. Run ensure and read summary, active profile/handoff records, open tasks, holds/lifts and the
   presented question. Resolve any new migration review before dispatch. A sourced explicit
   resume lifts the matching session stop, not unrelated scope/production holds; use the atomic
   decision supersession command so the original hold cannot remain falsely active.
2. Audit agents and inbox ownership before recreating anything (`coordinator-kit:watchdogs`).
   No duplicate writer/consumer, time-only kill, or assumption that a dirty tree is intended work.
3. Restore supported session listeners/watchdogs and record fresh ids in profile/lane records.
   Retain valid durable receivers/jobs and correlate messages received during the gap by id.
4. Work the handoff's ordered actions, including snapshot-first mutation recovery. Dispatch only
   within resumed scope. A continuing suspension also blocks new investigation agents unless
   its explicit terms authorize cleanup.
5. Mark the handoff resolved only when its actions are complete; unresolved work keeps canonical
   task/lane records and next steps. Persist the database snapshot as required, and continue
   authorized work under the chosen notification policy.
