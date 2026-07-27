# Updating an installed coordinator kit

**This file lives at the kit's root and is never installed into your project.** Fetch it the
same way you fetched `kickoff-prompt.md` — read it from the kit repo, or paste its contents into
chat. Don't expect to find it under `docs/coordination/` in an installed project.

**Do not re-run the install prompt to update an existing install.** It has no existence check on
most of what it copies: it overwrites `docs/coordination/STATE.md` with the empty template,
silently wiping the live phase, in-flight-agent tracking, durable decisions, and the whole agent
audit log. Follow this file instead.

## 1. Which version is installed

Check `docs/coordination/kit-version.md`. A current install's installer writes it in this exact
shape:

```
# Kit version

Installed from claude-coordinator-kit commit `<sha>` (`<YYYY-MM-DD>`).

- Telegram bridge: installed at `<BRIDGE_DIR>` | not installed
- Memory seed: installed at `~/.claude/projects/<slug>/memory/` | not installed

To update, follow the kit's `UPDATING.md` — do not re-run the install prompt.
```

**If the file is missing:** this project was installed before version stamping existed. You can
still update — you just have no recorded baseline commit to diff the kit's rule changes against,
so the `CLAUDE.md` step below (normally a clean diff) becomes a full read-and-reconcile: read the
installed `CLAUDE.md` and the fresh clone's `CLAUDE.md` in full, side by side, and manually work
out which differences are upstream rule changes versus this project's own customizations. That's
worse than having a baseline, but workable — treat it as a one-time cost, since finishing this
update writes `kit-version.md` and every update after this one gets the clean diff back.

## 2. Per-file update rules

Three classes apply to every file the kit ever puts on disk. **REPLACE**: kit-owned, safe to
overwrite with the fresh copy. **NEVER TOUCH**: grown live by this project; overwriting it
destroys real history or state. **MERGE**: customized at install time or filled in since; a
naive overwrite would erase that customization.

The classification below covers every file the kit's install process puts in place — copied
verbatim from the kit repo, or created in a kit-defined shape by the installer/Bootstrap (like
`kit-version.md`'s stamp or `.coordinator-scratch/`). It excludes everything a later phase
generates as project-specific content with no kit template — `docs/concept/`, `docs/objectives.md`,
`docs/plan.md`, `docs/decisions/`, `docs/validation/`, `docs/playbooks/` — an update never touches
those.

**`CLAUDE.md` (project root) — MERGE.** Holds resolved `<PROJECT>`/`<NOTIFY_CHANNEL>`/
`<BRIDGE_DIR>`, the filled-in Guardrails section, and any Phase 0.5 conventions merged in.

**`docs/coordination/PROCESS.md` — REPLACE.** Installed verbatim. Caveat: README invites editing
its `docs/concept/` sub-structure note per-project — diff before overwriting, don't blindly
clobber a deliberate edit there.

**`docs/coordination/STATE.md` — NEVER TOUCH.** Live phase, in-flight-agent tracking, durable
decisions, agent audit log — a copy over it destroys real history.

**`docs/coordination/codex-setup.md` — REPLACE.** Installed verbatim, no customization point.

**`docs/coordination/kit-version.md` — REPLACE, by the update itself.** Rewritten wholesale with
the new SHA/date at the end of every update — it's a stamp, not something to preserve across
versions.

**`.coordinator-scratch/` (project root) — NEVER TOUCH.** Working scratch space, gitignored; not
kit content, nothing to update.

**`memory-seed/*` → `~/.claude/projects/<slug>/memory/*.md` — MERGE.** Add new files, refresh
files unmodified since install, never overwrite one the coordinator has since edited. `MEMORY.md`
gains new index lines, never a wholesale replace (it also carries install-time
`<PROJECT>`/`<BRIDGE_DIR>` substitutions).

**`telegram-bridge/*.py`, `*.sh` — REPLACE.** `bot.py`, `notify.sh`, `react.sh`, `send-file.sh`,
`typing.sh`, `telegram_common.py`, `daily_report.py`, `email_monitor.py`, `get_chat_id.py`,
`process-media.sh` — kit-owned code, no per-install customization.

**`telegram-bridge/test_*.py` — REPLACE.** Kit-owned tests.

**`telegram-bridge/SETUP.md`, `EMAIL-MONITOR.md` — REPLACE.** Kit-owned docs.

**`telegram-bridge/*.template` — REPLACE.** All `.plist.template`/`.service.template`/
`.timer.template` files — kit-owned templates. Caveat: replacing the template does **not** touch
an already-installed `launchd`/`systemd` unit built from an older copy of it — see Bridge notes
below.

**`telegram-bridge/.env.example` — REPLACE.** Kit-owned template, never holds a real secret.

**`telegram-bridge/.gitignore` — REPLACE.** Kit-owned, lists the bridge's own runtime-state
exclusions.

**`telegram-bridge/.env` — NEVER TOUCH.** Live bot token, chat id, real config — a template copy
over it breaks the notify channel on the next poll cycle.

**`telegram-bridge/allowed-members.json` — NEVER TOUCH.** Hand-edited allowlist, deliberately
tracked (not gitignored) — not kit-generated content.

**Gitignored bridge runtime state — NEVER TOUCH.** `relay-inbox.jsonl`, `.offset.json` (and
`.tmp`), `.offset`, `.last_report` (and `.tmp`), `bridge-config.json` (and `.tmp`),
`seen-members.json` (and `.tmp`), `media-inbox/`, `models/`, `email-inbox.jsonl`,
`email-monitor-state.json` (and `.tmp`), any `*.log` — per `telegram-bridge/.gitignore`,
regenerated automatically, real data if it exists, nothing to install over.

Evidence used to build this classification:
- `README.md`'s guided-install step 3 and manual-install steps 2-4, 7 name exactly
  `CLAUDE.md` → project root, `PROCESS.md`/`STATE.md`/`codex-setup.md` → `docs/coordination/`,
  `memory-seed/*` → `~/.claude/projects/<slug>/memory/`, `telegram-bridge/` → a sibling location
  outside the project — this is the complete installed-file inventory.
- `git ls-files telegram-bridge/` lists the exact tracked files in that directory (28 files:
  `.env.example`, `.gitignore`, `SETUP.md`, `EMAIL-MONITOR.md`, `bot.py`, 8 service/plist
  templates, `daily_report.py`, `email_monitor.py`, `get_chat_id.py`, `notify.sh`,
  `process-media.sh`, `react.sh`, `send-file.sh`, `telegram_common.py`, 6 `test_*.py` files,
  `typing.sh`) — every one of them is REPLACE-class kit code/docs/templates, none carries
  per-install customization.
- `telegram-bridge/.gitignore` (read in full) lists the exact runtime-state filenames classified
  NEVER TOUCH above; `git status --short --ignored=matching telegram-bridge/` in this repo
  confirms `bot.log`, `daily_report.log`, and `relay-inbox.jsonl` are ignored-not-tracked exactly
  as the `.gitignore` says.
- `telegram-bridge/SETUP.md`'s Security section states `allowed-members.json` is "hand-edited
  config, not auto-generated runtime state, and is intentionally tracked (not gitignored)" —
  confirms it's real founder-maintained data, not a kit template, hence NEVER TOUCH rather than
  REPLACE despite being a tracked file in the bridge's own directory.
- `README.md` line ~188 explicitly invites editing `PROCESS.md`'s `docs/concept/` sub-structure
  note per-project — this is the one REPLACE-class file with a real diff-before-overwrite risk,
  confirmed by reading the note itself in `PROCESS.md`'s Knowledge base layout section.
- `git tag -l` returns nothing and `git log --oneline -- CLAUDE.md` shows `CLAUDE.md` present
  since the first commit (`75a0521`) — confirms the audit's "zero git tags, no version marker"
  claim and confirms a fresh clone's history reaches back far enough that
  `git show <sha>:CLAUDE.md` works for any commit a `kit-version.md` could ever record.

## 3. Update prompt (recommended)

Paste the block below as a message in a running coordinator session, in the project's root
directory. It is self-contained.

```
You're updating an already-installed coordinator kit in this project — not installing it fresh.
Do this in order. You are explicitly allowed to commit and push once the update is applied and
verified; never stop to ask permission for that specific commit/push.

1. Read `docs/coordination/kit-version.md`. If it does not exist, check
   `docs/coordination/STATE.md`: if STATE.md is missing entirely, or present but still just the
   template's "Phase: Bootstrap" stub with no real content, there is nothing installed to update —
   say so plainly and stop; that's the install prompt's job, not this one. Otherwise (STATE.md has
   real content but no kit-version.md) this is a pre-stamping install — proceed, but skip the
   pristine-diff shortcut below for CLAUDE.md and do the full read-and-reconcile instead, per
   UPDATING.md section 1.

2. Fetch the kit fresh into a scratch location:
   `git clone https://github.com/nikolamin/claude-coordinator-kit /tmp/coordinator-kit-update`
   This clone is a named, one-time exception to keeping writes inside the project — the same
   kind of one-time, install-approved, outside-the-project scratch as the install clone that
   `CLAUDE.md`'s Agent brief hygiene section exempts — remove it in step 8.

3. REPLACE-class files — overwrite directly from the fresh clone:
   - `docs/coordination/PROCESS.md`, `docs/coordination/codex-setup.md`.
     Exception: before overwriting PROCESS.md, diff the installed copy's `docs/concept/`
     sub-structure note (Knowledge base layout section) against the fresh clone's version — if
     they differ, this project customized that note; keep the customization, take the rest of the
     new file, don't silently clobber it.
   - If `telegram-bridge/` is installed (per kit-version.md, or ask if unrecorded): every
     `*.py`, `*.sh`, `test_*.py`, `*.template`, `.env.example`, `.gitignore`, `SETUP.md`,
     `EMAIL-MONITOR.md` in it, copied additively (file-by-file overwrite of these exact names,
     never a directory-level `rm -rf` + copy — that would take `.env` and all runtime state with
     it). Do NOT touch `.env`, `allowed-members.json`, or any gitignored runtime-state file listed
     in UPDATING.md section 2 (`relay-inbox.jsonl`, `.offset.json`, `.last_report`,
     `bridge-config.json`, `seen-members.json`, `media-inbox/`, `models/`, `email-inbox.jsonl`,
     `email-monitor-state.json`, any `*.log`) even if the fresh clone's versions differ in name or
     shape — these don't exist in the kit clone at all; they're only ever real if this install has
     generated them.
     If any `*.template` file actually changed, note in your final report that the
     already-installed `launchd`/`systemd` unit built from the old template is untouched by this —
     the founder (or a follow-up task) needs to re-copy and reload it manually if the change
     matters (new placeholder, new setting).

4. NEVER TOUCH — confirm you have not written to any of: `docs/coordination/STATE.md`,
   `.coordinator-scratch/`, `telegram-bridge/.env`, `telegram-bridge/allowed-members.json`, or any
   gitignored bridge runtime-state file named in step 3.

5. `memory-seed/*` (only if `~/.claude/projects/<slug>/memory/` exists — `<slug>` = this
   project's absolute path with every `/` replaced by `-`):
   - For each file the fresh clone's `memory-seed/` has and the installed memory directory
     lacks: copy it in as a new file.
   - For each file present in both: if you have a recorded baseline SHA (kit-version.md), compare
     the installed file against `git show <old-sha>:memory-seed/<name>` from the clone. Identical →
     safe to refresh with the fresh clone's current version. Different → the coordinator has
     edited it since install; leave it alone entirely, even if the kit's own version also changed.
     With no recorded baseline SHA, treat any file that looks meaningfully different from the
     fresh clone's version as possibly coordinator-edited and leave it alone rather than guessing.
   - For `MEMORY.md` specifically: never wholesale-replace it. Diff the old baseline's `MEMORY.md`
     (or, with no baseline, the fresh clone's current one) against the installed one to find lines
     that are new in the kit, and append only those as new index lines — keep every existing line,
     including the resolved `<PROJECT>`/`<BRIDGE_DIR>` substitutions already in the installed copy.

6. CLAUDE.md — this is the one file that changes this session's own operating rules, so it gets
   founder review, never a silent merge:
   - If `docs/coordination/kit-version.md` recorded an old SHA: run
     `git -C /tmp/coordinator-kit-update diff <old-sha> HEAD -- CLAUDE.md`. This isolates exactly
     what the kit's maintainers changed, independent of this project's own customizations (which
     sit on top of the old-SHA baseline, not inside this diff).
   - If that diff command fails (`fatal: bad revision`, exit 128 — the recorded SHA is
     unreachable, e.g. kit history was rewritten upstream since): treat it the same as no
     recorded SHA below — read both files in full and reconcile by hand instead of retrying.
   - With no recorded SHA (pre-stamping install, per step 1): there's no clean diff available —
     read the installed CLAUDE.md and the fresh clone's CLAUDE.md in full and work out the
     differences by hand instead.
   - Either way, show the founder the resulting rule changes in chat (not just a file write) and
     wait for explicit approval before touching CLAUDE.md at all.
   - Once approved, apply just those upstream changes on top of the currently-installed file,
     preserving every customization: the resolved `<PROJECT>`, `<NOTIFY_CHANNEL>`, `<BRIDGE_DIR>`
     values, the filled-in Guardrails section, a deleted Telegram subsection if no bridge is
     installed, and any Phase 0.5 project conventions merged in. If a kit rule change and a
     project customization touch the very same lines, flag the conflict to the founder instead of
     guessing which wins.
   - If the founder does not approve, or asks to defer: leave CLAUDE.md exactly as it is and say
     so in your final report — don't apply it partially.

7. Rewrite `docs/coordination/kit-version.md` with the fresh clone's current commit SHA and
   today's date, plus the current Telegram-bridge/memory-seed install status, in this exact shape:
   ```
   # Kit version

   Installed from claude-coordinator-kit commit `<sha>` (`<YYYY-MM-DD>`).

   - Telegram bridge: installed at `<BRIDGE_DIR>` | not installed
   - Memory seed: installed at `~/.claude/projects/<slug>/memory/` | not installed

   To update, follow the kit's `UPDATING.md` — do not re-run the install prompt.
   ```

8. Remove `/tmp/coordinator-kit-update` — the clone from step 2 is a named exception to keeping
   writes inside the project, but only for its own lifetime; it does not get to linger after this
   update finishes.

9. Report back: exactly what was REPLACEd, what MERGEd (and how, for CLAUDE.md and memory-seed),
   what you deliberately left untouched, and anything you couldn't reconcile automatically
   (a CLAUDE.md conflict, a coordinator-edited memory file the kit also changed, a changed
   template needing a manual service reload).

10. Tell the founder plainly, as the last line of your report: this session is still running under
    the OLD CLAUDE.md — Claude Code loaded it at session start and a file changed on disk mid-
    session does not change this session's own behavior. The new rules take effect only after the
    founder restarts the session (starts a fresh Claude Code session in this project). Say this
    even if CLAUDE.md wasn't approved/changed this run, so the founder never has to wonder.
```

## 4. If you'd rather do it by hand

The prompt above is the main path; this is the fallback for a founder who wants to drive the diff
themselves.

```bash
# Fresh clone for comparison
git clone https://github.com/nikolamin/claude-coordinator-kit /tmp/coordinator-kit-update

# What changed in the kit's rules since your install (needs kit-version.md's recorded sha)
OLD_SHA=$(grep -o 'commit `[a-f0-9]*`' docs/coordination/kit-version.md | grep -o '[a-f0-9]\{7,\}')
git -C /tmp/coordinator-kit-update diff "$OLD_SHA" HEAD -- CLAUDE.md

# REPLACE-class files: diff first, then copy if you're happy with the result
diff docs/coordination/PROCESS.md /tmp/coordinator-kit-update/PROCESS.md
cp /tmp/coordinator-kit-update/PROCESS.md docs/coordination/PROCESS.md
cp /tmp/coordinator-kit-update/codex-setup.md docs/coordination/codex-setup.md

# Bridge scripts/docs/templates (only the kit-owned names — never a directory-level copy)
IGNORE_RE='\.env$|allowed-members\.json$|relay-inbox\.jsonl$|\.offset|\.last_report'
IGNORE_RE="$IGNORE_RE"'|bridge-config\.json|seen-members\.json|media-inbox/?$|models/?$'
IGNORE_RE="$IGNORE_RE"'|email-inbox\.jsonl|email-monitor-state\.json|\.log$'
diff -q telegram-bridge/ /tmp/coordinator-kit-update/telegram-bridge/ \
  | grep -v -E "$IGNORE_RE"

# memory-seed (only if you seeded it) — same pristine-diff idea by hand
SLUG=$(pwd | sed 's/\//-/g')
diff /tmp/coordinator-kit-update/memory-seed/ "$HOME/.claude/projects/$SLUG/memory/"

# Clean up
rm -rf /tmp/coordinator-kit-update
```

Update `docs/coordination/kit-version.md` yourself afterward, in the pinned shape from section 1,
with the fresh clone's HEAD SHA and today's date. Then restart your Claude Code session — same
requirement as the prompt path, since the rules you just edited on disk don't apply retroactively
to the session that edited them.

## 5. Bridge-specific notes

The bridge is a machine-level service, typically running outside this project entirely, possibly
under `launchd` (macOS) or `systemd` (Linux). Per `telegram-bridge/SETUP.md`: *"Supervisor loop
(launchd on macOS, systemd on Linux) relaunches `bot.py` immediately after every exit — every poll
cycle is a fresh process, so `.env`/code edits on disk take effect on the very next cycle
automatically, no service restart needed."* That claim covers the code files (`bot.py`,
`telegram_common.py`, the other `.py`/`.sh` scripts) and `.env` — **the running service does not
need to be stopped** before those are replaced; the next poll cycle already picks up the new file.

That claim does **not** cover the `.template` files (`.plist.template`/`.service.template`/
`.timer.template`). Those are only ever read once, by hand, when the founder first copies one to
`~/Library/LaunchAgents/` or `~/.config/systemd/user/` and loads/enables it — updating the
template in `telegram-bridge/` has zero effect on the already-installed unit file until someone
manually re-copies it and reloads the service. If a template update matters (a new placeholder, a
changed setting), say so explicitly in the update's report instead of implying it took effect.

**Never do a directory-level replace of `telegram-bridge/`** (no "make destination match source,"
no `rm -rf telegram-bridge && cp -r` from the fresh clone) — that destroys `.env`,
`allowed-members.json`, and every piece of gitignored runtime state in one pass. Copy the named
REPLACE-class files individually instead; the update is additive by construction, never a mirror.
