---
name: feedback-escalation-protocols
description: "When the coordinator or a dispatched agent hits a hard-to-overcome challenge, or an agent keeps failing to deliver, escalate to a higher-capability advice agent and/or a second-model opinion, rather than retrying the same approach indefinitely."
metadata:
  type: feedback
---

Two related but distinct escalation paths, both separate from the normal build→verify→re-prompt
loop:

**1. Stuck escalation.** If the coordinator or a dispatched agent hits a genuinely hard-to-overcome
obstacle — or a build/verify agent keeps failing to deliver after re-prompting — spawn another
agent on the highest-capability model tier available, specifically to ask for advice, passing it a
self-contained summary of what's been tried and what's blocking. Don't reach for this on routine
task failures (a build agent hitting one bug, a verifier finding a real issue) — that's what
re-prompting/respawning is for. Reach for it once the Execute loop's retry cap is hit — 2 failed
re-prompt/respawn cycles on the same gap, escalating on the 3rd failure — or when a design/
architectural question has no clear path forward from normal iteration.

**Why:** re-prompting the same approach repeatedly when it isn't working just burns cycles; a
differently-angled second pass (higher capability tier, or a differently-trained model — see
below) often breaks the loop where more of the same doesn't.

Use whatever specific model tier your project's `CLAUDE.md` names for escalation/advice in its
Model routing section — don't independently guess at "the highest-capability tier available";
the point is a named, deliberately-chosen tier reserved for this case, not whichever one sounds
biggest.

**2. Second-model opinion.** For judgment-heavy work — UI/UX design decisions, research tasks
where independent framing has real value, reviewing generated documents (legal drafts, specs,
copy) — get a second opinion from a differently-trained model if one is available in the
environment (e.g. a competing CLI tool shelled out to from within a dispatched agent). This is a
genuine independent critique pass, not a rubber-stamp read. Engineering-only work (wire types,
state plumbing, test scaffolding) doesn't need it — the trigger is judgment/perspective value, not
mechanical execution. Either adopt/adapt the second opinion's output, or present it alongside a
first-model alternative when the choice is user-facing.

**How to apply:** dispatch via the Agent tool (or equivalent) with the advice-tier model set
explicitly, prompt framed as "here's the situation, here's what's been tried, what would you try
next" — self-contained like any other agent dispatch. For the second-model-opinion path, note in
the agent brief which task types warrant it (design/research/document-review) so agents don't
reach for it on routine engineering work.
