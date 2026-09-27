---
name: execute-loop
description: Run the coordinator's task loop, assign exclusive work lanes, bound retries, and gate pushes and completion on revision-specific evidence. Use when dispatching work, deciding what can run concurrently, or checking whether a task can ship. For how to prove behavior, use verification-standard.
---

# Execute loop

Follow the [required coordinator cycle](../../references/proactive-cycle.md) after every request,
answer, agent result and wakeup, and before waiting. Pending questions must actually be asked;
available capacity must take authorized work. A status report is not completion of this cycle.

Apply the [runtime adapter](../../references/runtime.md) for native delegation, model settings,
instruction files and missing capabilities. Never assume a Claude-specific tool exists in Codex.

The coordinator delegates implementation, investigation, and verification. Run database ensure,
finish pending migration reconciliation, then read the profile and current task records (`coordinator-kit:coordination-state`); project topology,
authorization, and model choices override defaults. A repository push may itself deploy or
publish: use the recorded trigger map, never infer permission from a branch or host name.

## Dispatch and delivery

1. Select an authorized, unblocked task by recorded queue order, priority and dependencies.
   Define and queue new requests through `coordinator-kit:backlog-discipline`; do not preempt
   active work without an explicit reprioritization or applicable incident policy. Preserve the founder's
   original request alongside acceptance criteria. Before implementing an old ticket, have the
   agent cheaply test its premise: already fixed, wrong cause, and not reproducible are useful
   findings, not invitations to invent a change. Correct stale records at their source.
2. Claim a lane before dispatch. Record task/agent id, repository and checkout, branch, owned
   paths, external resources, stage, model, start time, expected duration, and report path.
   Give the agent a bounded brief using `coordinator-kit:agent-brief-hygiene`.
3. Builder implements and runs affected checks locally. For non-trivial work, dispatch a fresh
   independent adversarial verifier; pure copy/comment/config changes with no behavior change
   may be exempt. Policy, authorization, routing, or deploy configuration changes are behavioral.
   Include one structural check suited to the acceptance criteria, such as a generated-case
   sweep, property invariant or controlled mutation. Repeated handpicked cases do not replace
   coverage of the failure mechanism; failures follow the same bounded retry/escalation loop.
4. A failed verification gets a fresh fixer with the exact gap and on-disk evidence. Allow at
   most two fix/re-verify cycles on the same gap after the initial failure; if the second cycle
   also fails (third failure overall), escalate via `coordinator-kit:escalation`. A new agent
   does not reset the counter. Do not resume a large completed transcript merely to continue
   work; a status-only probe to a still-running agent is different.
5. Establish the push gate below, then commit/push only what the project's authorization permits.
   An assigned agent may snapshot its own work before verification when local commits are
   authorized; otherwise preserve a patch. This does not expand the coordinator's product-commit
   exception, authorize a push, or allow sweeping another agent's changes into the snapshot.
6. Check the actual post-push outcome. Record built, verified, pushed, on-test, on-prod, and
   awaiting-user-validation separately; a server half without its required client is not a
   completed user goal. Dispatch a deployed-flow check when the criteria require one.
   When release approval is the only remaining step, set `awaiting_release` with target/evidence
   and queue its linked decision immediately. For user-initiated next actions, keep the current
   state plus that flag and await the user's initiation without proposing a release question.
7. Persist the result, release the lane when no writer/test/mutation process still owns it, and
   immediately run the required cycle: present the next question and dispatch the next authorized
   unblocked task independently. Do not ask whether to continue approved work or wait for all lanes.

## Lanes and shared resources

- **One writing/committing agent per shared checkout**, including fixers and mutation verifiers.
  A read-only verifier also needs a stable snapshot; do not certify a tree another agent edits.
  Disjoint filenames alone do not make tests, the index, or a dev server independent.
- Parallelize across independent repositories or isolated worktrees when the recorded branching
  convention permits them. Trunk-based projects can use serialized lanes without worktrees.
  Branch names and merge authority are project choices, not plugin defaults to impose.
- Worktrees still share external services and the Git stash stack. Allocate task-owned database
  schemas/instances, ports, build outputs, and browser sessions or serialize those users. Check
  ownership before starting and before cleaning up. Never kill a shared database or another
  developer's server, run broad daemon-stop commands, or use `git stash` as cross-agent isolation.
- Before a local app starts, identify outbound effects. Production-restored data can cause real
  email/SMS/webhook sends even on localhost; disable outbound delivery or use an isolated sink.
- A crash does not release a lane by itself. Inspect and preserve the remaining tree/processes
  first, including mutation markers (`coordinator-kit:watchdogs`).

## Test evidence: once per revision and environment

Avoid multiplying full suites by the number of agents. Builders and fixers run affected checks;
the full candidate suite runs at the push gate, and verifiers reuse valid suite evidence while
independently testing the acceptance criteria.

- Cache baseline results under `.coordinator-scratch/base-failures/<full-sha>/` with a manifest:
  repository, full revision, clean-tree/diff identity, commands, toolchain, dependency/config
  fingerprint (no secrets), database/schema setup, timestamp, exit codes, pass/fail/skip counts,
  named failure set, and log paths. A file merely existing is not a valid cache hit.
- Reuse only when that identity and required coverage match. Missing logs, changed fixtures,
  toolchains, config, schema, or source invalidate the affected evidence. Shared-tree edits
  during a run make attribution unresolved. Keep baseline failures distinct from candidate ones.
- After a fix, rerun affected checks. Before push, the full required suite, build, lint and
  typecheck must cover the final candidate. Use real local dependencies for required integration
  tests; no mocked/self-skip substitutes. Compare failure sets, not just totals, and report skips.
- Any source change after verification requires review of the changed scope. Reuse across a
  rebase only when an agent documents why the tested tree/dependencies are unchanged or the
  upstream changes cannot affect the covered behavior, with relevant checks on the new revision.
  If impact is uncertain, rerun; a vague "unrelated rebase" is not evidence.

## Push gate and completion gate

Push requires both **zero new failures versus the identified base** for the final candidate and
an **independent acceptance pass** (or documented non-behavioral exemption). Required live UI
verification that is blocked remains blocked: disclosure is not a substitute. Finish every
authorized preparatory step before presenting a concrete remaining approval/unblock request.

In a shared tree, check `git status` and the index before committing; stage/commit intended paths
only, never sweep another agent's staged files. Before pushing, inspect
`git log origin/<branch>..` and ensure every outgoing commit is reviewed and authorized. Never
reset, clean, discard, or force-push to get past a conflict or rejected push; dispatch recovery.

When CI exists, an agent checks required runs for the **full 40-character pushed SHA**, not
"latest run" or a possibly stale branch filter. Empty, pending, skipped-required, or missing
runs are unresolved; green deploy-only CI does not prove local tests ran. Failed required CI
returns to the fix loop. If verified topology establishes there is no CI, use the local gate
and any required deployed check; CI setup is a separate task. Recheck topology when it changes.

Keep release/go-live authority separate from verification. A tag, release branch, package
publish, or merge can have production effects; local green and test deployment never grant
permission for those effects. Report completion at the goal's agreed environment and scope.

## Holds and autonomous scope

Recover lost/failed agents without re-asking for already-authorized work, after checking liveness
and leftovers. Honor explicit holds across sessions. Record the founder's exact instruction,
scope and source; when lifted, mark the original hold superseded with the lift's source too.
"Resume this task" need not lift unrelated holds or authorize a new backlog. A status question
is not a lift. Stop only dependent work for a user-only action, unresolved material choice,
actual access/infra blocker, or applicable suspension; continue independent authorized lanes.
If the approved queue is empty, use only a recorded, authorized fallback activity or stay idle.
Report according to `coordinator-kit:comms-register`, not on every loop iteration.
