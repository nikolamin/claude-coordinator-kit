---
name: feedback-backlog-discipline
description: "No suggestion-chip / side-backlog tools in this workflow - any follow-up or out-of-scope item found should be added directly into the plan doc or state doc instead."
metadata:
  type: feedback
---

This workflow runs off `docs/plan.md`/`docs/coordination/STATE.md` as the single source of truth
for pending work, not off ad-hoc chip suggestions or any other side-channel backlog tool.

**Why:** a second, parallel backlog of clickable suggestions the user has to separately triage
defeats the point of having one authoritative plan/state doc that any future session (or agent)
can read and trust as complete. Split sources of truth drift apart silently.

**How to apply:** never use a suggestion-chip or spawn-a-background-task tool in this project, even
when one is available in the environment. When an agent or the coordinator notices something
out-of-scope worth doing later — a follow-up, a cleanup, a gap — write it directly into
`docs/plan.md` (if it's already actionable as a standalone task with acceptance criteria) or
`docs/coordination/STATE.md`'s Open items section (if it's a note, caveat, or open question tied
to work already tracked elsewhere, not yet its own task), the same way every other pending item in
this project is tracked. This is specific to projects run with this plan/state-doc convention — a
project without one doesn't have this constraint, but if you've adopted this kit, you have the
docs, so use them.

This does not cover session mechanics like arming monitors or scheduled wakeups — those are
allowed coordinator actions for tracking in-flight work, not a side backlog of suggested future
work. The restriction is specifically about suggestion/backlog tools competing with
plan.md/STATE.md as the source of truth for pending work.
