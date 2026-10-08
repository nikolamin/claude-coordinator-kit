# Verification by risk

Choose the gate before dispatch, from the original requirement, changed behavior and target
environment. Record `verification_mode`, `risk_reason`, required checks and evidence on the task;
include them in the brief. A project's sourced verification policy overrides these defaults.
Do not overwrite existing grants, stricter acceptance criteria or a pending exception on upgrade.

## Routine work

For ordinary UI, copy, local tooling and non-sensitive application behavior, use
`verification_mode: routine`. The builder checks the requested outcome, runs affected tests
while iterating, then runs the required final-candidate suite/build/lint/typecheck once before
an authorized push to the agreed test environment. The same agent can check that revision's CI.
Do not add a separate verifier, mutation campaign or repeated full-suite cycle simply because
the change is behavioral. A small fix needs the affected checks again, not a new review ceremony;
reuse other evidence only under execute-loop's revision/environment rules.

Required acceptance evidence still applies. A UI task needs a relevant rendered interaction;
the builder can supply it. Do not silently replace a specifically required device, live journey
or integration check with unit tests. If the project explicitly uses tester acceptance on TEST,
record that leg as pending and report the test deployment without claiming final acceptance.

## High-risk work

Use `verification_mode: high_risk` for money/fiscal behavior, production database writes,
production releases, security/authorization boundaries or other material irreversible effects.
Classify by the effect, not the file type: a UI permission change or deploy config can be high
risk. Resolve unclear impact before treating it as routine; keep a conservative gate while
material uncertainty remains.

A fresh independent verifier checks the original acceptance criteria against the actual
candidate. Use a structural check suited to the failure mechanism (generated cases, a property
invariant or controlled mutation); a safety assertion needs a negative control. Reuse valid
full-suite results and spend verification effort on behavior and uncovered boundaries. Mutating
checks need exclusive resources and exact restoration. Apply the bounded failure/escalation
loop; changing agents does not reset its counter. Evidence never grants release authority.

## Urgent revert on TEST

When the user or an established incident policy authorizes restoring a broken test environment
to a measured known-good revision, `verification_mode: urgent_test_revert` permits a narrow
restore gate: inspect the exact revert range and compatibility, run the affected regression and
required fast build/type checks, then commit/push within the existing test-release grant. Check
the pushed revision's CI and the restored behavior promptly. Record deferred full-suite work
with an owner and next trigger and run it after the push; do not call all checks complete early.

This path is for an exact restoration, not a speculative fix or bundled feature. Do not use it
for a production release, destructive schema/data rollback, changed money/security behavior,
or an unknown/incompatible baseline. Those cases retain their risk gate and approval scope.
Repository-required CI/branch protections still apply. Do not turn a time estimate into a
timeout that kills a live restore job.

## Release scope

Before asking to release, establish the actual deployed baseline for the destination and
enumerate the full candidate range from that baseline, including inherited commits/artifacts.
The test branch's push range is not the production release range. Record the baseline, candidate,
evidence and release contents before describing them as complete. If the range includes work
outside the existing grant, prepare and disclose the concrete expanded scope before release.
Recheck if the baseline or candidate moves; approval of one feature does not approve unnamed
ancestors. Use known artifact identities when a deployment does not map directly to a Git tag.
