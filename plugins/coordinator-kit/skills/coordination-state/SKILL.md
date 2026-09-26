---
name: coordination-state
description: Use the bundled coordinator SQLite database for tasks, events, decisions, questions, lanes, profiles and handoffs. Run first-use migration of STATE/plan/decision companions, reconcile imported records, then read and write canonical state through the CLI.
---

# Database-backed coordination

The canonical record is **`<workspace>/.coordinator/coord.db`**, created by the bundled
[Python CLI](../../scripts/coord.py). Python 3.9+ with sqlite3 is required; no pip packages or
server are needed. This replaces writable STATE.md, plan.md, decisions, question queues, operating
profiles, repo maps and coordination logs. Concept/design/validation artifacts and behavioral
instructions remain files. Retired filenames contain compatibility pointers, not parallel state.

Use the script's resolved absolute path and explicit workspace root (which may contain several
Git repos). The plugin's SessionStart hook runs migration on startup/resume in recognized
coordinator workspaces when supported, enabled and trusted. Codex requires user trust for bundled
hooks. If hooks are untrusted, disabled, unavailable, or the workspace is new, bootstrap
must run the same `ensure --init` command before coordination. Never claim migration succeeded
from plugin installation alone.

```text
python3 <plugin-root>/scripts/coord.py --root <workspace> ensure --init
python3 <plugin-root>/scripts/coord.py --root <workspace> summary
python3 <plugin-root>/scripts/coord.py --root <workspace> review list
```

## First-run migration

`ensure` snapshots recognized legacy coordination files and databases, imports original bytes
and searchable sections in a transaction, checks integrity and archive bytes, then replaces
Markdown sources with pointers. It is idempotent and resumes interrupted cutover. Every original
is recoverable with `source list` / `source show ID --output NEW_PATH`, as well as from its
`.coordinator/migrations/` archive. Existing SQLite stores are imported via consistent snapshots;
the originals are preserved with `.MIGRATED.md` pointers and an explicit integration-review item.
Repoint their old readers/writers before treating the new database as the sole live backend.

Recognizable checklist/legacy DB records are imported conservatively. Uncertain statuses, free
prose, holds/lifts, questions, operating configuration and stop notes **require coordinator
reconciliation**, not guessed approvals. Use `review show SECTION_ID`, create/update canonical
records carrying original requirements/provenance, then `review resolve SECTION_ID --note TEXT
--refs RECORD_ID ...`. Use `--historical` only after verifying that a section has no remaining
operational content. Do not dismiss an active constraint simply to clear the queue. Imported
`needs_review` records also need a deliberate status update. `summary.ready_for_dispatch` must
be true before dispatch; it certifies migration readiness, not authorization to run every task.

Migration bookkeeping is authorized on the first run; do not ask permission again. It preserves
source data and does not alter product repos, release permissions, or unrelated instructions.
On error, retain the records and source files, report the concrete failure, repair it and rerun
`ensure`. No fallback to a second writable Markdown backlog. See the
[storage and migration reference](references/database-adapter.md) for discovery/recovery details.

## CLI contract

Commands emit JSON except `render`. For writes, prefer `--data <workspace-local JSON file>` or
`--data -` (stdin) over shell-quoting long JSON. Never put secrets in these records.

- `task put ID --data FILE` creates/merges a record; `task show ID`, `task list --open` read it.
  Fields include `title`, `status`, `source`, `source_text`, `goal`, `acceptance`, `dependencies`,
  `priority`, `repo`, `branch`, `commits`, `environment`, `blocked_on`, `next_step`, `evidence`.
  Active/completed tasks require acceptance criteria. Use `--if-version N` after a read when a
  concurrent coordinator might update the same record. Put merges fields, never silently drops them.
- `decision put ID --data FILE` stores the exact sourced instruction, scope, and `type: hold`
  when applicable. `decision supersede OLD NEW --data FILE` records a sourced lift/replacement
  and marks the original superseded in one transaction. Scope must still be checked by the
  coordinator; a new id is not approval.
- `question put ID --data FILE` uses queued/presented/answered/parked states. Store exact options,
  default, outbound id, answer and answer_source. The DB permits only one presented question;
  reply correlation and stale-option checks still follow `coordinator-kit:question-protocol`.
- `lane put ID --data FILE` claims a checkout with `status: active`, `checkout`, `task`, `agent`,
  model, resources and checkpoint path. One active lane per normalized checkout is enforced.
  Set released only after settling writers, child processes and mutations. External-resource
  collisions across different checkouts still require coordination.
- `profile put workspace --data FILE` stores topology, models, communication policy, receiver
  ownership, persistence and plugin/spine versions. `handoff put ID --data FILE` stores stop/resume
  intent and ordered remaining actions; resolved handoffs stay in history. `guideline` records
  retain reusable rules and their rationale.
- `--actor agent event add TEXT --record TASK_ID --kind verify_pass --ref SHA --key UNIQUE`
  appends evidence without changing status. Agent CLI mode disallows coordination transitions;
  this is a workflow boundary, not a sandbox against a process with direct filesystem access.
- `event list`, `search WORDS`, `review list`, and `source list` locate live and historical evidence.
  `render` returns a human view; optional output belongs under `.coordinator/reports/` and is never
  authoritative. `check` validates DB and preserved sources; `backup NEW_PATH` creates a consistent
  SQLite snapshot. Commit that snapshot in the designated coordination repo when required;
  never copy a live database file or initialize Git at a multi-repo workspace root for convenience.

Read `summary`, active profile/handoff records and the relevant tasks on resume. Keep original
intent, holds and answers with source references; use actual clock timestamps and measured
revisions. The database retains the event history, so there is no need to rewrite or compact
large state files. This narrow bookkeeping access does not grant access to product databases.
