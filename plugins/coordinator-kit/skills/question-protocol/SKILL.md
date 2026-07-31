---
description: How the coordinator asks the founder/user any question — concept-interview
  questions, plan-gate decisions, escalations, attention pings, or any other point where a
  decision is needed before work can continue. Load this before sending such a question, in
  session (e.g. via an `AskUserQuestion`-style tool) or over a notify channel — it defines the
  four required parts (one-line context, the coordinator's own reasoning, 2-4 options with a
  marked recommendation, and the safe default if no answer arrives), the one-at-a-time rule
  against batching several questions into one message or a numbered questionnaire, how to run a
  question queue when more than one item needs an answer, and that a pending question blocks
  only the work that actually depends on its answer, not everything else in flight. Not for a
  status update or checkpoint ping that has nothing to ask (see coordinator-kit:comms-register
  for that), and not for a routine reversible choice with an obviously-correct default that
  never needed the founder in the first place.
---

# Question protocol

Governs every question the coordinator puts to the founder — concept-interview questions,
plan-gate approvals, escalations, attention pings. The installed `CLAUDE.md`'s Execute loop,
Escalation, and Watchdogs sections all route founder-facing questions through this protocol
rather than defining their own asking style; this skill is what "ask the founder" means in
practice.

Every founder-facing question is asked **one at a time**, never as a batched list or a numbered
questionnaire dumped in one message. Each question carries all four of:

1. One line of context: what this blocks / why it's being asked now.
2. The coordinator's own reasoning, briefly — what the agents found, what the actual trade-off
   is.
3. 2-4 concrete options with a one-line trade-off each, plus a marked recommendation when one
   exists.
4. The default action if no answer arrives — this must be safe, usually "do nothing yet."

Maintain a question queue when more than one item needs an answer: send the top question, wait
for the answer (or an explicit "park this"), then send the next question — never move on to the
next **question** before the current one resolves. That ordering rule is about questions, not
work: a pending question blocks only the work that actually depends on its answer — keep working
on everything else it doesn't block.

In-session, prefer an `AskUserQuestion`-style tool if the harness provides one (it renders
options natively) with the reasoning folded into the question text. Over a notify channel
(Telegram or similar), use the same four-part structure in plain text — see
`coordinator-kit:comms-register` for the notify-channel message format, cadence, and script
invocations.
