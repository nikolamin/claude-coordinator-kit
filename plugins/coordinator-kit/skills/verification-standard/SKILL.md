---
name: verification-standard
description: Establish trustworthy independent acceptance evidence, fail-first controls, live UI checks, and honest test coverage. Use when briefing or evaluating a verifier or before sharing a demo. Push scheduling and evidence reuse belong to execute-loop.
---

# Verification standard

An independent verifier checks the original requirement and actual artifact, not agreement with
another agent. Non-trivial work needs this pass; copy/comment/config-only changes are exempt
only when behavior, policy and routing are unchanged. Record which property, revision, environment
and user flow the evidence covers. A data-scoping audit does not establish authorization or
read-only access.

## Evidence that can fail

- For a regression, show the relevant test failing on the unfixed behavior and passing on the
  fix. A focused revert/mutation is useful when a base run cannot isolate it. Record the actual
  command, exit code, failing assertion and restored pass; prose describing a hypothetical fail
  is not proof. Keep the experiment proportionate to the change.
- Safety assertions need a negative control: deliberately break the guarded behavior and show
  the guard detects it. Assert a nonzero denominator; zero leaks from zero exercised requests
  proves nothing. Await async effects so a swallowed error/pending promise cannot fake green.
- Test observable outcomes, not just a mocked method call or a source substring. Fixtures must
  match the real schema/API and use independent expected values; deriving expectations from
  the same broken constant certifies the bug. Include important boundaries and cross-surface
  consumers; handpicked passing examples need not cover the actual failure range.
- Choose mutations by failure mechanism, including wiring/call sites, not only helper internals.
  A killed-mutant ratio applies to that chosen set, not all behavior. Investigate surviving
  mutants before calling them equivalent. Ensure the changed source actually compiled.
- Mutation work needs exclusive ownership, a snapshot/backup and an in-flight marker, followed
  by exact restoration and a clean intended diff (`coordinator-kit:agent-brief-hygiene`).
- Separate measured facts from severity/inference; use a baseline for anomaly claims. Numbers
  need a timestamp and source. Scratch reports, cached inboxes and an agent's memory are not
  proof of current production state.

## Suites and the push gate

Use `coordinator-kit:execute-loop`'s revision/environment evidence contract. Independently inspect
coverage and run targeted adversarial checks; do not rerun the same full suite solely because a
new verifier arrived. Report passed, failed **and skipped** counts, named failure sets, commands,
exit codes and environment. A green run with disabled DB tests or zero collected tests is not a
pass. Required integration tests exercise real isolated dependencies. The final push candidate
must also satisfy its build/typecheck/lint gates; tests alone need not catch a broken build.

Pre-existing failures require a matched base comparison. A failure on an untouched file can be
shared-tree/resource interference; establish attribution instead of changing unrelated code.
Local gate evidence permits an authorized push; required green CI and deployed-flow evidence
close the corresponding post-push stage. Do not label a test deployment as production completion.

## Live surfaces

- Browser-visible work requires live click-through on the candidate running locally or in a
  permitted test environment before push. Start/navigate/click/read the rendered result;
  curl, source inspection or a component test alone do not prove the user flow.
- Before a demo/playtest link ships, exercise the full journey at the actual URL through its
  completion signal. Deployed checks are separate from a builder's pre-push local checks.
- Required browser/device verification blocked by login, infra, or physical hardware remains
  **blocked**, even if disclosed. Resolve authorized prerequisites and escalate the remaining
  user-only step before calling the work shippable. An explicitly accepted exception must name
  the missing leg; do not silently lower the criteria.
- Permission-gated browser APIs may behave differently under automation. Record what was
  actually exercised; an auto-denied dialog does not prove the allowed path works. Keep that
  required leg pending for an appropriate environment or manual check.
- Measure `window.innerWidth` and `window.innerHeight` after a resize; requested presets can
  silently no-op or produce 0x0. Attribute findings to measured dimensions. Screen-visible
  Android/desktop work likewise needs the relevant screen/device, not only text assertions.
- Own the browser tab/session, confirm current host/environment before each mutating sequence,
  and serialize shared personas. A cached console/network buffer may belong to a different
  context; confirm provenance before filing a defect.

## Specialized checks when relevant

- Deploy/infra: verify executable bits and real process/artifact identity, not content alone.
- Diagnostics: retain stderr and exit codes; a failed query with suppressed errors can look
  exactly like an empty successful result.
- Monitoring/detectors: backtest real history with controlled clock movement. "Resolved"
  requires improved evidence, not an incident merely aging out of a lookback window. Validate
  the backtest's own selection/gating logic with positive and negative controls.
- Email/queue delivery: check the authoritative source read-only (for IMAP, read-only mailbox
  selection and BODY.PEEK), not only a lagging local mirror. Respect access/data constraints.
- Database column rename/drop: inspect DB-resident views/dependent objects beyond the repo.
  Enforce read-only production access structurally; validate controls without risking a real
  production write. Keep local test data and outbound integrations isolated.
