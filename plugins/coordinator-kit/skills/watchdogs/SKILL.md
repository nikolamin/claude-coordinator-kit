---
name: watchdogs
description: Monitor in-flight coordinator work, distinguish slow agents from lost ones, recover interrupted trees, and restore inbox ownership after restart. Use on wakeups, missing completions, or suspected stalls; use bootstrap or stop-and-save for session handoff.
---

# Watchdogs and recovery

Every wakeup runs the [required coordinator cycle](../../references/proactive-cycle.md) to
actually ask pending questions and fill free lanes. Reading or reporting a sweep alone is not
an adequate wakeup result. Recheck immediately after each completion; do not wait for a timer.

Use the available harness's completion events plus **one combined watch** as the fallback, not
one monitor per topic re-armed on a timer. A benign event must not cost a coordinator turn: every
wake-up re-reads the whole coordinator context, and in a measured session over a thousand
wake-ups found nothing to do and made up 43% of coordinator cost. The bundled `scripts/watch.py --root WORKSPACE`, started once in
the background, stays silent while everything is in range and prints one line and exits on the
first actionable event: an active lane past its recorded `deadline`, idle work lanes with
free slots (`IDLE_LANES`, see [lane filling](../../references/lane-filling.md)), a failing
autolane hook, or a project check from `.coordinator/watch.json` (inbox pending, a resource
under its threshold). **An idle wake means dispatch each pick up to FREE-SLOTS or record that
lane's blocker (`coord.py idle block LANE --reason`); never re-arm the watch with neither.** Each check prints
only when action is needed; a check that keeps failing is reported as broken instead of looking
quiet. Record each in-flight agent's `deadline` on its lane so the watch covers it. After an
event, act, then restart the watch with a single tool call and no commentary. Verify once on your
host that a background command is not cut off by a time limit; if it is, pass `--max-seconds`
below that limit or run `--once` from the host's scheduler. Record the watch's actual id and scope
in the canonical state. A missing scheduler is a disclosed limitation, never a reason to claim a
wake-up is armed. Do not create duplicate monitors or revive a schedule the founder disabled.

## Sweep the recorded queue

On wake/resume, run the bundled `coord.py --root WORKSPACE sweep` alongside the normal state
read. It reports releases/user blockers without a linked question, an idle question slot with
queued work, outdated questions, and quiet in-progress/verifying tasks. It never sends, changes
status, dispatches or cancels. `--available-slots auto` derives FREE-SLOTS from recorded agent
lanes (the bundled autolane hook records every background dispatch with its agent id and
releases it on SubagentStop), the profile's `capacity.max_agents` and host memory, and offers
one ranked pick per idle work lane; use `--available-slots N` after a native fleet check when
the records cannot see the fleet. Candidates still require scoped authorization and
lane/resource checks.
`check_capacity` requires that live check, `prepare_task` requires intake, and
`review_dispatch_scope` requires checking a hold against the named task rather than freezing
unaffected work. Finish the cycle with `--check-idle`; exit 2 means outstanding action/blocker
accounting, not permission to go silently idle.
Unknown capacity is not zero agents, and missing recent DB notes is not proof an agent died.
`queue_conflict` and `clear_closed_queue` expose stale ordering; correct canonical records
after checking their intent. Conflicting positions withhold those tasks from dispatch candidates
until reconciled; unrelated eligible work can proceed. `review_lane` flags running work without a lane or active lanes
whose task is missing/closed. Inspect native ownership and remaining processes before repairing
records; do not launch a replacement or release a checkout merely to make the sweep green.

Reconcile each item with current evidence. Promptly queue/present a legitimate release decision
while keeping one presented question; exclude user-initiated actions. Resolve migration reviews
and applicable holds before dispatch. Update task records for stale premises rather than hiding
the symptom in a report. `--stale-hours` changes only the liveness-review threshold; it is not a
kill timeout. Keep unchanged sweep results internal under the notification policy.

## Check evidence before replacing an agent

1. Read the native agent status and most recent meaningful output/checkpoint. Compare with its
   current operation, not a sibling's activity rate. An estimate expiring, a stale output stub,
   or a quiet scratch directory alone does not establish a stall. Account for machine sleep.
2. If needed, use a supported status-only probe: "status only; do not restart completed work."
   Some messaging tools restart completed agents, so check status first and prefer a read-only
   status API. A live long build/emulator/CI wait can explain silence: extend the estimate.
3. Repeated identical errors, a confirmed exit/lost agent, or a genuinely blocked process can
   justify recovery. If process inspection is needed, dispatch a small diagnostic agent;
   the coordinator still does not run product diagnostics itself.
4. Before killing or duplicating work, inspect the last output for a recent push, ongoing suite,
   or CI wait. Retain the lane until ownership is settled. Cancellation required by an explicit
   stop or an active harmful side effect takes precedence; record why it was necessary.

## Recover the work on disk

Stopping, rate limiting, or losing an agent does not roll back its files or stop its children.
Have a recovery agent snapshot the diff/untracked work before changing anything, inspect actual
branch/remote commits and process ownership, and reconcile its report with canonical task state.
Local HEAD alone can be stale while another worktree already pushed. Do not assert "tree
untouched" from a failure notification or immediately redispatch an identical writer.

For an interrupted mutation verifier, inspect its `mutation-in-flight` marker, backups and
intended patch. Classify every changed production hunk as intended work, applied mutant, or
unknown; preserve unknowns and resolve them before further builds. Never bless a dirty tree
with "keep if legitimate," or blindly restore HEAD over another agent's work. Clean up only
owned processes/resources and verify cleanup, then hand off the remaining work to a fresh agent.

Recovery is routine within the existing task authorization. A dispatch suspension also blocks
new recovery/investigation agents unless the founder's stop instruction authorizes that cleanup;
record unresolved leftovers and report instead. A restart never implicitly lifts a hold.

## Session and inbox ownership

On resume, audit existing agents and durable receivers before re-arming session-local monitors.
Session-local ids are stale after restart; durable receivers may still be alive. Record new ids
only after confirming they exist. Each inbox has one receiver owner; do not start a second
consumer of a single-consumer API such as Telegram getUpdates. Different coordinator runtimes
must hand off ownership, not each assume the other died.

Every few idle checks, compare the inbox's last delivered event/cursor against the last event
actually processed. A healthy producer proves delivery to the inbox, not to this session.
On a mismatch, restore the listener and process missed messages once using stable message ids.
Check local-only permission prompts when there is unexplained silence; use approved scratch
paths so an unseen allow-click does not masquerade as an agent stall.
For durable inboxes, read the full referenced payload when a preview is truncated. Preserve
sender, source time, reply/forward provenance and stable update ids; quoted or forwarded content
does not become fresh user authority. Persist the response/action receipt in canonical state
before acknowledging delivery. Receipt can be at-least-once even with a healthy receiver:
reconcile a crash between external action and acknowledgment before retrying the action.

For a dated obligation that must survive session exit, use a supported durable scheduler with
an owner, exact timestamp/timezone, completion evidence, and failure notification. An in-session
watchdog is not that guarantee. Do not schedule production actions beyond their authorization;
if no durable mechanism is available, surface the unresolved obligation before the session ends.

When work drains, use only the profile's authorized fallback activities. If only founder input
remains, retain the single question and a supported listener/wake-up; do not repeatedly ping
unchanged status. Apply `coordinator-kit:comms-register`'s notification policy.

For an enabled [Telegram idle-status updater](../../references/telegram-status.md), check the
sender's reported action and canonical preview separately from inbox health. Unknown send
outcomes or undeletable posts require observed reconciliation, not a second publisher. A running
sender loop proves neither receiver delivery nor native agent liveness. Keep exchange hooks
active for accepted inbound messages and confirmed outbound sends; stop/restart only its owner.
