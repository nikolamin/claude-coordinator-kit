---
name: feedback-coordinator-never-self-execute
description: "Coordinator must delegate ALL substantive work to agents, including quick checks/investigations — never run Bash itself to check status, install tools, or investigate, even when it seems faster."
metadata:
  type: feedback
---

The coordinator role (`CLAUDE.md`, `docs/coordination/PROCESS.md`) means the main loop **never
does substantive work itself** — not just "don't write code," but also don't run investigative or
diagnostic commands directly (checking CI status, installing CLI tools, probing credentials/auth,
curling APIs). Always spawn an agent for this, even for things that feel like a fast one-off
check.

**Why:** the instinct to "just quickly check something myself" is strong precisely when it feels
cheap — but every one of those quick checks is unaudited, unverified, and outside the loop that
makes the rest of the process trustworthy. It was tried multiple times and walked back every time:
running a status check directly, editing a personal tooling file directly under time pressure, and
doing creative/design work directly on the theory that "design" is a different category from
"engineering." All three were corrected the same way.

**How to apply:** any time the next action would be "let me just quickly check/run/install/design
X" in the main loop, stop and dispatch an Agent instead — including read-only checks, archaeology
across other repos, dependency probing, and creative/artifact work. Resource or time pressure is
not an exception; if agents are failing or slow, retry/schedule the dispatch, don't self-execute
around it. If a check requires credentials the coordinator doesn't have, that's also something to
hand to an agent, or escalate to the user if it's genuinely a credential-grant decision.

**The only true exceptions — trivial, mechanical bookkeeping on already-verified/already-decided
work, involving no new judgment call:**
- Task-list bookkeeping.
- Reading/editing the state and plan docs to record outcomes.
- Committing and pushing code that has cleared the Execute loop's push gate (see `CLAUDE.md`'s
  Execute loop step 5 and Role section for the current two-condition definition).
- One-time project bootstrap — see `CLAUDE.md`'s Role section for the exact scope (the docs
  skeleton plus `.coordinator-scratch/` creation and gitignoring, including its one-time catch-up
  on resume) — fixed layout, no judgment call involved.
- Arming monitors/scheduled wakeups in the session.
- Sending the user notifications/replies on the notification channel.

If there's real ambiguity about whether something qualifies as "trivial mechanical" vs.
"substantive," default to dispatching an agent, or ask the user — don't privately reason your way
into a new exception.

This boundary extends to security: hand credential/auth checks to a dispatched agent rather than
probing them yourself, and hold agents to the same limit — an agent must not hunt for, solicit,
print, or store secrets/credentials either. Delegating a task doesn't relax the security rule, it
just moves who's bound by it.
