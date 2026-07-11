# Coordinator kit

A portable set of instruction files that turns a Claude Code main session into a pure
**coordinator**: it interviews you, plans, then dispatches every build/research/design/
verification step to `Agent` sub-dispatches, keeping a durable, git-committed record of state
so any session (this one resumed, or a fresh one) can pick up where it left off.

Works for both a brand-new (greenfield) project and an existing codebase. On an existing repo, the
coordinator dispatches read-only analysis agents to map it first — languages/frameworks, layout,
build/test/CI, conventions, debt — commits that to `docs/coordination/repo-map.md`, and tailors the
concept interview to ask only what the code can't already answer. A greenfield repo skips straight
to the interview. See PROCESS.md's Phase 0.5 and the "Boot the first session" section below.

This kit is the distilled, generalized version of a working coordinator setup — the rules in
`CLAUDE.md` and `memory-seed/` encode real corrections a user had to make to get a Claude session
to actually stay in the coordinator role instead of drifting into doing work itself.

## What's in it

| File | Purpose |
|---|---|
| `CLAUDE.md` | The core deliverable — drop into the new project's root. Defines the coordinator role, model routing, execute loop, watchdogs/stall-recovery, verification standard, escalation, question protocol, comms register, backlog discipline, security boundaries. Loaded every session automatically by Claude Code. |
| `PROCESS.md` | The full phase loop (bootstrap → concept → objectives → plan → execute → validate → iterate) and the knowledge-base doc layout. Lives under `docs/coordination/`. |
| `STATE.md` | Empty state-tracking template with section guidance, in-flight-agent/watchdog tracking fields, and one fictional example entry. Lives under `docs/coordination/`; the coordinator edits this constantly. |
| `kickoff-prompt.md` | The first message to paste into a fresh session to boot the coordinator and run Bootstrap + start the Concept interview. Not installed into the project — just paste its contents into chat. |
| `memory-seed/` | Optional. Generalized versions of the behavioral corrections that make the coordinator role stick across sessions (see below). |
| `telegram-bridge/` | Optional. A complete, ready-to-install reference implementation of `<NOTIFY_CHANNEL>` over Telegram — see below. |
| `codex-setup.md` | Optional. Install/invocation guide for the GPT second-opinion (`codex exec`) that `CLAUDE.md`'s Escalation section triggers on judgment-heavy work. |

## Install into a new project

This kit lives in a **private** GitHub repo: `nikolamin/claude-coordinator-kit`. Plain
`raw.githubusercontent.com` curls won't authenticate against a private repo — you need `gh`
(authenticated) or an SSH/HTTPS git clone with your own credentials. Both install paths below
handle that.

### Install with a prompt (recommended)

Paste the block below as the **first message in a fresh Claude Code session, started inside your
new project's root directory**. It is self-contained — it fetches the kit itself, asks you the two
required questions one at a time, installs and customizes the files, then boots the coordinator by
following `kickoff-prompt.md`. You don't need to clone anything yourself first.

```
You're setting up the "coordinator kit" in this project, then booting it. Do this in order,
stopping to ask me questions where noted. Don't do any of the coordinator's actual work yet —
this message only covers installing the kit and then handing off to kickoff-prompt.md.

1. Verify GitHub access: run `gh auth status`. If it fails or isn't logged in, stop and tell me —
   don't attempt any login flow yourself. The kit's repo, `nikolamin/claude-coordinator-kit`, is
   PRIVATE, so a plain `curl` against raw.githubusercontent.com will not work; you must fetch it
   through `gh`, which carries my authentication.

2. Fetch the kit into a scratch location and inspect it:
   `gh repo clone nikolamin/claude-coordinator-kit /tmp/coordinator-kit-install`
   (if `gh repo clone` is unavailable for some reason, fall back to
   `gh api repos/nikolamin/claude-coordinator-kit/tarball --jq . > /tmp/kit.tar.gz` and extract it,
   or `git clone https://github.com/nikolamin/claude-coordinator-kit.git /tmp/coordinator-kit-install`
   using my existing git credentials). Confirm you can see CLAUDE.md, PROCESS.md, STATE.md,
   kickoff-prompt.md, codex-setup.md, memory-seed/, and telegram-bridge/ in the clone before
   continuing.

3. Ask me, ONE question at a time, waiting for my answer before the next:
   a. "What should `<PROJECT>` be?" — the name of this project/product. No options needed, just
      take my answer.
   b. "What should `<NOTIFY_CHANNEL>` be — how do you want the coordinator to ping you?" Offer
      options: (1) the bundled Telegram bridge (`telegram-bridge/` in the kit — asks a follow-up
      for the bridge's install directory on this machine, since it's a machine-level service, not
      per-project), (2) a different existing mechanism (Slack webhook, email script, desktop
      notification command — ask me for the exact invocation), (3) "just tell me in chat, no
      out-of-band channel." Wait for my answer.

4. Place the files from /tmp/coordinator-kit-install into this project:
   - `CLAUDE.md` → this project's root. If a `CLAUDE.md` already exists here, do NOT overwrite it —
     MERGE: append the coordinator-kit's rules (or a link to them) into the existing file, keeping
     every existing project convention already documented there. Read both fully before merging.
   - `PROCESS.md` and `STATE.md` → `docs/coordination/` (create the directory).
   - `memory-seed/*` → optional. If I asked for it (or if you think it's worth recommending — it
     seeds behavioral corrections so the coordinator role sticks across sessions), copy the files
     into `~/.claude/projects/<slug>/memory/`, where `<slug>` is this project's absolute path with
     every `/` replaced by `-` (e.g. `/Users/me/code/my-app` → `-Users-me-code-my-app`). Create
     that directory if it doesn't exist yet.
   - `telegram-bridge/` → optional, only if I chose it in step 3b. Copy the whole directory to a
     sibling tools location outside this project (it's a machine-level service meant to be reused
     across projects, e.g. `~/claude-telegram-bridge` or wherever I say), then follow its
     `SETUP.md` top to bottom for bot creation, `.env`, and OS service install. Never print or log
     the bot token; let me paste it into `.env` myself if a step calls for it.

5. Substitute every placeholder in the files you just installed: replace all `<PROJECT>` with my
   answer from 3a, and all `<NOTIFY_CHANNEL>` with my answer from 3b (a concrete invocation, e.g.
   the notify.sh path, not the literal word). Then run
   `grep -rn '<PROJECT>\|<NOTIFY_CHANNEL>' CLAUDE.md docs/coordination/ 2>/dev/null` (and the
   memory-seed destination if you copied it) to confirm zero matches remain. Fix any you find.

6. Now read `/tmp/coordinator-kit-install/kickoff-prompt.md` in full, and follow its instructions
   exactly as if I had pasted its contents as my next message to you — it will direct you through
   confirming/re-resolving `<NOTIFY_CHANNEL>`, running Bootstrap, branching on greenfield vs.
   existing-project (repo-analysis agents + `repo-map.md` for the latter, per PROCESS.md Phase
   0.5), and starting the Concept interview one question at a time. Do not skip or summarize any
   of its steps.

7. Once kickoff-prompt.md's instructions are underway, clean up: remove
   /tmp/coordinator-kit-install.
```

### Manual install

1. Clone the repo somewhere scratch, e.g. `gh repo clone nikolamin/claude-coordinator-kit
   /tmp/coordinator-kit-install` (private repo — requires `gh auth status` to be logged in first;
   a plain `raw.githubusercontent.com` curl will not authenticate).
2. Copy `CLAUDE.md` to the new project's root directory.
3. Create `docs/coordination/` in the new project; copy `PROCESS.md` and `STATE.md` into it.
4. Open the copied `CLAUDE.md` and replace every `<PROJECT>` with the project's actual name, and
   every `<NOTIFY_CHANNEL>` with how you want to be pinged (see below). Search for both tokens —
   don't leave placeholders in a file Claude Code loads every session. If you're seeding memory
   (step 6), replace `<PROJECT>` in `memory-seed/MEMORY.md`'s heading too.
5. Skim `PROCESS.md`'s "Knowledge base layout" section — it references `docs/concept/`,
   `docs/objectives.md`, `docs/plan.md`, `docs/decisions/`, `docs/validation/`. These don't need
   to exist yet; the kickoff prompt's Bootstrap step creates them. If your project has a strong
   opinion about the `docs/concept/` sub-structure already, adjust the note in `PROCESS.md`
   accordingly before the first session — it's meant to be edited, not treated as gospel.
6. (Optional but recommended) Copy `memory-seed/*.md` into the new project's Claude Code memory
   directory: `~/.claude/projects/<slug>/memory/`, where `<slug>` is the project's absolute path
   with every `/` replaced by `-` (e.g. `/Users/you/code/my-app` becomes
   `-Users-you-code-my-app`). If that directory doesn't exist yet, create it — it's populated lazily
   on first use otherwise, so seeding it up front is the only way to have it present from session 1.
   These files seed the behavioral corrections so the coordinator doesn't have to re-learn them the
   hard way (each one below was originally a real correction after a real mistake).
   `CLAUDE.md` alone carries the rules for any session that loads it, so this step is not
   load-bearing — but only `memory-seed/MEMORY.md` (not the individual linked files) is guaranteed
   to auto-load into a fresh session's context the way project instructions do. That's why each
   line in `MEMORY.md` is written to be actionable on its own, not just a pointer — treat the
   linked per-topic files as reference detail you or an agent can open on demand, not as content
   you can assume is already in context.
7. Remove the scratch clone from step 1 once everything you need is copied out.

### What to customize

- **`<PROJECT>`** — the project/product name. Appears in `CLAUDE.md`'s title and in
  `memory-seed/MEMORY.md`'s heading.
- **`<NOTIFY_CHANNEL>`** — whatever notification mechanism you want the coordinator to use for
  checkpoint pings and attention-needed pings. This kit bundles a ready-to-install Telegram
  implementation (`telegram-bridge/`, see below) — install it and point `<NOTIFY_CHANNEL>` at it,
  or use any other channel: a Slack webhook script, an email-send script, a desktop notification
  command, or literally "tell me in chat" if there's no out-of-band channel. If you have a
  notification script, tell the coordinator its invocation in the first session (the kickoff
  prompt asks for this explicitly) rather than baking a specific command into `CLAUDE.md` — keep
  the instructions file portable.
- **Deploy targets / infra specifics** — this kit deliberately has none baked in. `STATE.md`'s
  "Infrastructure" section is where the coordinator records deploy URLs, server access patterns,
  and CI/deploy pipeline state once your project has them. Nothing to customize up front.
- **Model tier names** — `CLAUDE.md` assumes the Agent tool's model parameter accepts something
  like `sonnet`/`opus`/`haiku`/a top-tier advice model. If your environment's Agent tool uses
  different tier names, update the Model routing section accordingly.
- **Telegram bridge placeholders** — only relevant if you install the optional `telegram-bridge/`.
  `<BRIDGE_DIR>`, `<PYTHON3_PATH>`, `<EXTRA_PATH_DIRS>`, and the launchd `Label` / systemd unit
  name are filled in during bridge install, not here — each is documented inline in
  `telegram-bridge/SETUP.md` and in the service/plist template headers at the point you replace it.
  Nothing in `CLAUDE.md` needs changing for these.

## Telegram bridge (optional)

`telegram-bridge/` is a complete, ready-to-install reference implementation of `<NOTIFY_CHANNEL>`:
a phone-reachable Telegram bot that relays messages into a live coordinator session mid-conversation
(not a disconnected headless call), plus a `notify.sh`/`react.sh` pair the coordinator uses to
reply and acknowledge, and file delivery via the Bot API. It's a machine-level service — install it
once and reuse it across every project's coordinator, or run a second bot for channel separation.
See `telegram-bridge/SETUP.md` for the full walkthrough (bot creation, `.env`, launchd/systemd
install, the relay-mode architecture, and the reaction-emoji/file-delivery gotchas). If you're not
using Telegram, ignore this directory entirely — nothing else in the kit depends on it.

## Boot the first session

1. `cd` into the new project, start Claude Code.
2. Paste the contents of `kickoff-prompt.md` as your first message.
3. The coordinator resolves `<NOTIFY_CHANNEL>` (asks you, updates `CLAUDE.md`; if you're using the
   bundled Telegram bridge it also asks for the bridge directory path and arms a monitor on its
   relay inbox immediately), then runs Bootstrap: reads `CLAUDE.md` + `PROCESS.md`, creates the doc
   skeleton, commits it, tells you it's done.
4. **Greenfield vs. existing project:** if the repo already has real code (not just the fresh doc
   skeleton) or meaningful git history, the coordinator dispatches read-only repo-analysis agents
   before interviewing you, and commits the findings to `docs/coordination/repo-map.md` — see
   PROCESS.md's Phase 0.5. A genuinely empty/new repo skips straight to the interview.
5. The coordinator goes into the Concept interview: themed rounds, but **one question at a time**
   within each round — context, its own reasoning, 2-4 options with a marked recommendation, per
   `CLAUDE.md`'s Question protocol. On an existing project, questions reference `repo-map.md`
   findings instead of asking from a blank slate. It should never dump a giant questionnaire on
   you.
6. Answer the concept questions across as many turns/sessions as needed. A dispatched agent
   synthesizes each round's answers into `docs/concept/` docs (the coordinator itself never does
   this), then the coordinator asks you to approve before moving
   to Objectives. From there it's Objectives → Plan (another user-approval gate) → Execute (fully
   autonomous, checkpoint pings only, with within-session watchdogs so it never silently stalls) →
   Validate → Iterate.

## Codex / second-model review of this kit

This kit's drafts were reviewed with a `codex exec` pass (see
`memory-seed/feedback_escalation_protocols.md` for why a second-model opinion matters for
judgment-heavy artifacts like this one). Disposition, in brief: taken — clarified that the
coordinator itself never verifies (only dispatches verifiers); added a bootstrap exception for
one-time skeleton creation; added a hard cap (2 failed re-prompt cycles) before the execute loop
must escalate instead of retrying indefinitely; added a "non-trivial" heuristic to reduce
rationalization room; tied escalation-tier wording consistently between `CLAUDE.md` and
`memory-seed/`; fixed a "top-level five" vs. six miscount in `PROCESS.md`; added approval-gate and
in-flight-agent tracking guidance to `STATE.md`; marked the `STATE.md` example entry as
illustrative/deletable; clarified plan.md-vs-STATE.md placement criteria for follow-ups; reordered
`kickoff-prompt.md` to resolve the notification channel before bootstrapping. Rejected — a full
concurrency/locking protocol and a formal `plan.md` schema file (out of scope for a portable kit;
addressed instead with a short inline task-entry checklist in `PROCESS.md` and a one-line
sequential-by-default rule); enumerating exhaustive numeric thresholds for terms like "high test
coverage" (would over-specify and fight the terse, judgment-preserving register the source
material uses — the "when unsure, treat it as non-trivial" heuristic addresses the worst of the
rationalization risk without turning this into a rulebook).
