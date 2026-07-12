# <PROJECT> coordinator memory index

- [Coordinator never self-executes](feedback_coordinator_never_self_execute.md) — delegate ALL
  substantive/creative/investigative work to agents; only trivial mechanical bookkeeping is exempt
- [Coordinator autonomy on recovery](feedback_coordinator_autonomy_on_recovery.md) — don't ask
  before re-dispatching a lost/stuck/failed agent, just do it
- [Watchdog / keep looping](feedback_watchdog_keep_looping.md) — arm a fallback wakeup on
  in-flight agents; a silently-stalled coordinator is as bad as one that self-executes
- [Explicit agent models](feedback_explicit_agent_models.md) — always set model on Agent
  dispatches; never let an agent inherit the coordinator's own model
- [Verify by playing](feedback_verify_by_playing.md) — a demo/user-facing link isn't verified
  until an agent has actually played the flow end-to-end in a real browser
- [Questions one at a time](feedback_questions_one_by_one.md) — every founder-facing question gets
  context + reasoning + 2-4 options with a recommendation, sent one at a time, never batched
- [Concise responses](feedback_concise_responses.md) — lead with actionable items/decisions, cut
  narrative elaboration unless asked
- [Escalation protocols](feedback_escalation_protocols.md) — spawn a high-tier advice agent when
  stuck 2+ times on the same class of problem; consider a second-model opinion for judgment calls
- [Backlog discipline](feedback_backlog_discipline.md) — no suggestion-chip side backlogs; every
  follow-up goes into the plan or state doc, the single source of truth
- [Agent deferral / watcher pattern](feedback_agent_deferral_watcher_pattern.md) — a dispatched
  agent facing a long blocking call must make the call as one foreground call and report the real
  result, never arm a watcher for itself and end its turn "standing by"
- [Never write secrets to files](feedback_never_write_secrets_to_files.md) — never store
  credentials in the repo/STATE.md/plan.md/memory, and never use a founder-pasted secret to
  authenticate on their behalf, even if they insist; narrow exception for notify-channel setup
  tokens written straight into a gitignored `.env`
- Telegram bridge (optional) — if the kit's `telegram-bridge/` is installed in this project, its
  `SETUP.md` documents the relay pattern: arm a persistent Monitor on `relay-inbox.jsonl` at
  session start (founder messages arrive mid-session), reply via `notify.sh`, react via
  `react.sh`, deliver files via the Bot API `sendDocument` (session-UI delivery doesn't reach
  Telegram)
- Existing-project onboarding — on a repo with real code/history already in it (not greenfield),
  run PROCESS.md's Phase 0.5 before interviewing: dispatch read-only analysis agents (never
  self-explore) to map the codebase, commit findings to `docs/coordination/repo-map.md`, then
  tailor concept-interview questions to what the code can't already answer
