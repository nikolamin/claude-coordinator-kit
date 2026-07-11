---
name: feedback-questions-one-by-one
description: "Founder-facing questions (concept interview, plan gates, escalations, attention pings) must be asked one at a time, each with context + reasoning + 2-4 options and a recommendation — never a batched list."
metadata:
  type: feedback
---

Every founder-facing question — concept-interview questions, plan-gate decisions, escalations,
attention pings — is asked **one at a time**, never dumped as a numbered list or a batched
questionnaire in a single message or a single notification ping.

**Why:** founder correction — batched question lists get ignored or half-answered (the reader
answers question 1 and 3, skips 2 and 4, or answers all of them shallowly to get through the
list), and the one decision that actually blocks progress gets buried among the others instead of
standing on its own. A single, well-framed question with real options gets a real answer; five
questions in one message get a skim.

**How to apply:** every question — in the main loop or over the notify channel — carries three
parts: (1) one line of context, what this blocks or why it's being asked now; (2) the
coordinator's own reasoning, briefly — what the agents found, what the actual trade-off is, not
just "which do you want"; (3) 2-4 concrete options with a one-line trade-off each, plus a marked
recommendation when one exists. Maintain a queue when more than one item needs an answer: send the
top question, wait for the answer (or an explicit "park this" from the founder), then send the
next — never advance to the next question before the current one resolves. In-session, prefer the
`AskUserQuestion` tool if the environment has one (it renders options natively; fold the reasoning
into the question text). Over an out-of-band notify channel (Telegram, Slack, email), use the same
three-part structure in plain text — the channel changes, the protocol doesn't.

This does not relax the "one ask per ping" rule in `CLAUDE.md`'s Comms register — that rule and
this one are the same discipline applied at two altitudes (don't stack multiple asks in one
notification; don't stack multiple questions in one turn of the interview either).
