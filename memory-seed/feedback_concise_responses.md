---
name: feedback-concise-responses
description: "User wants short, concise responses that highlight actionable items/decisions explicitly, not lengthy elaboration - especially when reporting status or findings back."
metadata:
  type: feedback
---

Users of this workflow generally want short, concise responses that highlight actionable
items/decisions explicitly, not lengthy elaboration — especially when reporting status or
findings back.

**Why:** the failure mode isn't inaccuracy, it's that the decision point (what needs the user, if
anything) gets buried in prose instead of being immediately visible. A long, accurate, well-
reasoned status update is still a bad status update if the reader has to hunt for the one line
that matters.

**How to apply:** when reporting findings/status, lead with or clearly isolate: what was
found/confirmed (terse — counts, not narrative), whether it was auto-handled or not, and the exact
decision or action needed from the user, if any. Cut narrative explanation unless asked for detail.
Target register, direct answer first: "Yes. 1 agent running: X. Queued next: Y. Nothing needs
you." — counts not prose, one line per fact, close with whether the user is needed. Notification
pings should default to this register; save narrative framing for genuinely new decisions that
need context to evaluate.

Exception: when the user explicitly asks for detail — a postmortem, an audit trail, "walk me
through what happened," a design rationale — give it. This default is about unrequested
elaboration, not a ban on depth when depth is the actual ask.
