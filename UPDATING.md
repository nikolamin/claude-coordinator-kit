# Updating an installed coordinator kit

**This file lives at the kit's root and is never installed into your project.** Fetch it the
same way you fetched `kickoff-prompt.md` — read it from the kit repo, or paste its contents into
chat. Don't expect to find it under `docs/coordination/` in an installed project.

**This file is not the update procedure.** The procedure is `FILE-COPY-INSTALL.md`'s `## Updating`
section: re-run the install prompt, and its own existence guard detects an already-installed
project and switches to update mode instead of re-copying files wholesale. This file is the
per-file reference that update mode reads when a divergence needs reconciling by hand — which of
the three classes below (REPLACE / NEVER TOUCH / MERGE) a given file falls into and why — plus a
manual by-hand fallback (section 3) for a founder who wants to drive an update without an agent at
all.

## 1. Which version is installed

Check `docs/coordination/kit-version.md`. A current install's installer writes it in this exact
shape:

```
# Kit version

Installed from claude-coordinator-kit commit `<sha>` (`<YYYY-MM-DD>`).

- Telegram bridge: installed at `<BRIDGE_DIR>` | not installed
- Memory seed: installed at `~/.claude/projects/<slug>/memory/` | not installed

To update, paste this install prompt again — its step 2 detects the existing install and
switches to the update branch (see FILE-COPY-INSTALL.md's Updating section).
```

**If the file is missing:** this is a **pre-stamp install, version unknown** — not evidence that
nothing is installed, and never treated as a fresh/greenfield project. (FILE-COPY-INSTALL.md's own
install-prompt guard covers this: a missing `kit-version.md` alone never authorizes running the
install prompt — it also checks whether `docs/coordination/STATE.md` already has real content,
which is what actually catches a pre-stamp existing install.) You can still update — you just have
no recorded baseline commit to diff the kit's files against, for either `CLAUDE.md` or any
REPLACE-class file (see section 2) — so two things change:

- The `CLAUDE.md` merge (normally a clean diff against the recorded baseline) becomes a full
  read-and-reconcile: read the installed `CLAUDE.md` and the fresh clone's `CLAUDE.md` in full,
  side by side, and manually work out which differences are upstream rule changes versus this
  project's own customizations.
- Every REPLACE-class file's diff-before-overwrite check (section 2) loses its exact baseline
  too. Reconstruct an effective baseline instead of skipping the check: walk the kit
  repo's own commit history for that file (`git -C /tmp/coordinator-kit-update log --oneline --
  <path>`) and find the version whose content matches what's actually installed. If one matches,
  use it as the baseline for that file's diff. If none matches closely — the file has clearly
  diverged from every commit the kit ever shipped — treat it as diverged with unknown baseline and
  go straight to the reconciliation path (never guess "close enough, overwrite it").

That's worse than having a recorded baseline, but workable — treat it as a one-time cost. Once this
update finishes, it writes `kit-version.md` with the fresh clone's current SHA, and explicitly notes
that the pre-update baseline was reconstructed by diffing rather than read from a stamp (so a future
update knows this history is approximate, not a hard guarantee) — every update after this one gets
the clean, exact-SHA diff back.

## 2. Per-file update rules

Three classes apply to every file the kit ever puts on disk. **REPLACE**: kit-owned by design — no
per-install customization point — but "by design" is not "guaranteed unmodified": before overwriting
any REPLACE-class file, the update flow diffs the installed copy against the kit content it was
actually installed from (the SHA recorded in `kit-version.md`, or the reconstructed baseline from
section 1 for a pre-stamp install). Identical → the overwrite is genuinely safe, do it. Diverged →
someone patched the live file directly, outside the kit's own update flow — do NOT blind-overwrite.
Reconcile instead: show the founder the diff for that file and ask whether it's a real fix or
customization worth keeping. If yes, leave the installed file exactly as-is (fix intact) and open a
follow-up task to backport it upstream into the kit repo itself — never fold the backport into the
same update. If no (stale, superseded, or the founder says drop it), overwrite with the fresh
clone's version, but say explicitly in the update's report that a real local change was
intentionally dropped and why. Either way, record the file, a one-line description of the
divergence, and the decision in `kit-version.md`'s `## Notes` section (see that file's bullet
below). This applies to every file below marked REPLACE, not just a few of them — the risk is
generic (anyone can hand-edit any file on disk at any time), it just bites hardest on
`telegram-bridge/*`, which commonly runs as a machine-level service maintained directly on the
deployed copy, entirely outside this project's own git history, so nothing else would ever catch a
local fix there. **NEVER TOUCH**: grown live by this project; overwriting it destroys real history
or state. **MERGE**: customized at install time or filled in since; a naive overwrite would erase
that customization.

The classification below covers every file the kit's install process puts in place — copied
verbatim from the kit repo, or created in a kit-defined shape by the installer/Bootstrap (like
`kit-version.md`'s stamp or `.coordinator-scratch/`). It excludes everything a later phase
generates as project-specific content with no kit template — `docs/concept/`, `docs/objectives.md`,
`docs/plan.md`, `docs/decisions/`, `docs/validation/`, `docs/playbooks/` — an update never touches
those.

**`CLAUDE.md` (project root) — MERGE.** Holds resolved `<PROJECT>`/`<NOTIFY_CHANNEL>`/
`<BRIDGE_DIR>`, the filled-in Guardrails section, and any Phase 0.5 conventions merged in.

**`docs/coordination/PROCESS.md` — REPLACE, diff-verified first (see above).** Installed verbatim
by design. One named exception on top of the general diff-first check above: diffed against the
same single baseline as every other REPLACE-class file (the recorded old SHA, or the reconstructed
baseline for a pre-stamp install — never the fresh clone's HEAD), if that diff is exactly one hunk
and it's the `docs/concept/` sub-structure note (Knowledge base layout section)
FILE-COPY-INSTALL.md invites editing per-project, that's the invited customization, not an
unexpected divergence — keep the note, take the rest of the new file (apply the fresh clone's
version, then reapply just the note). Any broader divergence, even one that also includes that
hunk, is a real divergence and goes through the general reconciliation path above instead.

**`docs/coordination/STATE.md` — NEVER TOUCH.** Live phase, in-flight-agent tracking, durable
decisions, agent audit log — a copy over it destroys real history.

**`docs/coordination/codex-setup.md` — REPLACE, diff-verified first (see above).** Installed
verbatim by design, no per-project customization point — but it lives in the same project git
history as `PROCESS.md`, so this one is realistically low-risk; the check still runs, it just
rarely finds anything.

**`docs/coordination/kit-version.md` — REPLACE, by the update itself.** The fixed-shape SHA/date
stamp fields are rewritten wholesale at the end of every update — that part isn't something to
preserve across versions. The `## Notes` section below it is different: carry forward every entry
still relevant (a REPLACE-class divergence not yet resolved, a memory-seed conflict not yet
re-raised — see the two bullets above and below), append this update's own new entries after, and
only drop an entry once it's actually resolved — never wholesale-erase the section, since a later
update relies on reading a still-relevant entry rather than re-discovering or re-asking it from
scratch.

**`.coordinator-scratch/` (project root) — NEVER TOUCH.** Working scratch space, gitignored; not
kit content, nothing to update.

**`memory-seed/*` → `~/.claude/projects/<slug>/memory/*.md` — MERGE.** Add new files, refresh
files unmodified since install, never overwrite one the coordinator has since edited. `MEMORY.md`
gains new index lines, never a wholesale replace (it also carries install-time
`<PROJECT>`/`<BRIDGE_DIR>` substitutions). "Add new files" is not unconditional: a new kit seed can
assert a rule that contradicts an existing local memory file under a different filename — the field
incident that surfaced this was a new kit seed on standing authorization to act on the founder's
behalf landing next to a local file asserting the opposite (an account-creation boundary), leaving
contradictory doctrine loaded together with no signal they disagreed. A new kit seed gets a content
conflict check against every existing local memory file, not just same-named ones, before it's
installed: read the new seed's actual content, skim every file already in the installed memory
directory (not just similarly-named ones) for a rule that asserts the opposite, and if one is
found, don't install silently — surface both files to the founder with a one-line stance for each
and ask them to pick: adopt the kit's rule (delete the local file, install the seed as-is), keep
the local override (skip the new seed), or keep both deliberately (rare — only when they genuinely
coexist). Record whichever they pick in `kit-version.md`'s `## Notes` section (see the bullet
above) so a future update doesn't re-ask the same resolved question.

**`telegram-bridge/*.py`, `*.sh` (excluding `test_*.py`, its own bullet below) — REPLACE,
diff-verified first — this is the highest-risk file group for divergence.** Run `git ls-files
telegram-bridge/ | grep -E '\.(py|sh)$' | grep -v '^telegram-bridge/test_'` for the current list
(`bot.py`, `notify.sh`, `telegram_common.py`, and the rest — the exact names are incidental, a new
script added here inherits this same classification) — kit-owned code by design, no per-install
customization point *intended*. In practice the bridge typically runs as a machine-level service
maintained directly on its deployed copy (a "sibling location outside this project," per
FILE-COPY-INSTALL.md) rather than through this project's own git — so a real production hotfix
(e.g. an IMAP timeout fix applied after a live outage) can land directly on the installed file with
zero trace anywhere except a content diff. Never assume "kit-owned" means "definitely still
identical to the kit" for these files; always run the diff-first check (see the reconciliation
recipe above) and treat a divergence as a signal to reconcile, not a stale diff to ignore.

**`telegram-bridge/test_*.py` — REPLACE, diff-verified first (see above).** Kit-owned tests — same
divergence risk as the code they cover, if someone extended a test alongside a local code fix.

**`telegram-bridge/SETUP.md`, `EMAIL-MONITOR.md` — REPLACE, diff-verified first (see above).**
Kit-owned docs, same "lives outside this project's git" risk as the bridge code.

**`telegram-bridge/*.template` — REPLACE, diff-verified first (see above).** All
`.plist.template`/`.service.template`/`.timer.template` files — kit-owned templates. Caveat:
replacing the template does **not** touch
an already-installed `launchd`/`systemd` unit built from an older copy of it — see Bridge notes
below.

**`telegram-bridge/.env.example` — REPLACE, diff-verified first (see above).** Kit-owned template,
never holds a real secret — but a locally-added variable comment (e.g. documenting a locally-added
`IMAP_PORT`) is still a real local edit worth not silently dropping.

**`telegram-bridge/.gitignore` — REPLACE, diff-verified first (see above).** Kit-owned, lists the
bridge's own runtime-state exclusions — a locally-added exclusion line is a real local edit too.

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
- `FILE-COPY-INSTALL.md`'s guided-install step 3 and manual-install steps 2-4, 7 name exactly
  `CLAUDE.md` → project root, `PROCESS.md`/`STATE.md`/`codex-setup.md` → `docs/coordination/`,
  `memory-seed/*` → `~/.claude/projects/<slug>/memory/`, `telegram-bridge/` → a sibling location
  outside the project — this is the complete installed-file inventory.
- `git ls-files telegram-bridge/` lists the exact tracked files in that directory — run it for the
  current count rather than trusting a number here, since a commit can add or remove one at any
  time (`git ls-files telegram-bridge/ | wc -l` for the total, `git ls-files telegram-bridge/ |
  grep -c 'test_.*\.py'` for the test-file share) — every one of them is REPLACE-class kit
  code/docs/templates with no per-install customization *point by design*. That's a design intent,
  not a runtime guarantee: a real field update caught this directory diverged from its recorded kit
  version (a production IMAP timeout fix landed directly on an installed `email_monitor.py`, since
  the bridge typically runs outside this project's own git tracking) — a blind REPLACE would have
  reverted a live fix and re-broken it. Hence the diff-first check above applies to every file in
  this list, not just the ones that happen to carry obvious customization hooks. Adding a new
  bridge file means updating its classification in this section in the same commit — a command can
  tell you a file exists, never which of the three classes it belongs in.
- `telegram-bridge/.gitignore` (read in full) lists the exact runtime-state filenames classified
  NEVER TOUCH above; `git status --short --ignored=matching telegram-bridge/` in this repo
  confirms `bot.log`, `daily_report.log`, and `relay-inbox.jsonl` are ignored-not-tracked exactly
  as the `.gitignore` says.
- `telegram-bridge/SETUP.md`'s Security section states `allowed-members.json` is "hand-edited
  config, not auto-generated runtime state, and is intentionally tracked (not gitignored)" —
  confirms it's real founder-maintained data, not a kit template, hence NEVER TOUCH rather than
  REPLACE despite being a tracked file in the bridge's own directory.
- `FILE-COPY-INSTALL.md`'s "Manual install" section, step 7, explicitly invites editing
  `PROCESS.md`'s `docs/concept/` sub-structure note per-project — confirmed by reading the note
  itself in `PROCESS.md`'s Knowledge base layout section. This is a deliberate, invited
  customization on top of the generic diff-first check every REPLACE-class file now gets, not a
  special case that check depends on. (Cited by section name, not line number — a line reference
  rots the moment either file gets an unrelated edit above it.)
- `git tag -l` returns nothing and `git log --oneline -- CLAUDE.md` shows `CLAUDE.md` present
  since the first commit (`75a0521`) — confirms the audit's "zero git tags, no version marker"
  claim and confirms a fresh clone's history reaches back far enough that
  `git show <sha>:CLAUDE.md` works for any commit a `kit-version.md` could ever record.

## 3. If you'd rather do it by hand

The main path is re-running the install prompt (FILE-COPY-INSTALL.md's `## Updating` section) and
letting it drive an update in an agent session. This section is the fallback for a founder who
wants to drive the diff themselves, without an agent — the mechanics below are the same
reconciliation logic section 2 describes, just as a script instead of prose.

This script assumes `bash` or `zsh`. **If you're on zsh (the default macOS shell), variable braces
are load-bearing, not style** — `$VAR:something` is parsed as a history-expansion modifier (`:P`,
`:t`, `:c`, etc.) and silently mangles the value instead of producing `VAR`'s value followed by a
literal colon. Every variable reference below is braced (`${VAR}`) for exactly this reason; if you
adapt this script, keep bracing every `${VAR}` that's ever followed by `:`, not just the ones shown
here.

```bash
# Fresh clone for comparison
git clone https://github.com/nikolamin/claude-coordinator-kit /tmp/coordinator-kit-update

# What changed in the kit's rules since your install (needs kit-version.md's recorded sha)
OLD_SHA=$(grep -o 'commit `[a-f0-9]*`' docs/coordination/kit-version.md | grep -o '[a-f0-9]\{7,\}')
git -C /tmp/coordinator-kit-update diff "${OLD_SHA}" HEAD -- CLAUDE.md

# REPLACE-class files: diff against the version YOU installed (${OLD_SHA}), not against the fresh
# clone's HEAD — diffing against HEAD only tells you the kit changed, not whether your installed
# copy diverged from it. Only cp when that diff actually came back clean; never cp unconditionally
# on the strength of the comment above it — a diverged local fix must survive this script even if
# you don't read every line of output.
if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:PROCESS.md" | diff -q - docs/coordination/PROCESS.md >/dev/null; then
  cp /tmp/coordinator-kit-update/PROCESS.md docs/coordination/PROCESS.md
else
  # Before treating this as a real divergence: if the ONLY difference is the docs/concept
  # sub-structure note (Knowledge base layout section) that FILE-COPY-INSTALL.md invites editing
  # per-project, that's the invited customization, not an unexpected one — keep your note, take
  # the rest of the new file by hand instead of a straight cp. Any other difference is a real
  # divergence — reconcile per section 2 above (show yourself the diff, decide
  # keep-local/backport vs. drop) before touching the file.
  echo "DIVERGED - do not overwrite, see section 2 above: docs/coordination/PROCESS.md"
fi
if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:codex-setup.md" | diff -q - docs/coordination/codex-setup.md >/dev/null; then
  cp /tmp/coordinator-kit-update/codex-setup.md docs/coordination/codex-setup.md
else
  echo "DIVERGED - do not overwrite, see section 2 above: docs/coordination/codex-setup.md"
fi

# Bridge scripts/docs/templates: same divergence-first idea, per file (only the kit-owned names —
# never a directory-level copy). This directory is the highest-risk one for a real local hotfix,
# since the bridge commonly runs outside this project's own git tracking — do NOT skip straight to
# copying just because the names match.
#
# BRIDGE_DIR is the bridge's actual install location, a sibling directory OUTSIDE this project
# (see FILE-COPY-INSTALL.md's install steps) — NOT a path inside this repo. Set it to the same
# absolute path recorded in kit-version.md's "Telegram bridge: installed at <BRIDGE_DIR>" line
# before running this block.
# Skip this whole block entirely if you didn't install the bridge. Diffing telegram-bridge/<name>
# against a path inside the project (instead of inside BRIDGE_DIR) compares against a file that was
# never installed there in the first place — every file reports DIVERGED, and the suggested cp would
# create a phantom in-project copy the bridge never reads.
BRIDGE_DIR="/absolute/path/to/your/telegram-bridge"   # <-- set this to your real install path first
if [ -z "${BRIDGE_DIR:-}" ] || [ ! -d "${BRIDGE_DIR}" ]; then
  echo "BRIDGE_DIR is not set to an existing directory - set it above before running this block. Skipping bridge files." >&2
else
  IGNORE_RE='\.env$|allowed-members\.json$|relay-inbox\.jsonl$|\.offset|\.last_report'
  IGNORE_RE="${IGNORE_RE}"'|bridge-config\.json|seen-members\.json|media-inbox/?$|models/?$'
  IGNORE_RE="${IGNORE_RE}"'|email-inbox\.jsonl|email-monitor-state\.json|\.log$'
  for f in $(git -C /tmp/coordinator-kit-update ls-tree -r --name-only HEAD -- telegram-bridge/ \
               | grep -v -E "${IGNORE_RE}"); do
    # ${f} is kit-repo-relative, e.g. "telegram-bridge/bot.py" - strip the leading directory to get
    # its real path inside BRIDGE_DIR.
    rel="${f#telegram-bridge/}"
    installed="${BRIDGE_DIR}/${rel}"
    if [ ! -f "${installed}" ]; then
      echo "not yet installed (new in this kit version, or BRIDGE_DIR is wrong): ${rel}"
      continue
    fi
    if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:${f}" >/dev/null 2>&1; then
      if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:${f}" | diff -q - "${installed}" >/dev/null; then
        cp "/tmp/coordinator-kit-update/${f}" "${installed}"
      else
        echo "DIVERGED, reconcile by hand before overwriting (see section 2 above): ${rel}"
      fi
    else
      echo "no ${OLD_SHA} copy of ${rel} in the kit repo — treat as diverged/unknown baseline: ${rel}"
    fi
  done
fi
# For each file reported DIVERGED above: read the diff, decide whether to keep the local change (and
# backport it upstream to the kit as its own task) or drop it — never blind-overwrite it.

# memory-seed (only if you seeded it): same per-file, diff-against-baseline idea as above, not one
# directory-level diff against the clone's HEAD — a directory diff conflates "kit seed you don't
# have yet" with "shared file that needs to be checked against the version YOU installed," and
# silently skips the coordinator-edited-since-install check section 2's memory-seed rules require.
SLUG=$(pwd | sed 's/\//-/g')
MEMDIR="$HOME/.claude/projects/${SLUG}/memory"
for f in $(git -C /tmp/coordinator-kit-update ls-tree -r --name-only HEAD -- memory-seed/ | sed 's#^memory-seed/##'); do
  installed="${MEMDIR}/${f}"
  if [ "${f}" = "MEMORY.md" ]; then
    echo "MEMORY.md: never wholesale-replace - diff the old baseline's MEMORY.md (or, with no baseline, the fresh clone's current one) against the installed one, append only the new-in-the-kit lines as index lines, keep every existing line. Skip the index line for any seed you decide below not to install."
    continue
  fi
  if [ ! -f "${installed}" ]; then
    echo "NEW kit seed, not yet installed: ${f} — before copying it in, this needs a "\
"content/doctrine check, not a diff: read ${f}'s actual content, then skim every file "\
"already in ${MEMDIR} (not just similarly-named ones) for a rule that contradicts it. Found "\
"a conflict? Don't copy it in silently — pick adopt-the-kit's-rule / "\
"keep-the-local-override / keep-both-deliberately (rare) and record the decision in "\
"kit-version.md's Notes section so a later update doesn't re-ask. See section 2's "\
"memory-seed rules above for the full procedure."
    continue
  fi
  if [ -n "${OLD_SHA:-}" ] && git -C /tmp/coordinator-kit-update show "${OLD_SHA}:memory-seed/${f}" >/dev/null 2>&1; then
    if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:memory-seed/${f}" | diff -q - "${installed}" >/dev/null; then
      cp "/tmp/coordinator-kit-update/memory-seed/${f}" "${installed}"
    else
      echo "coordinator-edited since install, leaving alone even if the kit's own version also changed: ${f}"
    fi
  else
    echo "no baseline for ${f} (pre-stamp install, or file predates your recorded SHA) — treat as possibly coordinator-edited and leave it alone rather than guessing: ${f}"
  fi
done

# Clean up
rm -rf /tmp/coordinator-kit-update
```

If `OLD_SHA` comes up empty (pre-stamp install, version unknown — see section 1), there's no exact
baseline to diff against: for each REPLACE-class file, walk
`git -C /tmp/coordinator-kit-update log --oneline -- <path>` to find a historical version matching
what's installed and diff against that instead; if nothing matches, treat the file as diverged with
unknown baseline and reconcile it by hand rather than guessing it's safe to overwrite.

Update `docs/coordination/kit-version.md` yourself afterward, in the pinned shape from section 1,
with the fresh clone's HEAD SHA and today's date — same `## Notes` carry-forward rule described in
section 2's `kit-version.md` bullet above, if you reconstructed the baseline or left any file
diverged pending an upstream backport. Then restart your Claude Code session — the rules you just
edited on disk don't apply retroactively to the session that edited them.

## 4. Bridge-specific notes

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
