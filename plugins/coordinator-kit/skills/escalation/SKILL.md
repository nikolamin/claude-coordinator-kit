---
name: escalation
description: Escalate repeated coordinator verification failures or unresolved architecture/judgment questions to advice or an optional second model. Use after the bounded retry loop is exhausted or another perspective could resolve a material choice.
---

# Escalation

After **two failed verify cycles on a task** the loop stops. `coord.py verify fail` counts them,
blocks the task at the cap and refuses another cycle; any finding counts, and a changed agent id
resets nothing. If the last verdict is a PASS for the task's target, deliver and file the rest.
Otherwise ask ONE fixed question (record it as a question with `type: verify_escalation`,
`cycle: N`, `tasks: [ID]`; `verify status ID` prints the fields):

1. Ship to the staging/test target as it is and file the open findings as tasks.
2. Cut scope to a named part that already passes.
3. One advice agent, then one last fix/verify cycle.
4. Park the task.

Default with no answer: no further fix agent; the task stays blocked while other lanes continue.
Options 1 and 2 need the target to be one the project already lets the coordinator deliver to;
otherwise they are the user's release decision. After option 3 is chosen, record the answer and
run `verify clear ID --question QID`: it permits exactly one more cycle. The advice-tier agent
uses the project's recorded model alias and gets the original criteria, failure evidence,
attempted fixes and constraints; ask what mechanism was missed and what to try next. A first
failure does not need an escalation.

For UI/UX, copy, research and document review, an available differently-trained opinion can
expose shared blind spots. Use `coordinator-kit:codex-second-opinion` from within the dispatched
agent when applicable. Preserve the project's explicit model/effort preference and confirm the
configured model is supported by the installed runtime. If unavailable, proceed with the available review
and record the limitation once. Engineering-only plumbing does not automatically need it.

The advice agent returns options and evidence, not production permission. The coordinator
chooses within existing authority or presents the concrete founder-only decision through
`coordinator-kit:question-protocol`; keep independent lanes moving.

Infra/execution briefs include: "Do not delegate; execute directly. Bulk output goes to the
named project scratch log; return decisive lines, counts, exit codes and evidence paths."
See `coordinator-kit:agent-brief-hygiene` for the complete bounded-work contract.
