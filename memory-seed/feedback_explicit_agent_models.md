---
name: feedback-explicit-agent-models
description: "Always set the Agent model explicitly (sonnet for builds, opus for verifiers) — never let agents inherit the coordinator's model, which may be a different/expensive tier."
metadata:
  type: feedback
---

Every `Agent` dispatch must set `model` explicitly.

**Why:** the Agent tool inherits the session's own model when `model` is omitted. If the
coordinator session itself is ever switched to a different or more expensive model tier (e.g. via
`/model`), every agent dispatched without an explicit `model` silently runs on that tier too. The
user pays for that difference without having asked for it.

**How to apply:** every Agent dispatch in this project sets `model` explicitly — `sonnet` for
build/fix/infra agents, `opus` for adversarial verifiers (the established quality split). Never
omit the field regardless of what the coordinator itself is running on. If a task genuinely
warrants a different tier (a tiny mechanical fix → `haiku`; a hard-stuck escalation → the specific
tier named for that in `CLAUDE.md`'s Model routing section, per the escalation protocol), set that
explicitly too — never let it default silently.

First-session check: confirm the environment's Agent tool actually accepts these tier names before
relying on them everywhere — if a dispatch errors on an unrecognized `model` value, check the
tool's valid identifiers and update `CLAUDE.md`'s Model routing section to match before continuing.
