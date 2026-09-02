---
name: respawn-dont-resume-and-bulk-output-to-files
description: "A failed verify cycle gets a fresh respawned agent pointed at the report files on disk, never a SendMessage resume of the grown agent; and an agent's bulk command output (test suites, builds, big greps) goes to a scratch file, with only the decisive lines pasted back."
metadata:
  type: feedback
---

Two habits that dominate the token bill of a multi-agent coordinator session, both invisible
unless you measure: **resuming a large agent** instead of respawning a small one, and **pasting
bulk command output** into an agent's own transcript.

**Why:** measured on one real session — 11 agents, ~48M weighted tokens — agents re-reading their
own growing transcripts were ~54% of total cost. Two agents that were RESUMED three times each
(via `SendMessage` after 30-60 minute gaps, so every resume landed on a cold prompt cache and
re-wrote the entire grown transcript at 2x write cost) accounted for 40% of everything. Raw
test-suite logs pasted into transcripts, then re-read by that agent on every subsequent step of
its turn, were ~29% of agent cost. The briefs themselves — the part that feels expensive to
write — were under 2%. The expensive thing is never the prompt; it's the transcript the prompt
grows into, re-read and re-written on every step.

**How to apply:**

- **Retry = respawn, not resume.** When a verifier fails a task, spawn a *fresh* agent with the
  specific gap, pointed at the artifacts on disk (the build report, design doc, and verify report
  paths) rather than resuming the agent that already carries the whole failed attempt in context.
  The fresh agent reads only what it needs; the resumed one re-pays for everything it ever saw.
  This changes nothing about the retry cap — still 2 failed cycles on the same gap, escalate on
  the 3rd.
- **Bulk output goes to a file.** Every infra/execution brief says so explicitly: bulk output
  (test suites, builds, big greps) is redirected to a scratch file under the project's scratch
  directory, and only the decisive lines come back into the transcript — failure names, exit
  codes, the mutation transcript. The coordinator gates on those lines anyway; the other 4,000
  lines are pure re-read tax on every later step of that agent's turn.
- Both are brief-writing requirements, not coordinator-only habits — a dispatched agent won't
  infer either one, so state them in the brief.

**Second measurement (2026-09-02):** 60% of agent cost was an agent re-reading its own context;
81% of tool-result bytes came from the 18% of results over 4 KB. Four brief rules followed, all in
`coordinator-kit:agent-brief-hygiene`: step cap ~150 per agent with handover through files and a
fresh agent continuing from disk; bulk output never enters the transcript (a hook caps Bash results
at 3 KB, the brief still says so); screenshots are final proof only, max 2 per task; reads carry
line ranges (a whole-file Read over 400 lines is denied).
