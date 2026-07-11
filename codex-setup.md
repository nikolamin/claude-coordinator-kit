# Codex / GPT second-opinion — setup

Optional. Gives the coordinator's dispatched agents a second, differently-trained model opinion
(GPT, via OpenAI's Codex CLI) on judgment-heavy work: UI/UX design decisions, copy/copywriting,
research tasks, and reviewing generated documents. Why bother: a coordinator that only
self-reviews with the same model family has a blind-spot problem — a second model catches
different failure modes. See `CLAUDE.md`'s Escalation section for when it fires; this file covers
install and invocation.

## Install

```bash
npm install -g @openai/codex
```

Requires Node. Same PATH gotcha as the Telegram bridge: launchd/systemd-spawned processes get a
minimal `PATH` that excludes nvm/homebrew-managed bin dirs, so a bare `codex` (like a bare
`claude`) resolves in your interactive shell but not in a service-spawned one — see
`telegram-bridge/SETUP.md`'s PATH note if anything other than an interactive session or a
dispatched agent will invoke it.

## Login — user-only, hard rule

**The user must run `codex login` themselves.** An agent or coordinator may install the CLI, but
NEVER authenticates on the user's behalf — it does not run `codex login`, does not drive or relay
the OAuth flow, does not handle, request, or store any credential or token for it. This is the
same boundary as `CLAUDE.md`'s Security boundaries section; installing a tool and authenticating
to a service are different categories. Before first use, an agent checks auth state with:

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

- `-o, --output-last-message <file>` — write only the final reply to a file (skip the run log).
- `-s, --sandbox <read-only|workspace-write>` — sandbox level; `read-only` for review/opinion
  work, `workspace-write` only if it genuinely needs to edit files.
- `--skip-git-repo-check` — required when running outside a git repo.
- `-C <dir>` — run with a different working directory.
- `--json` — machine-readable event output.

Approval defaults to never in exec mode. On some CLI versions `--ask-for-approval` doesn't exist —
if a flag errors as unrecognized, try again without it before assuming the install is broken.

## Usage pattern

The codex call is made **from within a dispatched agent's Bash** — the coordinator never shells
out itself (see `CLAUDE.md`'s Role section; a "quick codex check" is investigative Bash like any
other). For qualifying task types (UI/UX design, copy/copywriting, research, document review),
the coordinator writes the codex instruction into the agent's brief: what to ask, which sandbox
level, and what to do with the answer (present alongside a Claude-native alternative when the
choice is user-facing; adopt outright for mechanical asks).

## Graceful degradation

If codex isn't installed or isn't logged in, don't block and don't retry around it: proceed
Claude-only, and note it once in the next checkpoint ping ("codex second-opinion unavailable —
install/login per codex-setup.md if wanted"). One note, not a nag — the second opinion is an
enhancement, never a dependency.
