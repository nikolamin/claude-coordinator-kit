---
name: feedback-scratch-directory-writes
description: "Every write - by the coordinator or any dispatched agent - stays inside the project directory (except the kit's own install-approved paths); use .coordinator-scratch/ for anything scratch/temporary. A write outside the project (/tmp, home dir, a sibling dir) triggers a Claude Code permission prompt that never reaches the notify channel, so the session sits blocked rather than idle, indistinguishable from a hung agent."
metadata:
  type: feedback
---

All writes stay inside the project directory — never `/tmp`, never a home-directory path, never a
sibling directory — except the kit's own already-approved paths named in `CLAUDE.md`'s Agent brief
hygiene section (the rule targets a location the coordinator or an agent invents for itself, not
those). Scratch files, intermediate output, generated reports, temp scripts, downloaded fixtures:
all of it goes under `.coordinator-scratch/` at the project root. This binds the coordinator itself
and every agent it dispatches.

**Why:** a write outside the project root triggers a Claude Code permission prompt, and that prompt
renders only in the Claude Code UI — it does not reach the notify channel. On a channel like
Telegram, the founder sees nothing at all; the session isn't idle, it's blocked waiting on a click
nobody knows to make. A watchdog wakeup does not rescue this: the session isn't stalled in the
sense a watchdog checks for, it's actively waiting on input, so from the notify channel side it is
indistinguishable from a hung agent or a lost completion event (see the watchdog-keep-looping
memory — the same "looks like a hung agent from the outside" shape, triggered here by a UI-only
prompt instead of a genuinely stuck process) — except no amount of re-checking or re-dispatching
fixes it, because the fix is a click the founder doesn't know to make.

The general principle behind this specific rule: don't take an action whose permission prompt
can't reach the notify channel. The out-of-project write is the instance that has actually caused a
stall; the principle is what lets a future session recognize a new case that isn't literally a file
write but has the same shape (any action gated by a UI-only prompt with no out-of-band echo).

**How to apply:**
- Default every file write — coordinator or agent — to a path inside the project. Use
  `.coordinator-scratch/` at the project root for anything that doesn't belong in the committed
  `docs/` tree; see `CLAUDE.md` for the exact path and how it's bootstrapped/gitignored.
- Before reaching for `/tmp` or a path outside the repo out of habit, stop and redirect to
  `.coordinator-scratch/` instead — this isn't a style preference, it's what keeps the session
  from going silently blocked.
- Every dispatched agent's brief must restate this explicitly. Subagents share none of the
  coordinator's context or memory, so a brief that doesn't name the constraint will produce an
  agent that writes wherever seems convenient, including outside the project.
- If a task is ever genuinely blocked by needing to write outside the project (rare — most "needs
  /tmp" instincts are just old habit), treat it as a real blocker per the founder-only-action stop
  conditions, not something to route around silently.
