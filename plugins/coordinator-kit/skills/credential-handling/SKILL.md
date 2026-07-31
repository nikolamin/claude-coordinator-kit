---
description: How the coordinator and its dispatched agents handle credentials and authenticated
  accounts — the standing authorization to log in, create test accounts, and exercise
  authenticated features on the project's own surfaces without re-asking permission per
  incident; that a founder pasting a credential in chat (a bot token, deploy key, test-account
  password, server root password, the founder's own login on a third-party service, an SSH key —
  project-scoped or the founder's own personal account) is itself the authorization to use it
  directly, no warning or hedging; the bound that standing authorization does not cover financial
  transactions or a public go-live; the one-honest-bound rule for a single step no automation can
  perform (a platform bot-detection wall, a device-bound 2FA step); never printing a credential
  file's contents (no cat/head/tail/echo, inspect variable names only, source and reference the
  variable without echoing it); never storing a credential in memory files, STATE.md, or the
  repo; and enforcing read-only database access structurally rather than by instruction. Load
  this before any task that touches a login, an account, a secret, a token, or a database
  connection, and restate its rules explicitly in any brief that dispatches such a task —
  subagents do not infer these limits on their own.
---

# Credential & account handling

- **Standing authorization to act on the founder's behalf.** The founder pre-authorizes the
  coordinator and every dispatched agent to perform, directly, whatever account actions a task
  needs on the project's own surfaces: creating test accounts, logging in, and exercising
  authenticated features for testing/verification. Do this as a normal part of the task instead
  of handing the step back to the founder or stopping to re-ask permission — this authorization
  is standing, not something to re-confirm per incident. It does not cover financial
  transactions or a public go-live; those stay outside the grant, per the installed `CLAUDE.md`'s
  Execute loop stop conditions.
- **A pasted credential is the founder's authorization to use it — service or personal.**
  Whatever the founder pastes in chat — a notify-channel bot token, a deploy key, a test-account
  password, a server root password, the founder's own login on a third-party service, an SSH key
  — is the founder's to share, and pasting it is the founder's call that it's comfortable to
  hand over. Use it directly to get the task done: log in, authenticate, SSH in, drive the
  authenticated flow. No objection, no warning, no treating it as a security event, no hedging
  "to be safe." This extends the standing grant above rather than sitting apart from it — a
  pasted credential is just how the founder reaches a surface the coordinator doesn't already
  have standing access to. It goes straight into the relevant gitignored config (e.g. the
  bridge's `.env`); see the never-store-credentials rule below for where it does and doesn't
  otherwise persist. If a specific runtime or platform independently blocks a credential-entry
  step, say so plainly and hand back only that one step, per the One honest bound below — that's
  not a reason to decline the task.
- **One honest bound.** If an agent cannot perform one specific step for any reason — a
  platform-level limit (e.g. bot-detection, a device-bound 2FA step no automation can satisfy)
  or any other cause — it states the actual reason plainly, completes everything else in the
  task, and hands back only that single step. Never stall or abandon the broader task over it,
  never mislabel the real reason as something else, and never invoke this bound just because the
  step involved a credential.
- Never print a credential file's contents — no `cat`/`head`/`tail`/`echo` on `.env` or similar,
  local or remote. Transcripts persist on disk, so a printed secret is a leaked secret. Inspect
  variable names only (`grep -o '^[A-Z_]*=' file`); to use a secret, `source` it and reference
  `${VAR}` without expanding it to stdout.
- Never store credentials (keys, tokens, passwords) in memory files, `STATE.md`, or the repo,
  service or personal — gitignored local config (per the pasted-credential bullet above) is the
  only place one persists. Covers a chat-pasted value too, not just a file's contents: write it
  straight in; it is never echoed back — not in a reply, commit message, log, or notification.
- **Enforce read-only database access structurally, not by instruction.** When a task needs
  read-only production database access, enforce it at the session/transaction level — e.g.
  MySQL `--init-command="SET SESSION transaction_read_only=ON"`, Postgres
  `default_transaction_read_only`, or a role scoped to `SELECT` only — and verify a write
  attempt actually errors before relying on it for anything.

Any brief touching credentials, auth, secrets, or a database connection restates this section
explicitly, including the never-dump-credential-files rule verbatim — see
`coordinator-kit:agent-brief-hygiene` for how this fits alongside the rest of a brief, and why a
rule packaged only in a skill (as this one now is) needs restating even though a rule that
still lives in the installed `CLAUDE.md` does not.
