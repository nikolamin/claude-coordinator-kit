# Runtime adapter

Use the active host's provided tools and permissions. Installing this plugin does not add an
agent manager, browser, scheduler or external reviewer. The SQLite CLI and workflow resources
are shared; runtime-specific invocation and instruction files differ.

| Capability | Claude Code | Codex |
| --- | --- | --- |
| Project instructions | CLAUDE.md | AGENTS.md |
| Explicit workflow | `/coordinator-kit:<skill>` | Select the installed skill with `$`, such as `$bootstrap` or `$ux-audit`; use the catalog's name when names collide |
| Delegation | Available Agent tool and native completion/status tools | Available native subagent tools; do not create user-owned tasks as a substitute |
| Model selection | Supported configured model/effort options | Supported configured model/effort options; inherit when the native API requires it, such as a full-history fork |
| Migration hook | SessionStart, unless disabled | SessionStart after the user trusts the bundled hook; availability depends on the installed runtime |
| Missing/disabled hook | Bootstrap runs `scripts/coord.py --root WORKSPACE ensure --init` | The same required bootstrap command |

Skill identifiers such as `coordinator-kit:execute-loop` refer to workflows in this package.
When a host does not accept that identifier as an invocation, read the matching
`skills/<skill>/SKILL.md` from this installed plugin. Resolve its relative resource links
against that skill directory, never the product checkout or a guessed plugin cache path.

## Instruction files and shared state

Bootstrap installs the shared coordinator spine into the active host's instruction filename
only when that file is missing. Read existing AGENTS.md, CLAUDE.md and referenced policy files
before setup. Preserve existing content and references; a second host is not permission to
replace instructions or bypass a hold. Workspace discovery recognizes either instruction file.
Both hosts use the same `.coordinator/coord.db`; switching hosts is a handoff, not a new backlog.

## Tool boundaries

Use only delegation exposed and permitted by the current session. Brief workers to execute
directly. If the host provides no subagent mechanism, report the specific limitation and finish
authorized bookkeeping; do not label one session's self-review as independent verification.
In Codex desktop, creating a user-owned task requires the user's explicit request for a new task.

Record the actual selected/inherited model and context mode. Follow the host's restrictions on
model overrides and supported aliases. A second Codex process is not a different model merely
because it is a fresh process; the UX audit's independent design opinion must use an actually
different configured model, or remain pending under that workflow's exception rule.

Use native completion/status tools and their returned handles. Do not translate Claude tool
names into invented Codex calls. Use task-scoped native subagents for delegation and the host's
scheduler only when authorized; a session wait is not a durable automation. If a browser or
isolated context is unavailable, preserve a blocked live-check result rather than substituting
source inspection. Do not create new messaging or production permissions while adapting hosts.

## Hooks and trust

The common command hook uses `CLAUDE_PLUGIN_ROOT`, which Codex also supplies for compatibility.
Python 3.9+ with sqlite3 and Bash must be available to the hook process. On Windows use Git Bash
or WSL for automatic hooks; the Python bootstrap command remains usable independently.
Codex does not automatically trust a plugin's command hooks on install. Review/enable them in
the host's hook interface; never edit trust state or use a trust-bypass flag to hide this step.
Bootstrap performs the required migration even while automatic hooks are untrusted or disabled.

Sources: [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins),
[Codex hook trust and events](https://learn.chatgpt.com/docs/hooks), and
[Claude-to-Codex conversion](https://developers.openai.com/plugins/guides/submit-claude-plugin).
