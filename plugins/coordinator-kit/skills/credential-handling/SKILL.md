---
name: credential-handling
description: Use task-authorized account access while keeping credentials out of transcripts, arguments, derived artifacts and coordinator state. Use before dispatching work involving login, secrets or database access; restate the operative constraints in the brief.
---

# Credential and account handling

Use the project's existing account-access grants to complete the authorized task, including
test-account creation and authenticated testing when covered. Do not re-ask for the same grant.
The plugin itself grants no access. A pasted credential authorizes its stated task use; it does
not widen scope to financial transactions, production changes, public releases or unrelated sends.

If a platform limit or device-bound 2FA blocks one step, state the real reason and complete
everything else. Hand back only that specific user-only step; do not abandon the entire task
because it involves credentials. Required verification remains pending until actually completed.

- Never print a credential file's contents: no cat/head/tail/echo on .env or equivalent,
  local or remote. Inspect names only; load values without exposing them in output.
- Do not put expanded secrets in command arguments: shell errors/process listings can expose
  them even if nothing explicitly echoes. Use supported config, environment, stdin or secret
  stores, and check diagnostic output is redacted.
- No credentials in state, the coordination database, memory, logs, reports, commits, generated
  fixtures, backup patches or derived scratch copies. This includes discovered/decoded secrets,
  not only ones pasted by the founder. If persistence is needed, use the approved secret store
  or gitignored local config. Record locations, not values.
- Enforce read-only production database access structurally with a restricted role or supported
  session/transaction control. Validate the mechanism in a safe fixture/test environment and
  confirm it is active on the real connection. Do not try a potentially successful production
  write merely to demonstrate denial; read-only task authorization does not permit that probe.
- Local restores still contain restricted data and may retain live delivery destinations.
  Keep identifiers-only evidence where required and isolate outbound integrations before running.

Restate these operative rules in any agent brief involving credentials/auth/DB access. Naming a
skill alone does not guarantee another agent loaded it. Existing founder decisions about known
issues remain in the canonical record; check them before repeating an unchanged escalation.
