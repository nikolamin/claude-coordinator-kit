---
description: When and how to escalate — spawning an advice-tier (fable) agent once the same
  class of problem has failed its 2 allowed re-prompt/respawn cycles (per
  coordinator-kit:execute-loop's retry cap) or a design/architecture question has no clear path
  from normal iteration, with a self-contained prompt summarizing what was tried and what's
  blocking, framed as "what would you try next" and never reached for on a first failure;
  routing UI/UX design decisions, copy/copywriting (marketing text, UX microcopy, landing-page
  text), research tasks, and generated-document review to a second, differently-trained opinion
  via `codex exec` (see coordinator-kit:codex-second-opinion for setup and invocation —
  engineering-only work like wire types or test scaffolding doesn't need this); and the
  no-delegation constraint every infra/execution agent brief must carry ("do not delegate,
  execute directly, paste raw command output") so an agent with Agent/SendMessage access doesn't
  spiral into agent-to-agent delegation instead of doing the work. Load this when an agent has
  failed the same gap twice in a row, when a judgment-heavy task (UI/UX, copy, research,
  document review) needs a second, differently-trained opinion, or when writing any
  infra/execution agent's brief. Not for counting retry cycles or defining what "same gap" means
  in the first place (see coordinator-kit:execute-loop), and not for the codex install/auth/
  invocation mechanics themselves (see coordinator-kit:codex-second-opinion).
---

# Escalation

This skill packages `CLAUDE.md`'s Escalation section for delivery via a plugin. If this
project's coordinator uses the file-copy install, the project-root `CLAUDE.md` already carries
this exact content under its own "Escalation" heading — this skill is a second, parallel
delivery path for the same rules, not a replacement.

- If an agent hits `coordinator-kit:execute-loop`'s retry cap on the **same class of problem** —
  2 failed re-prompt/respawn cycles, escalating on the 3rd failure — or a design/architecture
  question has no clear path forward from normal iteration, spawn an agent with the advice tier
  (`fable`, per `CLAUDE.md`'s Model routing section) for advice. Prompt: self-contained summary
  of what was tried and what's blocking, framed as "what would you try next." This is distinct
  from routine re-prompting — don't reach for it on a first failure.
- For UI/UX design decisions, copy/copywriting (marketing text, UX microcopy, landing-page
  text), research tasks, and reviewing generated documents, additionally shell out to
  `codex exec` (OpenAI Codex CLI, if installed and authenticated) from within a dispatched agent
  for a second, differently-trained opinion — see `coordinator-kit:codex-second-opinion` for
  install, auth, and invocation mechanics. Present its output alongside a Claude-native
  alternative when the choice is user-facing; adopt it outright for mechanical asks.
  Engineering-only work (wire types, plumbing, test scaffolding) doesn't need this — the trigger
  is judgment/perspective value, not mechanical execution.
- An agent given unrestricted `Agent`/`SendMessage` access can spiral into agent-to-agent
  delegation instead of doing the work. For any infra/execution task, the brief must include:
  **"do not delegate, execute directly, paste raw command output."**
