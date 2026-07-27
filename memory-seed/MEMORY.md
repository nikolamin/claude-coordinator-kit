# <PROJECT> coordinator memory index

- [Coordinator never self-executes](feedback_coordinator_never_self_execute.md) — delegate ALL
  substantive/creative/investigative work to agents; only trivial mechanical bookkeeping is exempt
- [Coordinator autonomy on recovery](feedback_coordinator_autonomy_on_recovery.md) — don't ask
  before re-dispatching a lost/stuck/failed agent, just do it — unless a recorded suspension of
  autonomous dispatch is in force, in which case report status and don't re-dispatch
- [Watchdog / keep looping](feedback_watchdog_keep_looping.md) — arm a fallback wakeup on
  in-flight agents; a silently-stalled coordinator is as bad as one that self-executes
- [Explicit agent models](feedback_explicit_agent_models.md) — always set model on Agent
  dispatches; never let an agent inherit the coordinator's own model
- [Verify by playing](feedback_verify_by_playing.md) — a demo/user-facing link isn't verified
  until an agent has actually played the flow end-to-end in a real browser
- [Questions one at a time](feedback_questions_one_by_one.md) — every founder-facing question gets
  context + reasoning + 2-4 options with a recommendation + a safe default if unanswered, sent one
  at a time, never batched
- [Concise responses](feedback_concise_responses.md) — lead with actionable items/decisions, cut
  narrative elaboration unless asked
- [Escalation protocols](feedback_escalation_protocols.md) — spawn a high-tier advice agent once
  the Execute loop's retry cap is hit (2 failed re-prompt/respawn cycles on the same gap, escalate
  on the 3rd); consider a second-model opinion for judgment calls
- [Backlog discipline](feedback_backlog_discipline.md) — no suggestion-chip side backlogs; every
  follow-up goes into the plan or state doc, the single source of truth
- [Agent deferral / watcher pattern](feedback_agent_deferral_watcher_pattern.md) — a dispatched
  agent facing a long blocking call must make the call as one foreground call and report the real
  result, never arm a watcher for itself and end its turn "standing by"
- Telegram bridge (optional) — if the kit's `telegram-bridge/` is installed (typically outside this
  project, at `<BRIDGE_DIR>`, as a machine-level service — see README), its `SETUP.md` documents
  the relay pattern: arm a persistent Monitor on `<BRIDGE_DIR>/relay-inbox.jsonl` at session start
  (founder messages arrive mid-session), reply via `<BRIDGE_DIR>/notify.sh`, react via
  `<BRIDGE_DIR>/react.sh`, signal "still working" via `<BRIDGE_DIR>/typing.sh [seconds]` while a
  reply is being composed, and deliver files via `<BRIDGE_DIR>/send-file.sh <path> [caption]` —
  never hand-roll a `curl` against the Bot API (session-UI delivery doesn't reach Telegram on its
  own either)
- Existing-project onboarding — on a repo with real code/history already in it (not greenfield),
  run PROCESS.md's Phase 0.5 before interviewing: dispatch read-only analysis agents (never
  self-explore) to map the codebase, commit findings to `docs/coordination/repo-map.md`, then
  tailor concept-interview questions to what the code can't already answer
- [CI / push discipline](feedback_ci_push_discipline.md) — before pushing, rebase onto latest main
  and re-run the full local suite (including DB-gated integration tests against a real DB, no
  self-skip mode, no narrowed subset), once and deliberately, reporting zero new failures versus
  the base commit with failure sets diffed and the pre-existing set named — this is one of the
  push gate's two conditions, see `CLAUDE.md`'s Execute loop step 5 for the other; after pushing,
  a dispatched agent checks the real CI run instead of the coordinator assuming local green means
  CI green
- [Shared-checkout git hygiene](feedback_shared_checkout_git_hygiene.md) — in a shared checkout,
  check `git status` before committing intended paths only, check what's ahead of origin before
  pushing, and never run destructive git ops on a tree that may hold another agent's uncommitted work
- [Never dump .env files](feedback_never_dump_env_files.md) — never `cat`/`head`/`tail`/`echo` a
  credential file's contents, local or remote; inspect variable names only and `source` to use a
  secret without printing it, since a printed secret in a transcript is a leaked secret
- [Never backticks in notify messages](feedback_never_backticks_in_notify_messages.md) — a
  backtick inside a double-quoted `notify.sh "..."` call triggers bash command substitution and can
  execute the embedded text; describe commands in prose or point at a scratch file instead
- [Execute precise instructions as stated](feedback_execute_precise_instructions_as_stated.md) —
  when the founder states a timing/scope/decision precisely, execute it as stated; disagree in one
  sentence and still do it, or ask one direct question, and surface any deviation in the same message
- [Act on the founder's behalf](feedback_act_on_founders_behalf.md) — standing authorization to
  create accounts, log in, and drive authenticated sessions directly instead of bouncing those
  steps back; one honest bound for a platform-blocked step, hand back only that step
