---
name: watchdogs
description: Monitor in-flight coordinator work, distinguish slow agents from lost ones, recover interrupted trees, and restore inbox ownership after restart. Use on wakeups, missing completions, or suspected stalls; use bootstrap or stop-and-save for session handoff.
---

# Watchdogs and recovery

Use the available harness's completion events plus an authorized fallback wake-up for in-flight
work (typically 20–30 minutes). Record its actual id and scope in the canonical state. A missing
scheduler is a disclosed limitation, never a reason to claim a wake-up is armed. Do not create
duplicate monitors or revive a schedule the founder disabled.

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

For a dated obligation that must survive session exit, use a supported durable scheduler with
an owner, exact timestamp/timezone, completion evidence, and failure notification. An in-session
watchdog is not that guarantee. Do not schedule production actions beyond their authorization;
if no durable mechanism is available, surface the unresolved obligation before the session ends.

When work drains, use only the profile's authorized fallback activities. If only founder input
remains, retain the single question and a supported listener/wake-up; do not repeatedly ping
unchanged status. Apply `coordinator-kit:comms-register`'s notification policy.
