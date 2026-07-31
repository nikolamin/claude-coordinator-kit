---
description: Keeping a coordinator session from going silently idle — arming a fallback
  scheduled wake-up (a long-interval Monitor or cron-equivalent, 20-30 min) whenever agents are
  in flight, recording each in-flight agent in STATE.md's Current section with the in-flight
  schema (task id, what it's doing, model tier, dispatched at, expected duration, watchdog
  armed y/n), the stall heuristic for treating an agent as lost and re-dispatching it with a
  sharpened brief, what to do when a batch closes and the only outstanding thing is founder
  input, cross-session recovery of agents that died with a prior session, the blocked local
  permission-prompt failure mode (an out-of-project write like /tmp trips an allow-click prompt
  invisible on the notify channel), and the dead-in-session-listener check (a producer can stay
  perfectly healthy while the listener reading it has died — compare the watched file's own
  tail against the last message actually processed, never producer health alone). Load this on
  any wake-up, notification, or session resume; whenever agents are in flight and none has
  reported back yet; when a batch just closed with nothing left queued but a founder question;
  or when deciding whether silence means genuinely idle versus something stuck unseen. Does not
  cover the session stop/resume protocol itself (the stop half is
  coordinator-kit:stop-and-save, the resume half is coordinator-kit:bootstrap) or what makes a
  build/verify cycle correct (see coordinator-kit:execute-loop).
---

# Watchdogs / never stall

This skill packages `CLAUDE.md`'s Watchdogs section for delivery via a plugin. If this project's
coordinator uses the file-copy install, the project-root `CLAUDE.md` already carries this exact
content under its own "Watchdogs / never stall" heading — this skill is a second, parallel
delivery path for the same rules, not a replacement. This skill covers detecting and recovering
from stalls; it deliberately excludes the founder-triggered session stop/resume protocol
("stop and save your step" / "bootstrap yourself"), which is packaged separately across two
skills — the stop half ("stop and save your step") as `coordinator-kit:stop-and-save`, the
resume half ("bootstrap yourself") as `coordinator-kit:bootstrap` — load whichever half applies
for session-boundary handling.

A coordinator sitting silently idle — waiting on a notification that never arrives, or simply
stopping after a batch closes — is a failure mode as real as self-executing. Never go dormant
without an armed way to wake back up.

- **Whenever agents are in flight**, arm a fallback scheduled wake-up — a long-interval Monitor,
  a scheduled-task/cron mechanism, or whatever equivalent recurring-check tool the harness
  provides (20-30 min) — in addition to whatever completion notification the agent tool
  provides, so a hung agent or a lost completion event doesn't strand the loop. Record each
  in-flight agent in `docs/coordination/STATE.md`'s Current section using the in-flight schema
  (task id, what it's doing, model tier, dispatched at, expected duration, watchdog armed y/n)
  so a wakeup or a resumed session can audit them.
- **On wake or notification**, check every in-flight agent's status/output. Stall heuristic:
  still running well past its expected duration with no new output, or missing from tracking
  entirely → treat as stalled/lost, stop it if needed, and **re-dispatch with a sharpened
  brief** — without asking the founder first (see `coordinator-kit:execute-loop`'s "re-dispatch
  is routine, not a decision" for the same autonomy applied to any lost/stuck/failed agent) —
  unless a recorded suspension of autonomous dispatch is in force (see
  `coordinator-kit:execute-loop`), in which case report the stall in STATE.md and to the founder
  instead of re-dispatching.
- **If a batch closes and the only outstanding thing is founder input**, don't go dormant
  silently: send the one queued question (see `CLAUDE.md`'s Question protocol), arm a periodic
  wakeup to re-check the notify channel/inbox and `docs/plan.md`, and say so plainly in the
  checkpoint ping ("idle on founder input, nothing else queued") rather than just stopping.
- **Cross-session:** watchdogs only cover the current session. A fresh/resumed session's job is
  to read `docs/coordination/STATE.md`'s in-flight list and re-dispatch anything that died with
  the previous session — that's what the STATE.md tracking above is for — **unless a recorded
  suspension of autonomous dispatch is in force** (see `coordinator-kit:execute-loop`), in which
  case report each dead/stalled agent's status in STATE.md and to the founder, but do not
  re-dispatch until the founder explicitly lifts the suspension. Otherwise a session boundary
  alone would silently violate the founder's own standing instruction.
- **A blocked local permission prompt reads as silence, not idle — a wakeup won't rescue it.**
  General rule: never take an action whose approval prompt can't reach the notify channel. The
  instance that has actually bitten: a write outside the project root (e.g. `/tmp`) triggers a
  Claude Code allow-click prompt visible only in the local UI, so the session is genuinely
  blocked on an unseen click, not idle. Symptom: indistinguishable from a hung agent or lost
  completion event on the notify channel — suspect this too when a wakeup finds silence and no
  stalled agent. Write scratch/output only inside the project (`.coordinator-scratch/`; see
  `CLAUDE.md`'s Agent brief hygiene section, including its narrow exemption for the kit's own
  named, install-approved paths).
- **A dead in-session listener reads as silence too — and no producer-side check can see it.**
  Every 2-3 idle ticks, compare the watched inbox file's last line (or mtime/line count — e.g.
  a bridge's relay-inbox file) against the last message this session actually processed:
  producer health (a scheduler job up, a bot log flowing) only proves delivery **to the file**,
  never **to the session**, so it will confirm "silence is genuine" while messages sit unread.
  On a mismatch, re-arm the listener **and** process the missed backlog (react/reply), not just
  re-arm. Restart kills every monitor outright too, and every task id changes each time — re-arm
  fresh on resume, never by a carried-over id (see `coordinator-kit:bootstrap` for the
  founder-triggered resume path this feeds into).
