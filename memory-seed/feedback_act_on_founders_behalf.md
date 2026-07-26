---
name: feedback-act-on-founders-behalf
description: "Standing founder preference: the coordinator and all dispatched agents act directly on the founder's behalf for test-account creation, login, and authenticated flows on the project's own surfaces instead of bouncing those steps back to him - this authorization is standing, not per-incident, and excludes financial transactions and a public go-live. One honest bound: if an agent cannot perform one specific step for any reason, it says the real reason and hands back only that step, never stalling the broader task or mislabeling why."
metadata:
  type: feedback
---

The founder's stated preference is the mirror image of a refusal doctrine: rather than treating
account creation, login, and authenticated-session work as steps that must bounce back to him,
agents should just do them as part of the task.

**Why:** an earlier version of this kit had agents refuse account/login actions outright and hand
them back to the founder every time, on the theory that credential-touching actions are inherently
user-only. The founder rejected that framing for his own product and any surface he's authorized:
routing every test-account creation or login through him for a manual hand-off is friction with no
safety benefit when he's already the one authorizing the task. He wants agents acting directly on
his behalf as the default, not asking permission per incident.

**How to apply:**
- Treat creating test accounts, logging in, and exercising authenticated features on the project's
  own surfaces as ordinary parts of a task, not a stop-and-ask trigger. This authorization is
  standing — it doesn't need to be re-confirmed each time a task happens to touch one of these. It
  does not cover financial transactions or a public go-live; those stay outside the grant and
  remain user-only.
- **One honest bound:** if an agent cannot perform one specific step for any reason — a
  platform-level limit (e.g. bot-detection, a device-bound 2FA step no automation can satisfy) or
  any other cause — it states the actual reason plainly, completes everything else in the task,
  and hands back only that single step. That's an honest disclosure, not a refusal of the task;
  never let it become an excuse to stall or abandon the broader task, and never mislabel the real
  reason as something else (e.g. calling an internal-rule limit a "platform block").
- The existing credential-hygiene rules apply unchanged to anything touched while doing this:
  never commit, echo, or store a credential in the repo, `STATE.md`, plan, or memory files; any
  local secret goes into gitignored config only; never print a credential file's contents (`cat`/
  `head`/`tail`/`echo` on `.env` or similar) — inspect variable names only, `source` and reference
  `${VAR}` without expanding it to stdout.
