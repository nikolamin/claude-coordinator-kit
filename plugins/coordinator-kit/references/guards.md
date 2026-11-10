# Guards: rules the harness and the CLI enforce

Instructions and skill text get lost in a long, busy session. In one measured multi-day session a
retry cap that existed in writing was passed three times over, 107 agents ended their turn
"waiting", about a fifth of the coordinator's own commands were investigation, and 43% of coordinator
cost was wake-ups that did nothing. The rules below are therefore enforced by a hook or a command
wherever that is reliable. Judgment (risk class, wording of a question) stays in the skills.

| Rule | Mechanism | Where |
| --- | --- | --- |
| Dispatch has an explicit model and the execution contract (no delegation, step cap, scratch dir, wait recipe) | PreToolUse hook on `Agent`, deny | `scripts/guard.py agent` |
| The coordinator session runs no investigative commands itself | PreToolUse hook on `Bash`, deny | `scripts/guard.py bash` |
| Coordinator context checkpoint cap; oversized agents | UserPromptSubmit, PostToolUse on `Agent`, SessionStart resume: warning only | `scripts/guard.py context` |
| Checkpoint canonical state before compaction; re-orient the same session after it | PreCompact hook; SessionStart `source: compact` | `scripts/checkpoint.py`, `scripts/session_start.py` |
| Two failed verify cycles per task, then one fixed question | CLI refuses the next cycle | `coord.py verify …` |
| A stated commitment binds until withdrawn in the same channel | CLI record shown in `summary`/`status` | `coord.py commitment …` |
| Shared sequential resources are assigned at dispatch | CLI allocator | `coord.py slot …` |
| One combined, silent watch | script | `scripts/watch.py` |

## Scope of the hooks

A guard acts only when **both** hold: the hook input has no `agent_id` (the main session, not a
subagent), and `.coordinator/coord.db` exists in the session's `cwd` or a parent up to the home
directory. A dispatched agent, and any session in a project without a coordinator database, is
never touched. The plugin installs at user scope, so this check is what keeps the guards out of
unrelated projects.

A main session inside a coordinator workspace is treated as the coordinator. If you use such a
workspace for direct hands-on work, switch the guards off for it (below).

Each guard fails closed on its rule and open on its own faults: unreadable config, unexpected
input, a missing Python or a crash prints a one-line notice and allows the call.

## Configuration: `.coordinator/guards.json`

Optional. Missing file means the defaults. Sections merge key by key; named maps (`markers`,
`deny_commands`) merge entry by entry, lists replace.

```json
{
  "agent_brief": {
    "mode": "deny",
    "require_model": true,
    "exempt_agent_types": ["fork", "Explore", "Plan", "claude-code-guide", "statusline-setup", "web-fetch"],
    "markers": {"wait_recipe": null}
  },
  "coordinator_bash": {
    "mode": "deny",
    "allow": ["^git diff --cached --stat$"],
    "wrappers": ["sudo", "env", "time", "command", "nohup", "exec"],
    "deny_commands": {"kubectl": "cluster inspection"},
    "deny_git": ["log", "show", "diff", "fetch", "rev-list", "blame", "reflog", "grep", "bisect"]
  },
  "context": {"mode": "warn", "coordinator_tokens": 450000, "agent_tokens": 200000, "step": 50000},
  "checkpoint": {"mode": "on"}
}
```

- `mode`: `deny` blocks with a message that says how to comply; `warn` lets the call run and adds
  the same message to the model's context; `off` disables that guard. `context` supports `warn`
  and `off` only.
- `markers`: each entry is `{"all": [regex, …], "hint": "…"}` matched against the brief; `null`
  removes a default marker. `coord.py brief-contract --scratch .coordinator-scratch/<task>` prints
  text that satisfies all defaults.
- `allow` (regex on the whole command) is checked first. Adding one is a project decision to
  record, not a way around a single denial.
- `wrappers`: command prefixes to look through (add a local proxy command here).
- `checkpoint`: `{"mode": "off"}` disables the PreCompact checkpoint (or set
  `COORDINATOR_KIT_CHECKPOINT=off`). It is not one of the guards, so `COORDINATOR_KIT_GUARDS=off`
  leaves it on.
- Environment `COORDINATOR_KIT_GUARDS=off` disables every guard for that process tree.
- To remove the hooks entirely, disable the plugin's hooks with the host's own setting; bootstrap
  still runs the migration by command.

## What the Bash guard does and does not catch

Denied by default in the coordinator session: `ssh`/`scp`/`sftp`, `curl`/`wget`, `gh`, git history
and remote inspection (`log`, `show`, `diff`, `fetch`, `rev-list`, `blame`, `reflog`, `grep`,
`bisect`), and reads of agent transcripts or native task output files. Still allowed: `coord.py`,
notification scripts, `git status`, `git log origin/<branch>..` (the outgoing-commit check),
commit and push, the watch script, and everything not on the list.

It is a deny list over command words, not a sandbox. It looks at the first word of each simple
command (after `&&`, `;`, `|`, a newline, `do`/`then`), so text inside quotes is not matched and a
command hidden in `$(…)`, `eval` or a script file is not seen. Reading a report file an agent was
asked to write is allowed: that file is the agent's deliverable. The guard removes the easy path;
the role rule in the instructions still covers the rest.

## Context size

No hook input reports the live context size of a running session. The guard estimates it from the
session transcript named in `transcript_path`: the prompt size (`input_tokens` +
`cache_creation_input_tokens` + `cache_read_input_tokens`) of the last main-thread model request.
That transcript layout is not a documented interface; if it changes, the guard finds no number and
stays silent. On resume it uses the documented `context_tokens` field instead. After an `Agent`
call it reads the documented `tool_response.totalTokens` (the subagent's final request) when the
host returns it; a background launch returns no such number.

The warning repeats only after the context grows by another `step` tokens. `coordinator_tokens`
is a checkpoint threshold, not the end of the session. The warning tells the coordinator to update
the handoff record, take a backup and keep working here. The host's compaction is the reset, and
the user never has to open a new session. A hook cannot start a compaction; it can only prepare
for one and re-orient the session afterwards:

- **PreCompact** (`scripts/checkpoint.py`, manual and automatic compaction). It works only from the
  database. It refreshes the handoff record `handoff-auto-checkpoint` (open tasks, holds,
  commitments, the presented and queued questions, active lanes with agent ids, the other active
  handoffs, resume actions). It writes a consistent backup to
  `.coordinator/backups/precompact-<stamp>.db` (keeping the newest 10). It clears this session's
  warning throttle. Its stdout becomes instructions for the compaction summary: keep the role, the
  handoff, question and lane ids, and every founder instruction not yet in the database. If the
  active profile has `persistence.snapshot`, the hook also replaces that snapshot with a consistent
  copy and commits only that file:

  ```json
  {"persistence": {"snapshot": {"path": ".coordinator-bridge/snapshots/coord.db",
                                "repository": ".coordinator-bridge", "push": true}}}
  ```

  Both paths are workspace-relative, and `repository` must be the top of a git checkout.
  `"push": true` pushes only when every outgoing commit touches the snapshot file alone, so other
  work is never pushed. A failed step never blocks compaction; it is listed in the record's
  `errors` and in the summary instructions.
- **SessionStart, `source: compact`** (`scripts/session_start.py`). It adds: context was compacted;
  re-read `summary`, the active handoffs, the active lanes (agents launched before compaction still
  report to this session) and the presented question; continue the proactive cycle; do not tell
  the user to start a new session. It also names the checkpoint's time and any failed steps.

The host decides when to compact. The plugin cannot change that, but the workspace can; see the
README section "Context: checkpoint and compaction".

## Verified against the hooks reference, and assumed

Verified in the Claude Code hooks reference (read 2026-11-10): plugin hooks live in
`hooks/hooks.json` and may use `${CLAUDE_PLUGIN_ROOT}`; `PreToolUse` receives `tool_name` and
`tool_input`; the subagent tool matches as `Agent` with `prompt`, `description`, `subagent_type`
and `model`; Bash carries `command`; hooks also run inside subagents and their input then carries
`agent_id`/`agent_type`; `hookSpecificOutput.permissionDecision: "deny"` with
`permissionDecisionReason` blocks a call; `additionalContext` is supported on `PreToolUse`,
`PostToolUse`, `UserPromptSubmit` and `SessionStart`; a hook that exits non-zero (other than 2) or
times out does not block the call; `SessionStart` on resume can carry `context_tokens`; the
`Agent` tool response carries `totalTokens`. On compaction (read 2026-11-10): `PreCompact` receives
`trigger` (`manual`/`auto`). On exit 0 its stdout becomes instructions for the compaction summary.
Exit 2 or `"decision": "block"` would block compaction, which `checkpoint.py` never does.
`SessionStart` runs after a compaction with `source: "compact"`, and its output is added to the
compacted context. No hook can start a compaction.

Assumed, not documented: the transcript line layout described above; that a main session in a
coordinator workspace is the coordinator; that Codex marks worker sessions with `agent_id` as
Claude Code does (the existing migration hook already relies on this). Codex tool names differ, so
the `Agent` matcher may never fire there; the CLI commands work on both hosts.

Not hook-enforceable, left to instructions: choosing the risk class, deciding what "the same
feature" spans, ending a turn while a background run is live (a `SubagentStop` hook could block a
stop, but it cannot tell a finished agent from a waiting one without guessing), and starting a
compaction (the host decides when; hooks only checkpoint before it and re-orient after it).
