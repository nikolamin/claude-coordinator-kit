---
name: feedback-agent-deferral-watcher-pattern
description: "Dispatched agents facing a long blocking call sometimes arm a watcher for themselves and end their turn 'standing by' instead of making the call and reporting the result - briefs for long-blocking-call tasks must forbid this explicitly."
metadata:
  type: feedback
---

A dispatched agent given a task with a long-running blocking call in it — a multi-minute build, a
live API round-trip — sometimes solves the "this will take a while" problem by arming a
watcher/background monitor for its own work and ending its turn with something like "standing by
for the result," instead of just making the call and reporting what actually happened.

**Why:** this looks superficially like good citizenship (not blocking the parent) but it's a
non-answer dressed as progress — the coordinator, or a verifier reading the agent's output, can
mistake "standing by" for a passed check when nothing has actually been verified yet. Observed 3x
in one real session: an agent facing a slow step deferred to a watcher of itself rather than just
waiting the call out. Agents don't get to background their own single-turn task — only the
coordinator manages watchdogs on agents, per its own Watchdogs / never stall rules.

**How to apply:** any coordinator brief for a task with a long blocking call must say explicitly:
"run it as one blocking foreground call and report the actual output; do not background it or set
up watchers for yourself." If an agent still returns a "standing by" non-answer instead of a
result, treat it the same as any other failed/incomplete task — re-prompt or respawn with the
sharpened brief, don't accept the deferral as a pass.
