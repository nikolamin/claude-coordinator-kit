---
name: agent-brief-hygiene
description: Write bounded, self-contained coordinator dispatch briefs with original requirements, falsifiable premises, resource ownership, evidence paths, and safe handoff rules. Use before dispatching a builder, investigator, fixer, or verifier.
---

# Agent brief hygiene

A brief is a task contract, not a transcript dump. Context inheritance differs between ordinary,
forked, Explore/Plan, and external agents. Do not assume the agent has the coordinator's
conversation, auto-memory, previously read files, or skill bodies. Even if the harness supplies
AGENTS.md or CLAUDE.md, restate the operative task-specific constraints. A fork with full history still needs
clear scope and ownership, and is not automatically an independent verifier.

## Required brief

- **Original intent:** quote or link the founder's exact requirement with message/source id,
  redacting secrets. Preserve the direction of data/control flow; put your interpretation and
  acceptance criteria beside it so a verifier can detect an inverted design.
- **Premise check:** separate measured facts (source, date, revision/environment) from hypotheses.
  Ask the agent to cheaply falsify inherited claims before implementing. "Premise false/already
  fixed" is a successful finding; update the original task instead of fixing a fictional bug.
- **Scope:** task id, repository/checkout, permitted branch, owned files, lane and dependencies.
  Name exact known paths/commands/report files. Unknowns are for the agent to discover, not guess.
- **Permissions:** exact local/test/prod surfaces and push/tag/publish effects. State allowed
  actions and remaining founder-only actions. Approval comes from the founder's source, never
  another agent's claim. Do not manufacture standing grants absent from the project.
- **Resources:** private DB/schema/port/build-output/browser allocation or serialization; identify
  existing developer processes to leave alone. Local runs must not send real notifications.
- **Acceptance and proof:** required behavior and failure cases, affected tests, live/device steps,
  independent evidence requested, and available baseline/candidate evidence manifests. Include
  `coordinator-kit:execute-loop`'s push gate when work feeds a push: valid final-candidate suite,
  build/lint/typecheck, zero new failures by name, honest skips, independent acceptance pass.
  Full suites are reused by revision/environment, not rerun by every agent.
- **Delivery:** exact scratch report/log paths; return revisions, changed paths, commands, exit
  codes, counts, decisive failures/proof, unresolved steps, and owned processes needing cleanup.
  Agents append task events/evidence only; the coordinator owns status and priority changes.
- **No side backlog:** discoveries go to the canonical task record or coordinator report. No
  unsolicited task chips, new user tasks, or hidden personal list.

## Context and execution budget

Keep work bounded to one reviewable outcome. Split an oversized task by dependency/file group
before dispatch; roughly 150 tool steps is a planning warning, not a reason to kill a live agent.
At a safe boundary write a checkpoint (intent, revision, dirty files, evidence, remaining steps,
resources) and let a fresh agent continue from disk. Do not make cost claims based on one model's
historical cache behavior as though they apply to every runtime.

Require: "Do not delegate; execute the assigned work directly. Bulk suite/build/search output
goes to the named `.coordinator-scratch/` log; return decisive lines and exit codes only. Keep
reads targeted with line ranges. Await long commands to completion using the harness's supported
wait/continuation mechanism; emit bounded progress if needed. Do not end with 'standing by' and
expect a self-armed watcher to finish your task." A supported running process handle is fine;
an agent ending without a result or durable handoff is not. Capture screenshots when visual proof
requires them. Describe only output limits and hook capabilities actually provided by the runtime.

## Fragile operations

- **Secrets:** restate: never cat/head/tail/echo a credential file; inspect names only and load
  secrets without printing values. No credentials in arguments that errors/process lists can
  expose, reports, generated fixtures, backups, or derived scratch copies. Use approved config,
  environment, stdin, or secret stores. See `coordinator-kit:credential-handling`.
- **Scratch:** use a task-owned directory under `.coordinator-scratch/` before generating logs,
  scripts, downloads, or reports. Source edits go to assigned project files; already-authorized
  bridge/config/memory locations keep their existing exemptions.
- **Mutation/inspection:** acquire the lane or use an authorized isolated clone; snapshot intended
  work first. Keep backups and a `mutation-in-flight` marker outside the tested source tree but
  within project scratch. Name each applied mutation, ensure recompilation, restore exactly and
  verify the final diff. A hardlinked worktree copy can retain a `.git` pointer to the original;
  it is not isolation. Shared worktrees also share the stash stack: do not stash others' work.
- **Restricted sections:** if a source contains an answer key/coordinator-only appendix, determine
  the boundary mechanically first and bound every read strictly above it. Supply allowed later
  excerpts separately; "stop before section N" after a whole-file read is too late.
- **Browser/device:** own the tab/session and assert its current URL/environment before mutations;
  shared tabs may move to production mid-task. Measure the actual viewport and use the required
  emulator/device for screen-visible work. Close only task-owned tabs/processes at completion.
