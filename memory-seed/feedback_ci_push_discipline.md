---
name: feedback-ci-push-discipline
description: "Never push speculatively 'to see if CI passes' - gate every push on a fully green local suite (including DB-gated integration tests, no self-skip mode) and a rebase on main, then check the real CI run after pushing instead of assuming local green means CI green."
metadata:
  type: feedback
---

Push discipline has two halves, and both have burned real projects: what must be true *before* a
push, and what must be checked *after* one.

**Why:** two real incidents. In one project, speculative pushes and push-then-hotfix churn burned
through the GitHub Actions budget badly enough to trigger a billing freeze — pushing to "see if it
passes" instead of verifying locally first turns CI into an expensive guess-and-check loop. In
another, a task was marked done off a green *targeted* local suite, but the actual failure was
CI-runner-only (an environment difference the local run never exercised) — nobody checked the real
Actions run, so a broken build shipped as "verified."

**How to apply — mind who does which step; the coordinator itself never rebases, runs tests, or
runs `gh`:**
- **Before pushing:** the coordinator does not rebase or run the suite itself (that's
  investigative/verification work the Role section reserves for a dispatched agent). The build
  agent's own brief requires it to rebase its work onto latest main, then re-run the full local
  build+test suite on the rebased result — not a narrowed/targeted subset — including any
  DB-gated integration tests against a real local database (no self-skip or mocked-DB mode masking
  a real failure), and to report the actual results; the coordinator gates the commit/push on that
  report. Push once, deliberately, when the reported results already say it should pass — never
  push speculatively to find out.
- **After pushing:** the coordinator does not run `gh` itself either — it dispatches a small agent
  (`model: haiku` for a plain pass/fail read, `sonnet` if the `--log-failed` output needs triage)
  to check the actual CI run (`gh run list` / `gh run view --log-failed`) and report back, rather
  than assuming local green implies CI green. A failed Actions run means the task is NOT done —
  the coordinator treats it as a normal verification failure and loops back into the build→verify→
  fix cycle, re-dispatching the build agent with the failure log — not letting it sit unnoticed
  because "local was green."
- **In agent briefs:** subagents don't inherit this file. Any build-agent brief whose task feeds a
  commit/push must restate the before-push gate explicitly (rebase onto latest main, re-run the
  complete local suite on the rebased result including DB-gated integration tests, report the real
  results) — a brief that omits it gets a speculative push, or a push gated on an untrustworthy
  claim instead of an actual report.
