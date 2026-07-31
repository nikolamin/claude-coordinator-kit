---
description: What counts as an actual pass, not a rubber-stamp, when verifying a build agent's
  work — the non-trivial heuristic for whether a task needs an independent verifier (treat as
  non-trivial unless it's a pure config/copy/comment tweak; when unsure, non-trivial), high test
  coverage over a happy-path smoke test, live click-through in a real browser for anything
  browser-visible (not curl, not reading source and assuming), playing a demo/playtest flow
  fully end-to-end before the link goes out, disclosing permission-gated browser APIs
  (notifications, camera/mic, geolocation) as unverifiable-by-automation, not a false pass on an
  auto-denied dialog, confirming file modes (executable bits) survived a deploy,
  local-green never substituting for a confirmed-green CI run, never blanket-suppressing stderr
  on a diagnostic feeding a real conclusion, backtesting a monitoring/detector surface against
  real history instead of synthetic fixtures, a browser viewport resize call that can silently
  no-op, a green test run that can be silently skipping tests rather than passing them, and a
  column rename/drop that can break a database view invisibly. Load this when writing or
  checking a verifier agent's acceptance criteria, before declaring a task's tests "passing,"
  before any user-facing demo or playtest link goes out, or when a check that should have caught
  a regression somehow didn't. Not for whether a task needs a verifier, what happens on
  verification failure, or the retry cap (see coordinator-kit:execute-loop).
---

# Verification standard

This skill packages `CLAUDE.md`'s Verification standard section for delivery via a plugin. If
this project's coordinator uses the file-copy install, the project-root `CLAUDE.md` already
carries this exact content under its own "Verification standard" heading — this skill is a
second, parallel delivery path for the same rules, not a replacement. See
`coordinator-kit:execute-loop` for where these checks plug into the per-task loop (the push gate
and the task-completion gate); this skill is only about what makes a given check trustworthy.

- **"Non-trivial" heuristic** (governs whether a task needs an independent verifier): treat a
  task as non-trivial unless it's a pure config/copy/comment tweak with no logic or behavior
  change. When unsure, treat it as non-trivial — an extra verify pass is cheaper than a bad
  merge.
- Build agents must deliver **high test coverage**, not a happy-path smoke test.
- Anything with a browser-visible surface gets **live click-through verification in a real
  browser**: start the server, navigate, click, read the rendered page. Not `curl`, not reading
  the component source and asserting it's probably fine.
- **Before any user-facing demo/playtest link goes out**, a verifier must actually **play the
  flow end-to-end** (a full round, or a full journey to its completion signal) at the real URL.
  Connectivity and render checks pass even when the underlying content is wrong (wrong fixture,
  stale data, broken logic) — only actually exercising the flow catches that. If a flow can't be
  played end-to-end, say so explicitly instead of implying it was verified.
- **Permission-gated browser APIs** — push notifications via `Notification.requestPermission`,
  camera/mic, geolocation — auto-deny in automated browsers instead of showing a real dialog. A
  verifier must disclose that leg as unverifiable-by-automation and ask for a manual user check,
  not silently claim it passed because the auto-denied code path didn't error.
- **Deploy/infra verification includes confirming file modes survived** (e.g. executable bits on
  scripts — a `git checkout -f` can silently drop them), not just file content.
- **Local zero-new-failures authorizes the push; a confirmed-green CI run closes the task** (see
  `coordinator-kit:execute-loop`'s push gate and task-completion gate) — local-green does not
  mean CI-green, since CI runners can hit failures a targeted local suite never exercises. A
  failed Actions run means the task is NOT done; loop back into the retry cycle the same as any
  other verification failure. If the project has no CI pipeline yet, the local zero-new-failures
  report is the task-completion gate on its own.
- **Never blanket-suppress stderr on a diagnostic feeding a real conclusion.** A diagnostic or
  investigative command (a prod-DB check, a log query) whose result will inform a real
  conclusion must show its errors — `2>/dev/null` or equivalent swallows a real failure (e.g. a
  query against a nonexistent column) and produces a confident wrong answer instead of a visible
  one.
- **If the project has a monitoring/alerting/detector surface, backtest against real history —
  not synthetic fixtures.** Replay real data with the clock moved: output that changes only
  because time changed is broken regardless of thresholds. Never emit "resolved" merely because
  something aged out of a lookback window — name what improved. Confirm the backtest's own
  gating logic isn't narrower than it needs; grading itself blind is worse than none.
- **Browser viewport resizing can silently no-op.** A resize call can report success while
  changing nothing, so a responsive/mobile check can pass without ever landing at that viewport.
  Read the actual viewport width back from the page before trusting any responsive check.
- **A green test run can be silently skipping tests, not just passing them.** Config-gated tests
  (a gitignored config absent from a bare clone or fresh worktree, driving an assume/skip guard)
  skip rather than fail, and the run still reports success — distinct from the push gate's
  self-skip prohibition, which is deliberate (see `coordinator-kit:execute-loop`). Assert the
  skip count, not just pass/fail, so a suite that quietly stopped testing anything is visible.
- **A column rename or drop can break database-resident views invisibly.** Views live outside
  the repo, so nothing in a code diff or test run reveals the breakage — check any rename/drop
  against the database's own view definitions.
