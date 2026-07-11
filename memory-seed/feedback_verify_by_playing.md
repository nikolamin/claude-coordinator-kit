---
name: feedback-verify-by-playing
description: "Before sending the user any demo/playtest link, a verifier must actually exercise the flow end-to-end in a real browser (a full round/journey), not just verify connectivity - connect-and-render is not the same as working correctly."
metadata:
  type: feedback
---

A flow that "verified end-to-end" by checking page load, a WebSocket handshake, and rendered
state can still be serving the wrong data entirely — the wrong fixture, stale content, a broken
core interaction — while every connectivity-level check stays green.

**Why:** connectivity checks (loads / connects / renders) pass even when the CONTENT is wrong.
The failure mode isn't the infrastructure — every layer a connectivity check touches can be green
while the thing the user actually cares about (does the game/flow/feature work as intended) is
broken. The gap is that no one exercised the flow AS THE USER WOULD before handing it over. A
claim isn't verified until the actual acceptance behavior is observed, not just its transport.

**How to apply:** before any user-facing link/demo/playtest goes out, dispatch a verification step
that plays the actual flow in a real browser at the real URL. This should be the independent
verifier from the normal build→verify loop, not the same agent that built/set up the flow —
self-verification is exactly the blind spot that let the wrong-fixture case above ship. For an
interactive/game flow, play at least one full round/cycle across the relevant roles (e.g. every
seat in a multiplayer game, both sides of a login/logout cycle, a full checkout, an admin-approval
step) and confirm the mechanics visibly work (state changes propagate, turns/steps advance
correctly, the right data is present) — these are illustrative examples, not an exhaustive list;
match the check to what "one full use" actually means for the specific flow. For a journey/UI
flow, click it through to its completion signal. The check must validate CONTENT sanity (is this
the right fixture/rules/data?), not just transport. If the flow can't be exercised end-to-end for
some reason, say so to the user explicitly instead of implying it was fully verified.
