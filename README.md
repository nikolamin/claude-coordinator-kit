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
| `CLAUDE.md` | The core deliverable — drop into the new project's root. Defines the coordinator role, model routing, execute loop, watchdogs/stall-recovery, verification standard, escalation, question protocol, comms register, backlog discipline, credential handling, and a Guardrails section the coordinator fills in with project-specific hard limits at Plan time. Loaded every session automatically by Claude Code. |
| `PROCESS.md` | The full phase loop (bootstrap → concept → objectives → plan → execute → validate → iterate) and the knowledge-base doc layout. Lives under `docs/coordination/`. |
| `STATE.md` | Empty state-tracking template with section guidance, in-flight-agent/watchdog tracking fields, a size budget with an archive path (`docs/coordination/state-archive/`) for trimming old entries, and one fictional example entry. Lives under `docs/coordination/`; the coordinator edits this constantly. |
| `kickoff-prompt.md` | The first message to paste into a fresh session to boot the coordinator and run Bootstrap + start the Concept interview. Not installed into the project — just paste its contents into chat. |
| `memory-seed/` | Optional. Generalized versions of the behavioral corrections that make the coordinator role stick across sessions (see below). |
| `telegram-bridge/` | Optional. A complete, ready-to-install reference implementation of `<NOTIFY_CHANNEL>` over Telegram — see below. |
| `codex-setup.md` | Optional. Install/invocation guide for the GPT second-opinion (`codex exec`) that `CLAUDE.md`'s Escalation section triggers on judgment-heavy work. Installed to `docs/coordination/codex-setup.md` alongside `PROCESS.md`/`STATE.md` — `CLAUDE.md` points at it there. |
| `UPDATING.md` | Per-file update rules and a paste-able update prompt for bringing an already-installed project onto a newer kit version. Not installed into the project — like `kickoff-prompt.md`, just fetch and paste/read it when updating. See "Updating" below. |
| `docs/coordination/kit-version.md` | Not a kit file — created by the installer during install (see below), not shipped in the kit's own tree. Records which kit commit was installed, the date, and whether the bridge/memory seed were included. What `UPDATING.md` reads to know where you're updating from. |

## Install into a new project

This kit lives in a public GitHub repo: `nikolamin/claude-coordinator-kit`. A plain `git clone`
over HTTPS works — no GitHub authentication needed.

### Install with a prompt (recommended)

Paste the block below as the **first message in a fresh Claude Code session, started inside your
new project's root directory**. It is self-contained — it fetches the kit itself, asks you the
required questions one at a time (project name, notify channel, Chrome browser access, memory
seeding), installs and customizes the files, then boots the coordinator by following
`kickoff-prompt.md`. You don't need to clone anything yourself first.

```
You're setting up the "coordinator kit" in this project, then booting it. Do this in order,
stopping to ask me questions where noted. Don't do any of the coordinator's actual work yet —
this message only covers installing the kit and then handing off to kickoff-prompt.md. You are
explicitly allowed to commit and push in this project — for the kit installation itself and for
all later coordinator work; never stop to ask permission for a commit or push.

1. Fetch the kit into a scratch location and inspect it:
   `git clone https://github.com/nikolamin/claude-coordinator-kit /tmp/coordinator-kit`
   Confirm you can see CLAUDE.md, PROCESS.md, STATE.md, kickoff-prompt.md, codex-setup.md,
   UPDATING.md, memory-seed/, and telegram-bridge/ in the clone before continuing.

2. Before asking me anything or copying a single file, guard against re-running this on a project
   that already has the kit installed: check whether `docs/coordination/kit-version.md` exists, or
   whether `docs/coordination/STATE.md` exists with content beyond the template stub — concretely,
   its `## Current` section reads as anything other than the single line `- Phase: Bootstrap. No
   tasks dispatched yet.`, or its `## Agent log` section holds any entry beyond the one EXAMPLE
   entry. If either holds, stop here: tell me plainly that this project already has the kit
   installed, that re-running this install prompt is destructive (it would silently wipe
   `docs/coordination/STATE.md` back to an empty template, destroying the live phase, in-flight
   agent tracking, and durable decisions), and that I should use the kit's `UPDATING.md` instead.
   Do not continue to any step below — not the questions in step 3, not a partial file copy — once
   either condition holds. A missing `kit-version.md` is NOT by itself evidence that nothing is
   installed — it only means this install predates the version stamp (older installs have none).
   Always evaluate the `STATE.md`-content check too, regardless of what the `kit-version.md` check
   found; that second check is what actually catches a pre-stamp existing install, and skipping it
   after a missing `kit-version.md` would silently defeat the whole guard. `UPDATING.md` calls this
   case a "pre-stamp install, version unknown" and has its own explicit handling for it.

3. Ask me, ONE question at a time, waiting for my answer before the next:
   a. "What should `<PROJECT>` be?" — the name of this project/product. No options needed, just
      take my answer.
   b. "What should `<NOTIFY_CHANNEL>` be — how do you want the coordinator to ping you?" Offer
      options: (1) the bundled Telegram bridge (`telegram-bridge/` in the kit — asks a follow-up
      for the bridge's install directory on this machine, since it's a machine-level service, not
      per-project; bot creation and credentials are collected interactively in chat during step 4,
      never via manual file edits), (2) a different existing mechanism (Slack webhook, email
      script, desktop notification command — ask me for the exact invocation, and if it needs a
      credential, apply the same interactive-collection pattern as step 4's Telegram flow), (3)
      "just tell me in chat, no out-of-band channel." Wait for my answer. If I pick the Telegram
      bridge, ask its follow-up (the install directory) immediately, as part of 3b, and wait for
      that answer too before moving on to 3c.
   c. "Do you want to allow Chrome browser usage — Claude's Chrome integration, driving your real
      logged-in browser — for the coordinator's verification work later?" Offer: (1) yes (needed
      for anything that requires your actual logged-in session, e.g. sites behind auth), (2) no,
      verification will use the built-in browser pane only. Wait for my answer.
   d. "Seed the coordinator memory files (the kit's memory-seed/)?" Offer: (1) yes — recommended,
      it seeds the behavioral corrections that make the coordinator role stick across sessions,
      (2) no. Wait for my answer.

4. Place the files from /tmp/coordinator-kit into this project:
   - `CLAUDE.md` → this project's root. If a `CLAUDE.md` already exists here, do NOT overwrite it —
     MERGE: inline the coordinator-kit's rules content into the existing file, keeping every
     existing project convention already documented there. Read both fully before merging. Never
     link to the scratch clone (/tmp/coordinator-kit is deleted in step 9); linking to the GitHub
     repo as a reference is fine, but the rules themselves must be in the file.
   - `PROCESS.md`, `STATE.md`, and `codex-setup.md` → `docs/coordination/` (create the directory).
     `CLAUDE.md`'s Escalation section points at `codex-setup.md` there — it must land in this
     directory or that pointer is dead on every fresh install.
   - `memory-seed/*` → only if I said yes in 3d. Copy the files into
     `~/.claude/projects/<slug>/memory/`, where `<slug>` is this project's absolute path with
     every `/` replaced by `-` (e.g. `/Users/me/code/my-app` → `-Users-me-code-my-app`). Create
     that directory if it doesn't exist yet.
   - `telegram-bridge/` → optional, only if I chose it in step 3b. Copy the whole directory to a
     sibling tools location outside this project (it's a machine-level service meant to be reused
     across projects, e.g. `~/claude-telegram-bridge` or wherever I say). Then set it up yourself,
     interactively — do not tell me to hand-edit files:
     a. Tell me the exact @BotFather steps (open Telegram, message @BotFather, send `/newbot`,
        follow its name/username prompts) and ask me to paste the resulting bot token directly
        into this chat.
     b. Check first: if `.env` already exists in the bridge directory, it's an already-configured
        bridge (likely shared with another project, since the bridge is machine-level) — leave it
        untouched and skip to (d). Only if `.env` is missing, `cp .env.example .env` inside the
        bridge directory and fill in `TELEGRAM_BOT_TOKEN` with the token I pasted. Never echo the
        token back, never commit `.env`, never write the token anywhere else — not STATE.md, not a
        memory file, not a log.
     c. Ask me to open a chat with the new bot and send it any message (e.g. "hi"), then fetch the
        chat id yourself via `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates"` (or
        `python3 get_chat_id.py`, after `pip install requests` — the script imports it), confirm
        the detected name/id with me, and write it into `TELEGRAM_CHAT_ID` in `.env`.
     d. Continue with the rest of `telegram-bridge/SETUP.md` top to bottom (Python dependency, OS
        service install) — skip any `.env` setup it describes if (b) already found one in place.
     If I instead chose a different mechanism in step 3b that needs a credential (e.g. a Slack
     webhook URL), apply the same pattern: ask for it in chat, write it into a gitignored config
     location yourself, never ask me to hand-edit a file.
     If I did NOT choose the Telegram bridge in step 3b, skip this bullet entirely — and in step 5,
     delete rather than substitute the placeholder that would otherwise reference it.

5. Substitute every placeholder in the files you just installed: replace all `<PROJECT>` with my
   answer from 3a (including `memory-seed/MEMORY.md`'s heading, if you copied it in step 4), all
   `<NOTIFY_CHANNEL>` with the concrete invocation resulting from step 4 (e.g. the installed
   notify.sh's absolute path — not the literal channel name from 3b), and, if I chose the Telegram
   bridge in 3b, all `<BRIDGE_DIR>` in both `CLAUDE.md` and (if copied) `memory-seed/MEMORY.md`
   with the absolute path you placed `telegram-bridge/` at in step 4 — both files reference the
   bridge's `notify.sh`/`react.sh`/`typing.sh`/`send-file.sh`/`relay-inbox.jsonl` by that
   placeholder, and it needs a real path just like `<NOTIFY_CHANNEL>` does. If I did NOT choose the
   Telegram bridge, don't leave `<BRIDGE_DIR>` dangling — delete the whole "If the Telegram
   bridge ... is installed" subsection near the end of `CLAUDE.md`'s Comms register, and, if you
   copied memory-seed, the Telegram bridge bullet near the end of `memory-seed/MEMORY.md`, instead,
   since their instructions describe machinery I don't have.
   Then run `grep -rn '<PROJECT>\|<NOTIFY_CHANNEL>\|<BRIDGE_DIR>' CLAUDE.md docs/coordination/`
   (and the memory-seed destination if you copied it) to confirm zero matches remain — don't
   suppress stderr on this check (no `2>/dev/null`): a real error, like a bad path, must surface
   as one instead of being swallowed into a false "zero matches" pass. Fix any you find.

6. Write the version stamp, while the scratch clone from step 1 still exists (the commit SHA only
   lives there — step 9 removes it): get the short SHA with
   `git -C /tmp/coordinator-kit rev-parse --short HEAD`, then create
   `docs/coordination/kit-version.md` with the real SHA, today's date, and the real outcome of my
   step 3b/3d answers (keep only the line that applies for the bridge and for memory seed, drop
   the other):

       # Kit version

       Installed from claude-coordinator-kit commit `<sha>` (`<YYYY-MM-DD>`).

       - Telegram bridge: installed at `<BRIDGE_DIR>` | not installed
       - Memory seed: installed at `~/.claude/projects/<slug>/memory/` | not installed

       To update, follow the kit's `UPDATING.md` — do not re-run the install prompt.

7. If I said yes to Chrome browser usage in step 3c, exercise it now: open
   `https://github.com/nikolamin/claude-coordinator-kit` with the Chrome browser tool and confirm
   it actually renders — read the page title, don't just issue the navigate call and assume it
   worked. Work through whatever obstacles come up: if the Claude-in-Chrome browser extension
   isn't installed yet, guide me through installing it; if a permission/connection or tab-access
   prompt appears, ask me to grant it, then retry. Keep retrying until the page renders and you've
   read its title — that's the pass signal. If any step needs an action only I can take, name it
   precisely and wait. Once done (or immediately, if I said no in step 3c), record the outcome in
   `docs/coordination/STATE.md`'s Infrastructure section: either "Chrome browser verification:
   allowed, smoke-tested against the kit's GitHub page" or "Chrome browser verification: not
   allowed, built-in browser pane only."

8. Now read `/tmp/coordinator-kit/kickoff-prompt.md` in full, and follow its instructions
   exactly as if I had pasted its contents as my next message to you — it will direct you through
   confirming/re-resolving `<NOTIFY_CHANNEL>`, running Bootstrap, branching on greenfield vs.
   existing-project (repo-analysis agents + `repo-map.md` for the latter, per PROCESS.md Phase
   0.5), and starting the Concept interview one question at a time. Do not skip or summarize any
   of its steps.

9. Once kickoff-prompt.md's instructions are underway, clean up: remove /tmp/coordinator-kit — the
   version stamp in step 6 already captured everything needed from it.
```

### Manual install

If you're having a Claude Code session run these steps for you rather than doing them yourself, it
is explicitly allowed to commit and push without stopping to ask permission — same as the scripted
install prompt above.

1. Clone the repo somewhere scratch, e.g. `git clone https://github.com/nikolamin/claude-coordinator-kit
   /tmp/coordinator-kit-install`.
2. Guard against re-running this on an already-installed project: check whether
   `docs/coordination/kit-version.md` exists, or whether `docs/coordination/STATE.md` exists with
   content beyond the template stub — concretely, its `## Current` section reads as anything other
   than the single line `- Phase: Bootstrap. No tasks dispatched yet.`, or its `## Agent log`
   section holds any entry beyond the one EXAMPLE entry. If either holds, stop: this project
   already has the kit installed, re-running this install is destructive (it would wipe
   `docs/coordination/STATE.md` back to an empty template, destroying live phase and in-flight
   agent tracking), so use the kit's `UPDATING.md` instead of continuing with step 3 onward. A
   missing `kit-version.md` is NOT by itself evidence that nothing is installed — it only means
   this install predates the version stamp. Always evaluate the `STATE.md`-content check too,
   regardless of what the `kit-version.md` check found; that second check is what actually catches
   a pre-stamp existing install, and skipping it after a missing `kit-version.md` would silently
   defeat the whole guard. `UPDATING.md` calls this case a "pre-stamp install, version unknown"
   and has its own explicit handling for it.
3. Copy `CLAUDE.md` to the new project's root directory.
4. Create `docs/coordination/` in the new project; copy `PROCESS.md`, `STATE.md`, and
   `codex-setup.md` into it. `CLAUDE.md`'s Escalation section points at `codex-setup.md` at that
   path — skip this and the pointer resolves to nothing.
5. (Optional) If you want the Telegram bridge, copy the whole `telegram-bridge/` directory out of
   the scratch clone now, to wherever you want it installed — it's a machine-level service, not
   per-project, so it doesn't have to live inside this project (see "Telegram bridge" below). Do
   this before step 10 removes the clone, or you'll have nothing left to copy. Note the absolute
   path you chose; you need it in step 6 and, if you seed memory, step 8 too, plus throughout
   `telegram-bridge/SETUP.md`. If `<BRIDGE_DIR>` already has a configured `.env` (e.g. this machine
   already runs the bridge for another project), leave it alone — don't repeat
   `telegram-bridge/SETUP.md`'s `.env` steps over a live bridge and clobber its token.
6. Open the copied `CLAUDE.md` and replace every `<PROJECT>` with the project's actual name, and
   every `<NOTIFY_CHANNEL>` with how you want to be pinged (see below). If you copied the Telegram
   bridge in step 5, also replace every `<BRIDGE_DIR>` in `CLAUDE.md` with the absolute path from
   that step — `CLAUDE.md`'s Comms register section references the bridge's
   `notify.sh`/`react.sh`/`typing.sh`/`send-file.sh`/`relay-inbox.jsonl` by that placeholder. If
   you did NOT install the bridge, delete the "If the Telegram bridge ... is installed" subsection
   near the end of the Comms register instead of leaving `<BRIDGE_DIR>` unresolved — its
   instructions describe machinery you don't have. Then run `grep -rn
   '<PROJECT>\|<NOTIFY_CHANNEL>\|<BRIDGE_DIR>' CLAUDE.md` to confirm zero matches remain — don't
   leave placeholders in a file Claude Code loads every session. If you're seeding memory (step
   8), the same `<PROJECT>` and `<BRIDGE_DIR>` substitutions — or, if you skipped the bridge, the
   same subsection deletion — apply to `memory-seed/MEMORY.md`'s heading and Telegram bridge
   bullet too; do that as part of step 8, once the file is at its real destination.
7. Skim `PROCESS.md`'s "Knowledge base layout" section — it references `docs/concept/`,
   `docs/objectives.md`, `docs/plan.md`, `docs/decisions/`, `docs/validation/`, plus
   `.coordinator-scratch/` (gitignored, at the project root, not inside the `docs/` tree). These
   don't need to exist yet; the kickoff prompt's Bootstrap step creates them. (The section also
   documents `docs/playbooks/`, but that one is intentionally *not* part of the Bootstrap
   skeleton — it's created later, only once the project actually has a recurring scheduled
   procedure worth checking in.) If your project has a strong opinion about the `docs/concept/`
   sub-structure already, adjust the note in `PROCESS.md` accordingly before the first session —
   it's meant to be edited, not treated as gospel.
8. (Optional but recommended) Copy `memory-seed/*.md` into the new project's Claude Code memory
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
   you can assume is already in context. In the copied `MEMORY.md`, replace `<PROJECT>` in its
   heading with the project's actual name. If you copied the Telegram bridge in step 5, also
   replace every `<BRIDGE_DIR>` in its Telegram bridge bullet with the absolute path from that
   step; if you did NOT install the bridge, delete that bullet instead of leaving `<BRIDGE_DIR>`
   unresolved. Then run `grep -rn '<PROJECT>\|<BRIDGE_DIR>' ~/.claude/projects/<slug>/memory/` to
   confirm zero matches remain — don't leave placeholders in the file that auto-loads every
   session.
9. Write the version stamp, before step 10 removes the scratch clone (the commit SHA only lives
   there): get the short SHA with `git -C /tmp/coordinator-kit-install rev-parse --short HEAD`,
   then create `docs/coordination/kit-version.md` with the real SHA, today's date, and the real
   outcome of steps 5 and 8 (keep only the line that applies for the bridge and for memory seed,
   drop the other):

   ```
   # Kit version

   Installed from claude-coordinator-kit commit `<sha>` (`<YYYY-MM-DD>`).

   - Telegram bridge: installed at `<BRIDGE_DIR>` | not installed
   - Memory seed: installed at `~/.claude/projects/<slug>/memory/` | not installed

   To update, follow the kit's `UPDATING.md` — do not re-run the install prompt.
   ```
10. Remove the scratch clone from step 1 once everything you need is copied out — including
    `telegram-bridge/` from step 5, if you're installing it.

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
- **Model tier names** — `CLAUDE.md` assumes the Agent tool's model parameter accepts
  `sonnet`/`opus`/`haiku`/`fable` (its build, verifier, cheapest-mechanical, and escalation-advice
  tiers respectively). If your environment's Agent tool uses different tier names, update the
  Model routing section accordingly.
- **`<BRIDGE_DIR>`** — only relevant if you install the optional `telegram-bridge/`, but unlike
  the placeholders below, this one *does* require edits beyond copying files as-is: it appears in
  `CLAUDE.md`'s Comms register section (`notify.sh`/`react.sh`/`typing.sh`/`send-file.sh`/
  `relay-inbox.jsonl` paths) and, if you seeded `memory-seed/`, in `memory-seed/MEMORY.md`'s
  Telegram bridge bullet too — both need the directory's absolute install path the same way
  `<PROJECT>` and `<NOTIFY_CHANNEL>` do (see the install steps above). If you don't install the
  bridge, delete `CLAUDE.md`'s Telegram subsection and, if you seeded memory, `MEMORY.md`'s
  Telegram bridge bullet, instead of leaving the placeholder unresolved.
- **`<PYTHON3_PATH>`, `<EXTRA_PATH_DIRS>`, launchd `Label` / systemd unit name** — also only
  relevant if you install the optional `telegram-bridge/`, and unlike `<BRIDGE_DIR>` these never
  appear in `CLAUDE.md` — they're filled in during bridge install, inside the service/plist
  templates only, each documented inline in `telegram-bridge/SETUP.md` and in the template headers
  at the point you replace it.

## Updating

Re-running an install path above on a project that already has the kit is not the update path —
it re-copies files wholesale instead of merging, and silently wipes the live
`docs/coordination/STATE.md` in the process. Both install paths guard against this and point you
at `UPDATING.md` instead — via either `docs/coordination/kit-version.md` existing, or (for an
install made before that stamp existed) `docs/coordination/STATE.md` already holding real content;
the guard does not depend on `kit-version.md` alone. Fetch `UPDATING.md` from the kit's repo and
follow it: it has the per-file update rules (what gets REPLACEd, what's NEVER TOUCHed, what gets
MERGEd — including a diff-before-overwrite check on every REPLACE-class file, since "kit-owned by
design" doesn't guarantee a given install's copy was never hand-patched) and a paste-able update
prompt of its own.

## Telegram bridge (optional)

`telegram-bridge/` is a complete, ready-to-install reference implementation of `<NOTIFY_CHANNEL>`:
a phone-reachable Telegram bot that relays messages into a live coordinator session mid-conversation
(not a disconnected headless call), plus `notify.sh`/`react.sh`/`send-file.sh`/`typing.sh` helpers
the coordinator uses to reply, acknowledge, deliver files, and show a live typing indicator. It's a
machine-level service — install it once and reuse it across every project's coordinator, or run a
second bot for channel separation.
See `telegram-bridge/SETUP.md` for the full walkthrough (bot creation, `.env`, launchd/systemd
install, the relay-mode architecture, and the reaction-emoji/file-delivery gotchas). If you're not
using Telegram, ignore this directory entirely — nothing else in the kit depends on it.

Beyond the core 1:1 DM relay, the bridge also supports several optional, purely additive
capabilities: group chat (a gated, @mention/reply-triggered relay for a Telegram group, on top of
the founder's DM), media relay (voice/photo/video/document messages downloaded and, via
`process-media.sh`, transcribed/frame-extracted locally), a significance-gated daily activity
digest (sends only on a notably active or flagged day, not every day), and an optional email
monitor (polls an IMAP inbox and surfaces new mail the same way relay mode surfaces Telegram
messages). All are off by default and documented in `telegram-bridge/SETUP.md` and
`telegram-bridge/EMAIL-MONITOR.md`.

## Boot the first session

**Only needed if you used Manual install above.** The guided install prompt already ends by
reading `kickoff-prompt.md` and following it in the same session (its step 8) — if that's the path
you took, this already happened automatically and there's nothing to do here. This section exists
for Manual-install founders, who still need to start a session and hand it `kickoff-prompt.md`
themselves.

1. `cd` into the new project, start Claude Code.
2. Paste the contents of `kickoff-prompt.md` as your first message.
3. The coordinator checks whether `<NOTIFY_CHANNEL>` in `CLAUDE.md` is already resolved — this
   branches on whether you actually did step 6's substitution above, not on having installed
   manually per se:
   - **If you did step 6:** `<NOTIFY_CHANNEL>` (and `<BRIDGE_DIR>`, if you installed the bridge)
     is already a concrete value. The coordinator confirms it back to you in one line and moves on
     — it does not ask again. If you're using the bundled Telegram bridge, it still arms a Monitor
     on `<BRIDGE_DIR>/relay-inbox.jsonl` now regardless, since a fresh session's Monitor starts
     unarmed even though the placeholder was already resolved earlier.
   - **If you skipped step 6** (or are handing this file to a session without having edited
     `CLAUDE.md` yourself): `<NOTIFY_CHANNEL>` is still the literal placeholder, so the coordinator
     asks you for it, updates `CLAUDE.md`, and — if you're using the bundled Telegram bridge —
     also asks for the bridge directory path, substitutes it for every `<BRIDGE_DIR>` in
     `CLAUDE.md`, and arms the same Monitor.

   Either way, it then runs Bootstrap: reads `CLAUDE.md` + `PROCESS.md`, creates the doc skeleton,
   commits it, tells you it's done.
4. **Greenfield vs. existing project:** if the repo already has real code (not just the fresh doc
   skeleton) or meaningful git history, the coordinator dispatches read-only repo-analysis agents
   before interviewing you, and commits the findings to `docs/coordination/repo-map.md` — see
   PROCESS.md's Phase 0.5. A genuinely empty/new repo skips straight to the interview.
5. The coordinator goes into the Concept interview: themed rounds, but **one question at a time**
   within each round, following `CLAUDE.md`'s Question protocol in full (context, reasoning,
   options with a recommendation, and a safe default if you don't answer). On an existing project,
   questions reference `repo-map.md` findings instead of asking from a blank slate. It should never
   dump a giant questionnaire on you.
6. Answer the concept questions across as many turns/sessions as needed. A dispatched agent
   synthesizes each round's answers into `docs/concept/` docs (the coordinator itself never does
   this), then the coordinator asks you to approve before moving to Objectives. From there it's
   Objectives → Plan (another user-approval gate) → Execute (fully autonomous, checkpoint pings
   only, with within-session watchdogs so it never silently stalls) → Validate → Iterate.

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

## License — MIT

See `LICENSE`.
