# Bundled database: migration and recovery

The executable lives at `scripts/coord.py` in the plugin root, with `storage.py`, `migrate.py`
and `schema.sql`. Python 3.9+ standard library only. The database is created per workspace;
there is no prepopulated binary containing another project's data.

## Discovery and first run

The SessionStart hook runs from `hooks/hooks.json` through a Bash launcher which finds Python
3.9+ (`python3` or `python`). Windows needs the Bash environment supplied with Claude Code and
Python on PATH. It resolves the nearest established coordinator workspace, including a session
started inside a child product repo. Unrelated directories and this kit's source checkout are
not auto-initialized. Explicit bootstrap uses `coord.py --root WORKSPACE ensure --init`.

Recognized sources: root coordination companions; `docs/coordination/` (also `Docs/coordination/`);
workspace child directories named coordination or autopilot; STATE.md, plan.md,
objectives.md, DECISIONS.md, DECISION-QUEUE.md, COORD.md, operating-profile.md, repo-map.md;
coord.db alongside those records; state-archive Markdown; `docs/plan.md`, `docs/objectives.md`
and `docs/decisions/**/*.md`. CLAUDE.md, PROCESS.md, CHARTER.md, concept/design/validation evidence
and auto-memory remain instruction/artifact files, not retired state.

For nonstandard paths, create `.coordinator/migration.json` before ensure:

```json
{"sources": ["operations/STATE.md", "operations/backlog.md", "operations/ledger.sqlite"]}
```

Paths must be workspace-local regular Markdown or SQLite files. Symlinks, traversal, and the
canonical store itself are rejected. No home-directory memory crawl or arbitrary DB discovery.

## Preservation and reconciliation

Each source revision has a stable path+SHA-256 identity, original byte BLOB, exact archive path,
and import batch. Every Markdown character is retained, including headings, comments and prose
that cannot be parsed into a task. Searchable sections point to source line numbers. Checklists
and recognized SQLite records are imported with conservative needs_review status. Existing SQLite
schemas/tables remain fully recoverable in their snapshots; unknown table rows are searchable too.

The coordinator resolves sections into task/decision/question/profile/handoff/guideline records
with source references before dispatch. Preserve explicit holds and lifts without synthesizing
permission. Historical sections can be marked historical with a rationale. Ready-for-dispatch
requires no pending source retirement, no unresolved sections and no needs_review records.

SQLite source files remain untouched because an external reader may have them open. Their
`.MIGRATED.md` sidecars and integration-review section require old coordinator/status-bridge
readers and writers to be repointed to the bundled CLI. Do not run both stores as writable
backlogs. Later writes to retired Markdown/legacy DB sources are imported as new revisions and
need reconciliation; they cannot silently overwrite canonical task state.

## Failure/restart behavior

A workspace migration lock serializes ensure processes; SQLite transactions and a busy timeout
serialize record writes. Database import commits before pointer replacement. The importer verifies
DB integrity and preserved bytes before retiring each Markdown file. A change detected before
cutover leaves the source in place and asks for a retry. At cutover the original inode is moved
to an archive-adjacent `.displaced-*` file, then the pointer is published without replacing any
file an older writer has recreated. Never delete these retained inodes while old sessions might
still hold them open. Later edits through old file handles stay recoverable; ensure imports each
new revision for review on that run or the next run. Immutable archives remain separate.

Failed or interrupted publication retries without duplicating records. A crash after displacement
may leave the old pathname absent until ensure recreates its pointer; the original is still in
the migration directory and database. Stop older sessions that still write legacy files before
upgrading. Migration provides recovery, not mutual exclusion against unrelated legacy writers.

The SessionStart event adds migration status/context; it cannot mechanically block tools. Bootstrap
and execute instructions require successful ensure/reconciliation before dispatch, including in
hosts with hooks disabled. A missing interpreter or unsupported newer schema reports a failure,
never a successful migration. Do not force schema downgrades.

`coord.py --root WORKSPACE check` checks integrity, foreign keys and each archive/source digest.
`source show ID --output NEW_PATH` extracts original bytes without overwriting an existing file.
`backup NEW_PATH` uses SQLite's consistent backup API, refuses to overwrite files, and checks the
snapshot before returning. Store snapshots and migration archives according to the project's
persistence policy; a rendered report is not a complete backup. Restoring a backup is an explicit
recovery operation with all coordinator writers stopped, not something ensure improvises.

SessionStart packaging follows the official [hook reference](https://code.claude.com/docs/en/hooks#sessionstart)
and [plugin hook discovery](https://code.claude.com/docs/en/plugins-reference#hooks).
