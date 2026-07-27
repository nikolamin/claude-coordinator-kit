---
name: feedback-ci-push-discipline
description: "Never push speculatively 'to see if CI passes' - gate every push on zero new failures versus the base commit (full local suite, including DB-gated integration tests, no self-skip mode, rebased on main, failure sets diffed and the pre-existing set named), then check the real CI run after pushing instead of assuming local green means CI green."
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
  a real failure), and to report the actual results: **zero new failures versus the base commit**,
  diffing the failure sets and naming the pre-existing failure set in the report (on a fresh
  greenfield repo that pre-existing set is simply empty). That report satisfies one of the push
  gate's two conditions (`CLAUDE.md`'s Execute loop step 5) — the coordinator still needs the
  other: an independent verifier that passed, or an exemption under the Verification standard's
  non-trivial heuristic. Push once, deliberately, when both conditions are met — never push
  speculatively to find out.
- **After pushing:** the coordinator does not run `gh` itself either — it dispatches a small agent
  (the cheapest tier per `CLAUDE.md`'s Model routing for a plain pass/fail read, the build tier if
  the `--log-failed` output needs triage) to check the actual CI run (`gh run list` / `gh run view
  --log-failed`) and report back, rather than assuming local zero-new-failures implies CI green. A
  failed Actions run means the task is NOT done — the coordinator treats it as a normal
  verification failure and loops back into the build→verify→fix cycle, re-dispatching the build
  agent with the failure log — not letting it sit unnoticed because "local was clean." (If the
  project has no CI pipeline yet, the local zero-new-failures report is the task-completion gate on
  its own — see `CLAUDE.md`'s Execute loop step 5.)
- **In agent briefs:** subagents don't inherit this file. Any build-agent brief whose task feeds a
  commit/push must restate the push gate from `CLAUDE.md`'s Execute loop step 5 explicitly (rebase
  onto latest main, re-run the complete local suite on the rebased result including DB-gated
  integration tests, report zero new failures versus the base commit with the failure sets diffed)
  — a brief that omits it gets a speculative push, or a push gated on an untrustworthy claim
  instead of an actual report.
