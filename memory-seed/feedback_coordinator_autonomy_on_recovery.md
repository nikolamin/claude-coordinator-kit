---
name: feedback-coordinator-autonomy-on-recovery
description: "User does not want to be asked before re-dispatching a lost/stuck/failed agent, or before starting the next unblocked plan task - that's routine coordination, handle it and keep going."
metadata:
  type: feedback
---

Re-dispatching lost/stuck/failed agents, re-prompting after a bad result, retrying a transient
failure, or starting the next unblocked task from the plan — this is routine execute-phase
mechanics per the build→verify→re-prompt loop, not a strategic or irreversible decision. Asking
for sign-off on it is noise, not diligence.

**Why:** the plan document already names the next unblocked task and its dependencies; asking
"what's next" when the plan answers that itself is the same class of noise as asking to
re-dispatch a lost agent. The build/engine portion of a task is not itself a decision point, even
for a large multi-agent task — only the pieces that explicitly require the user in the loop
(a live playthrough/demo, a public go-live, a credential) are.

**How to apply:** when an agent is lost, silently fails, or a task needs a straightforward retry/
re-dispatch, just do it — don't stop to ask. After closing one plan task, immediately dispatch the
next unblocked one per the plan's dependency graph, without an intervening turn asking permission.
This is distinct from genuinely novel decisions (which direction to build, whether to go live
publicly, which credential to use) — those still warrant a check. The line: if the answer is
"obviously yes, keep the pipeline moving," don't ask; if it's a real fork with user-only judgment,
do ask. Report progress via checkpoint notifications rather than by pausing and waiting for
acknowledgment.

This autonomy is not unlimited retrying: it covers re-dispatch/re-prompt mechanics, not overriding
an escalation trigger. If the same class of failure recurs 2+ times, that's a stuck-escalation
case (see the escalation-protocols memory), not another silent retry.

Note the "live playthrough/demo" that stays user-only is the user's own attendance/participation
(e.g. a final go/no-go session) — distinct from an agent's own pre-send verification playthrough
(see the verify-by-playing memory), which is mandatory, always agent-executed, and never something
to defer to the user.
