---
name: codex-second-opinion
description: Set up and invoke the optional Codex CLI for a coordinator agent's independent opinion on UI/UX, copy, research, or document review. Use when that second-opinion path is selected; escalation decides when it is useful.
---

# Codex / GPT second-opinion — setup

This skill documents the optional Codex CLI reviewer. On a Claude Code coordinator it can
provide a different model's opinion on UI/UX, copy, research or documents. On a Codex
coordinator, another Codex process is not automatically a different model. Compare the actual
primary and reviewer models; select a genuinely different configured reviewer when the audit
requires one. Use the [runtime adapter](../../references/runtime.md) and project permissions.

For a Codex-hosted second opinion, a dispatched agent can use an already configured alternate
model or external reviewer, including Claude Code when authorized and available. Check that
reviewer's installed CLI/tool contract, permissions and actual model; do not invent flags,
install it or authenticate another account implicitly. Record the model, review artifact and
disagreements. Keep a required UX audit opinion pending when no suitable reviewer is available.
See `coordinator-kit:escalation` for optional review and its fallback; the following commands
apply only when Codex CLI is the selected reviewer.

## Install

```bash
npm install -g @openai/codex
```

Requires Node. Same PATH gotcha as the Telegram bridge: launchd/systemd-spawned processes get a
minimal `PATH` that excludes nvm/homebrew-managed bin dirs, so a bare `codex` (like a bare
`claude`) resolves in your interactive shell but not in a service-spawned one. On Windows, a Task
Scheduler task has the same problem — it doesn't see PATH additions made by a shell profile — so
use the absolute path to the codex binary there too (typically `%APPDATA%\npm\codex.cmd`). See
`telegram-bridge/SETUP.md`'s PATH note if anything other than an interactive session or a
dispatched agent will invoke it.

## Login

`codex login` is an interactive OAuth flow, normally run by whoever owns the OpenAI account it
authenticates. Before first use, an agent checks auth state with:

```bash
codex login status
```

If not logged in, that's a graceful-degradation case (below), not something to work around.

## Headless invocation

`codex exec` is the `claude -p` equivalent — one-shot, non-interactive:

```bash
codex exec "<prompt>"
```

Key flags:

- `-o, --output-last-message <file>` — write only the final reply to a file under
  `.coordinator-scratch/` (skip the run log).
- `-s, --sandbox <read-only|workspace-write>` — sandbox level; `read-only` for review/opinion
  work, `workspace-write` only if it genuinely needs to edit files.
- `--skip-git-repo-check` — required when running outside a git repo.
- `-C <dir>` — run with a different working directory.
- `--json` — machine-readable event output.

Approval defaults to never in exec mode. On some CLI versions `--ask-for-approval` doesn't exist —
if a flag errors as unrecognized, try again without it before assuming the install is broken.

## Usage pattern

The Codex call is made from the dispatched reviewer's supported shell tool, following the
project's AGENTS.md or CLAUDE.md role boundary. For qualifying task types (UI/UX design,
copy/copywriting, research, document review),
the coordinator writes the codex instruction into the agent's brief: what to ask, which sandbox
level, and what to do with the answer (present alongside the primary model's alternative when the
choice is user-facing; adopt outright for mechanical asks).

## Graceful degradation

If codex isn't installed or isn't logged in, don't block and don't retry around it: proceed
with the available review and record the limitation once in the canonical task record. Mention
it in a completion/status report only when the project's notification policy calls for one;
do not create a checkpoint ping in decisions-only mode. The second opinion is an enhancement,
never an implicit dependency or permission to install/configure tools beyond the task's scope.
An explicitly required second opinion, such as the UX audit's design review, follows that
workflow's pending/waiver rule instead of this optional-review fallback.
