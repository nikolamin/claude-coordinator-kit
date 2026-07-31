---
description: The coordinator's per-task build/verify/commit/dispatch loop — spawning a build
  agent then an independent verifier, the 2-cycle retry cap before escalating, updating
  STATE.md, the push gate's two conditions (zero-new-failures rebase report plus a verifier
  pass or exemption), the post-push CI task-completion gate and its no-CI fallback, and
  immediately dispatching the next unblocked task from docs/plan.md — including parallel
  dispatch defaults and the shared-resource collisions (a test database, a fixed listen port,
  a login-gated browser session) that make tasks non-disjoint even across separate worktrees.
  Load this when pulling the next task from docs/plan.md, deciding whether a task has cleared
  enough to commit and push, checking whether CI actually passed, deciding whether several
  unblocked tasks can run in parallel or must serialize, or recognizing a founder instruction
  that suspends autonomous dispatch ("don't start anything new until I tell you what to do").
  Not for the phase-level loop itself (Bootstrap through Iterate — see
  coordinator-kit:phase-loop), and not for what makes a verifier's pass/fail judgment correct
  once dispatched (see coordinator-kit:verification-standard).
---

# Execute loop

This skill packages `CLAUDE.md`'s Execute loop section for delivery via a plugin. If this
project's coordinator uses the file-copy install, the project-root `CLAUDE.md` already carries
this exact content under its own "Execute loop" heading — this skill is a second, parallel
delivery path for the same rules, not a replacement. See `CLAUDE.md`'s Role section for the
standing boundary this loop runs inside: the coordinator dispatches every build, verify, and
investigative step via the `Agent` tool and never performs one itself, including the rebase and
test run that back the push gate below. See `CLAUDE.md`'s Model routing section for which tier
("build" vs "verifier" vs "cheapest") each dispatch below uses — every `Agent` call sets `model`
explicitly, never inheriting the coordinator's own tier.

## Per task pulled from `docs/plan.md`

1. Spawn a build agent (the build tier per `CLAUDE.md`'s Model routing) with a self-contained
   prompt carrying acceptance criteria plus the required verification step — see
   `coordinator-kit:verification-standard` for what that step actually needs to establish.
2. Spawn an independent verifier agent (the verifier tier) for any non-trivial task — adversarial,
   not a rubber stamp. It re-derives and re-checks the acceptance criteria; it does not just
   re-read the build agent's own claims.
3. If verification fails: re-prompt or respawn the build agent with the specific gap. Repeat
   until acceptance criteria are actually met — but cap it at **2 failed re-prompt/respawn cycles
   on the same gap**. On the 3rd failure on that same gap, stop retrying and escalate instead of
   continuing to loop (see `coordinator-kit:escalation`).
4. Update `docs/coordination/STATE.md` (build → verify → fix → re-verify, commit hashes,
   disclosed caveats).
5. Commit and push once two conditions both hold — this is the **push gate**:
   — The build agent's own report establishes **zero new failures versus the base commit** on
     rebased work. Its brief requires it to rebase its work onto latest main, re-run the complete
     suite on the rebased result (including any DB-gated integration tests against a real local
     database, no self-skip/mocked mode), and report the actual results: zero new failures versus
     the base commit, diffing the failure sets and naming the pre-existing failure set in the
     report (on a fresh greenfield repo that pre-existing set is simply empty).
   — An independent verifier has passed the acceptance criteria, or the task was exempt under
     `coordinator-kit:verification-standard`'s non-trivial heuristic (a pure config/copy/comment
     tweak with no logic or behavior change; when unsure, treat it as non-trivial).

   The coordinator gates the commit/push on those two reports and never rebases or runs the suite
   itself (see `CLAUDE.md`'s Role section). Push once, deliberately — never push speculatively "to
   see if CI passes." The coordinator's own commit/push is covered by `CLAUDE.md`'s Role-section
   bookkeeping exception, which extends to two read-only safety checks immediately around it and
   nothing more: in a shared (non-worktree) checkout, run `git status` before committing and
   commit only the intended paths — a broad `git add <file> && git commit` in a shared tree can
   sweep in a concurrent agent's staged-but-uncommitted files under an unrelated commit message —
   and before pushing, check what is actually ahead of origin (`git log origin/<branch>..`) and
   push only the reviewed/verified commit(s), since a push meant to land one reviewed commit can
   also carry a second agent's in-flight unreviewed commit along with it. Never run destructive
   git operations (`checkout --`, `reset`, `clean`) on a tree that may hold another agent's
   uncommitted work.

   **Task-completion gate (necessarily after push, not before):** if the project has a CI
   pipeline — established via `STATE.md`/the repo map or a dispatched agent's report, never the
   coordinator's own guess — dispatch a small agent (cheapest tier for a plain pass/fail read,
   build tier if `--log-failed` needs triage) to check the actual CI run (`gh run list` /
   `gh run view --log-failed`) and report back; the coordinator never runs `gh` itself, same
   investigative-Bash prohibition as above. A confirmed-green run closes the task; a failed run
   means NOT done: loop back into step 3 with the failure log. If there's no CI pipeline yet
   (e.g. still at Bootstrap), the push gate's local zero-new-failures report is the
   task-completion gate on its own — don't invent a CI check that doesn't exist — and standing up
   CI becomes its own task in `docs/plan.md`, not a blocker on every other task.
6. Immediately dispatch the next unblocked task from `docs/plan.md`'s dependency graph —
   **without asking**. The plan already answers "what's next"; asking again is noise. If
   multiple tasks are unblocked, pick by the plan's stated priority/dependency order yourself —
   don't ask the founder to choose between viable options ("preference, or should I pick?" is the
   same anti-pattern as "should I continue?"). When several unblocked tasks don't touch the same
   files, dispatch them in parallel by default rather than serializing one at a time.

   This worktree-per-task default assumes a project where isolating each task in its own branch
   is safe; a trunk-based or continuous-deploy project (where a push to the trunk branch is
   itself the deploy trigger) may need the opposite convention entirely — don't assume the
   default applies. Confirm which this project is and record it as a durable decision in
   `STATE.md`.

   Worktrees isolate the file tree only — they do not isolate a shared external service (a test
   database, a fixed listen port, a shared schema). If the colliding tasks would also share one
   of those, either fall back to sequential dispatch for just those tasks, or give each agent a
   private instance: put it in each parallel build agent's own brief to claim its own
   port/datadir (e.g. check `lsof -nP -iTCP:<port> -sTCP:LISTEN` before claiming one) and
   drop+recreate its own schema so migrations start clean — the coordinator doesn't provision
   this itself, it's a requirement placed on each build agent's brief. A shared-service collision
   shows up as a flaky test failure or a bogus assertion mismatch, not an obvious merge conflict,
   so it's easy to misdiagnose as a real bug. One browser holds one session per site, so
   login-gated persona/browser tests are the same shared-resource collision class applied to a
   browser session instead of a service — run them sequentially too, never in parallel.

## Re-dispatch is routine, not a decision

**Never ask permission to re-dispatch a lost, stuck, or failed agent.** Retrying a transient
failure, re-prompting after a bad result, or recovering a dropped task ID is routine coordination
mechanics, not a decision — unless a recorded suspension of autonomous dispatch is in force (see
below), in which case report the failure/stall in STATE.md and to the founder instead (see also
`coordinator-kit:watchdogs` for the stall-detection side of this same rule).

## Suspension of autonomous dispatch

**A founder instruction can suspend autonomous dispatch.** Step 6's "immediately dispatch,
without asking" is the default, not an absolute — a founder instruction can impose a standing
gate on new dispatch (e.g. "don't start anything new until I tell you what to do"). When it does:
record it verbatim in `docs/coordination/STATE.md`'s Durable decisions, and honor it until the
founder explicitly lifts it. A status question, an ambiguous query, or "do you have work?" is
never such a lift — only an unambiguous instruction naming what to resume is. While suspended,
status reporting, the question queue, and scheduled/checkpoint reports continue exactly as
before; only new agent/build/investigation dispatch stops. See `coordinator-kit:watchdogs` for
how this interacts with cross-session recovery.

## Stop conditions

**Only stop the loop for:**
- A genuine user-only action (live demo/playthrough, a public go-live).
- A real fork in the road with no obviously-correct default.
- Being actually blocked (missing access, failing infra only the user can unblock).
- A recorded suspension of autonomous dispatch (above) still in force.

Everything else: keep looping, report at checkpoints (see `CLAUDE.md`'s Comms register section),
don't pause and wait.
