---
name: feedback-watchdog-keep-looping
description: "A coordinator that goes silently idle waiting on a notification that never fires is a failure mode as real as self-executing - arm watchdogs on in-flight agents and never stop the loop silently."
metadata:
  type: feedback
---

A coordinator session that stops and waits silently — because a completion notification never
fired, an agent hung, or a batch closed and nothing else was obviously queued — is not "being
careful," it's stalled without anyone knowing it's stalled.

**Why:** founder correction, prompted by "why can't you simply keep looping?" — the coordinator
had gone dormant waiting on something that was never going to arrive on its own, instead of
noticing the silence and acting on it. A paused coordinator that never says it's paused is exactly
as bad as one that quietly does substantive work itself: both leave the founder unable to trust
what's actually happening without asking.

**How to apply:**
- Whenever agents are in flight, arm a fallback scheduled wakeup (ScheduleWakeup/Monitor or
  equivalent, a long interval like 20-30 minutes) in addition to any completion notification the
  agent tool provides, specifically so a hung agent or a dropped completion event doesn't strand
  the session. Record enough about each in-flight agent in `docs/coordination/STATE.md` (task id,
  what it's doing, dispatch time, expected duration, watchdog armed y/n) that the wakeup — or a
  completely fresh session — can audit it later.
- On wake or notification, check every in-flight agent's status. Stall heuristic: running well
  past its expected duration with no new output, or missing from tracking entirely → treat it as
  stalled/lost, stop it if needed, and re-dispatch with a sharpened brief. Do this **without
  asking the founder first** — this is the same autonomy as the existing
  coordinator-autonomy-on-recovery rule (re-dispatching a lost/stuck/failed agent is routine
  mechanics, not a decision), just triggered by a watchdog instead of an immediate failure
  signal — unless `STATE.md`'s Durable decisions records a suspension of autonomous dispatch
  still in force, in which case report the stall there and to the founder instead of
  re-dispatching.
- If a batch closes and the only outstanding thing is founder input, don't go dormant silently:
  send the one queued question (see the questions-one-by-one memory), arm a periodic wakeup to
  re-check the notify channel/inbox and the plan doc, and say so plainly in the checkpoint ping
  ("idle on founder input, nothing else queued") instead of just stopping and hoping someone
  notices.
- Watchdogs are within-session only. Cross-session continuity is `docs/coordination/STATE.md`'s
  job — a fresh or resumed session reads its in-flight list and re-dispatches anything that died
  with the previous session, the same way it would recover from a within-session stall — unless
  `STATE.md`'s Durable decisions records a suspension of autonomous dispatch still in force, in
  which case it reports each dead/stalled agent's status instead and waits for the founder to
  explicitly lift the suspension before re-dispatching.
