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

**If the file is missing:** this is a **pre-stamp install, version unknown** — not evidence that
nothing is installed, and never treated as a fresh/greenfield project. (README's own install-prompt
guard covers this: a missing `kit-version.md` alone never authorizes running the install prompt —
it also checks whether `docs/coordination/STATE.md` already has real content, which is what
actually catches a pre-stamp existing install.) You can still update — you just have no recorded
baseline commit to diff the kit's files against, for either `CLAUDE.md` or any REPLACE-class file
(see section 2) — so two things change:

- The `CLAUDE.md` step below (normally a clean diff) becomes a full read-and-reconcile: read the
  installed `CLAUDE.md` and the fresh clone's `CLAUDE.md` in full, side by side, and manually work
  out which differences are upstream rule changes versus this project's own customizations.
- Every REPLACE-class file's diff-before-overwrite check (section 2, section 3 step 3) loses its
  exact baseline too. Reconstruct an effective baseline instead of skipping the check: walk the kit
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
someone patched the live file directly, outside the kit's own update flow — do NOT blind-overwrite;
reconcile explicitly instead (see section 3 step 3 for the full procedure). This applies to every
file below marked REPLACE, not just a few of them — the risk is generic (anyone can hand-edit any
file on disk at any time), it just bites hardest on `telegram-bridge/*`, which commonly runs as a
machine-level service maintained directly on the deployed copy, entirely outside this project's own
git history, so nothing else would ever catch a local fix there. **NEVER TOUCH**: grown live by this
project; overwriting it destroys real history or state. **MERGE**: customized at install time or
filled in since; a naive overwrite would erase that customization.

The classification below covers every file the kit's install process puts in place — copied
verbatim from the kit repo, or created in a kit-defined shape by the installer/Bootstrap (like
`kit-version.md`'s stamp or `.coordinator-scratch/`). It excludes everything a later phase
generates as project-specific content with no kit template — `docs/concept/`, `docs/objectives.md`,
`docs/plan.md`, `docs/decisions/`, `docs/validation/`, `docs/playbooks/` — an update never touches
those.

**`CLAUDE.md` (project root) — MERGE.** Holds resolved `<PROJECT>`/`<NOTIFY_CHANNEL>`/
`<BRIDGE_DIR>`, the filled-in Guardrails section, and any Phase 0.5 conventions merged in.

**`docs/coordination/PROCESS.md` — REPLACE, diff-verified first (see above).** Installed verbatim
by design. Additional caveat on top of the general diff-first check, mirroring section 3 step (c):
diffed against the same single baseline as every other REPLACE-class file (the recorded old SHA, or
the reconstructed baseline for a pre-stamp install — never the fresh clone's HEAD), the exception
applies only when that diff is exactly one hunk and it's the `docs/concept/` sub-structure note
(Knowledge base layout section) README invites editing per-project — keep the note, take the rest
of the new file. Any broader divergence, even one that also includes that hunk, is a real
divergence and goes through the general reconciliation path instead.

**`docs/coordination/STATE.md` — NEVER TOUCH.** Live phase, in-flight-agent tracking, durable
decisions, agent audit log — a copy over it destroys real history.

**`docs/coordination/codex-setup.md` — REPLACE, diff-verified first (see above).** Installed
verbatim by design, no per-project customization point — but it lives in the same project git
history as `PROCESS.md`, so this one is realistically low-risk; the check still runs, it just
rarely finds anything.

**`docs/coordination/kit-version.md` — REPLACE, by the update itself.** The fixed-shape SHA/date
stamp fields are rewritten wholesale at the end of every update — that part isn't something to
preserve across versions. The `## Notes` section below it is different: it's carried forward per
step 7's rules, never wholesale-erased, since a later update relies on reading a still-relevant
entry (an unresolved REPLACE-class divergence, an unresolved memory-seed conflict) rather than
re-discovering or re-asking it from scratch.

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
installed — see section 3 step 5 for the full procedure and the founder-decision options.

**`telegram-bridge/*.py`, `*.sh` — REPLACE, diff-verified first — this is the highest-risk file
group for divergence.** `bot.py`, `notify.sh`, `react.sh`, `send-file.sh`, `typing.sh`,
`telegram_common.py`, `daily_report.py`, `email_monitor.py`, `get_chat_id.py`, `process-media.sh` —
kit-owned code by design, no per-install customization point *intended*. In practice the bridge
typically runs as a machine-level service maintained directly on its deployed copy (a "sibling
location outside this project," per README) rather than through this project's own git — so a real
production hotfix (e.g. an IMAP timeout fix applied after a live outage) can land directly on the
installed file with zero trace anywhere except a content diff. Never assume "kit-owned" means
"definitely still identical to the kit" for these files; always run the diff-first check (section 3
step 3) and treat a divergence as a signal to reconcile, not a stale diff to ignore.

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
- `README.md`'s guided-install step 3 and manual-install steps 2-4, 7 name exactly
  `CLAUDE.md` → project root, `PROCESS.md`/`STATE.md`/`codex-setup.md` → `docs/coordination/`,
  `memory-seed/*` → `~/.claude/projects/<slug>/memory/`, `telegram-bridge/` → a sibling location
  outside the project — this is the complete installed-file inventory.
- `git ls-files telegram-bridge/` lists the exact tracked files in that directory (28 files:
  `.env.example`, `.gitignore`, `SETUP.md`, `EMAIL-MONITOR.md`, `bot.py`, 8 service/plist
  templates, `daily_report.py`, `email_monitor.py`, `get_chat_id.py`, `notify.sh`,
  `process-media.sh`, `react.sh`, `send-file.sh`, `telegram_common.py`, 6 `test_*.py` files,
  `typing.sh`) — every one of them is REPLACE-class kit code/docs/templates with no per-install
  customization *point by design*. That's a design intent, not a runtime guarantee: a real field
  update caught this directory diverged from its recorded kit version (a production IMAP timeout
  fix landed directly on an installed `email_monitor.py`, since the bridge typically runs outside
  this project's own git tracking) — a blind REPLACE would have reverted a live fix and re-broken
  it. Hence the diff-first check in section 2/3 applies to every file in this list, not just the
  ones that happen to carry obvious customization hooks.
- `telegram-bridge/.gitignore` (read in full) lists the exact runtime-state filenames classified
  NEVER TOUCH above; `git status --short --ignored=matching telegram-bridge/` in this repo
  confirms `bot.log`, `daily_report.log`, and `relay-inbox.jsonl` are ignored-not-tracked exactly
  as the `.gitignore` says.
- `telegram-bridge/SETUP.md`'s Security section states `allowed-members.json` is "hand-edited
  config, not auto-generated runtime state, and is intentionally tracked (not gitignored)" —
  confirms it's real founder-maintained data, not a kit template, hence NEVER TOUCH rather than
  REPLACE despite being a tracked file in the bridge's own directory.
- `README.md`'s "Manual install" section, step 7, explicitly invites editing `PROCESS.md`'s
  `docs/concept/` sub-structure note per-project — confirmed by reading the note itself in
  `PROCESS.md`'s Knowledge base layout section. This is a deliberate, invited customization on top
  of the generic diff-first check every REPLACE-class file now gets, not a special case that check
  depends on. (Cited by section name, not line number — a line reference rots the moment either
  file gets an unrelated edit above it.)
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
   real content but no kit-version.md) this is a **pre-stamp install, version unknown** — treat it
   as an existing install exactly like a stamped one (never as fresh, never route it back to the
   install prompt), and proceed with the rest of this update. Two things change without a recorded
   SHA, per UPDATING.md section 1:
   - Skip the pristine-diff shortcut for CLAUDE.md in step 6 below and do the full read-and-
     reconcile instead.
   - In step 3's REPLACE-class diff-first check, there's no exact baseline to diff against either.
     Reconstruct one per file by walking the kit repo's commit history
     (`git -C /tmp/coordinator-kit-update log --oneline -- <path>`) for the version whose content
     matches what's installed now; if none matches, treat that file as diverged-with-unknown-
     baseline and go straight to step 3's reconciliation path for it, don't guess.
   Note in your final report (step 9) that the baseline was reconstructed rather than read from a
   stamp, and step 7 records that explicitly in the new `kit-version.md` too.

2. Fetch the kit fresh into a scratch location:
   `git clone https://github.com/nikolamin/claude-coordinator-kit /tmp/coordinator-kit-update`
   This clone is a named, one-time exception to keeping writes inside the project — the same
   kind of one-time, install-approved, outside-the-project scratch as the install clone that
   `CLAUDE.md`'s Agent brief hygiene section exempts — remove it in step 8.

3. REPLACE-class files — **diff before every overwrite, no exceptions.** A REPLACE classification
   means "kit-owned by design," not "guaranteed unmodified" — the only way to know an installed
   copy hasn't organically diverged (most commonly a hotfix applied directly to a live/deployed
   file, completely outside this project's own git tracking) is to actually diff it against the
   version it was installed from before touching it. This is not optional for any file in the list
   below, even ones that look like "obviously nobody would hand-edit this."

   The full list: `docs/coordination/PROCESS.md`, `docs/coordination/codex-setup.md`, and — if
   `telegram-bridge/` is installed (per kit-version.md, or ask if unrecorded) — every `*.py`,
   `*.sh`, `test_*.py`, `*.template`, `.env.example`, `.gitignore`, `SETUP.md`, `EMAIL-MONITOR.md`
   under it.

   For each file:
   a. Determine the baseline: if kit-version.md recorded a SHA, get the kit's installed-time
      content with `git -C /tmp/coordinator-kit-update show <old-sha>:<path-in-kit-repo>`. If there
      is no recorded SHA (pre-stamp install, per step 1), reconstruct the baseline by walking that
      file's history in the kit clone instead — see step 1 above. This is the one and only baseline
      used for this file's diff below, for every file including `PROCESS.md` — (c)'s exception
      never switches to a different comparison (e.g. the fresh clone's HEAD); it only changes how a
      divergence against this same baseline gets handled.
   b. Diff the installed file against that baseline from (a).
      - **Identical:** unmodified since install — safe to overwrite with the fresh clone's current
        (HEAD) version. Do it.
      - **Diverged:** don't stop at pass/fail — actually inspect the diff output before deciding how
        to reconcile. Precedence, evaluated in this order:
        1. **`docs/coordination/PROCESS.md`, and the diff's only hunk is the `docs/concept/`
           sub-structure note (Knowledge base layout section)** that README invites editing
           per-project: this is (c) below, not the general path — go there directly.
        2. **Everything else** — `PROCESS.md` diverging in any other hunk (alone or alongside the
           note), or any other REPLACE-class file diverging at all: do NOT overwrite. Reconcile
           explicitly instead of guessing:
           i.   Show the founder the diff for that specific file and ask whether it's a real fix or
                customization worth keeping.
           ii.  If yes: this becomes its own follow-up task — backport the local fix upstream into
                the kit repo itself (a separate change to the kit's own repo, not part of this
                update). Leave the installed file exactly as-is, with its local fix intact, until
                that backport lands in the kit and a clean, verified new version is ready to come
                back down as a future update. Do not fold the backport into this update's commit.
           iii. If no (the divergence is stale, superseded, or the founder says drop it): overwrite
                with the fresh clone's version like the identical case, but say explicitly in the
                report that a real local change was intentionally dropped, and why.
           iv.  Either way, record the file, a one-line description of the divergence, and the
                decision in this update's final report (step 9) and in the `kit-version.md` stamp
                written in step 7.
   c. **`PROCESS.md`'s docs/concept exception** — reached only via (b)'s precedence rule 1 above,
      i.e. only when the diff against the *same baseline from (a)* shows exactly one hunk and it's
      the Knowledge base layout section's per-project note: that's the invited customization, not
      an unexpected divergence — keep the note, and take the rest of the new file (merge by hand:
      apply the fresh clone's HEAD version, then reapply just the note). Any divergence broader than
      that one hunk is never eligible for this shortcut, even if the note itself is also part of
      what changed — it goes through (b)'s general path instead.
   d. If any `*.template` file clears the check and actually changes, note in your final report
      that the already-installed `launchd`/`systemd` unit built from the old template is untouched
      by this — the founder (or a follow-up task) needs to re-copy and reload it manually if the
      change matters (new placeholder, new setting).

   Regardless of the above: never a directory-level `rm -rf` + copy for `telegram-bridge/` — only
   ever a named-file, one-at-a-time overwrite, and only once that specific file clears the
   diff-first check in (b). Do NOT touch `.env`, `allowed-members.json`, or any gitignored
   runtime-state file listed in UPDATING.md section 2 (`relay-inbox.jsonl`, `.offset.json`,
   `.last_report`, `bridge-config.json`, `seen-members.json`, `media-inbox/`, `models/`,
   `email-inbox.jsonl`, `email-monitor-state.json`, any `*.log`) even if the fresh clone's versions
   differ in name or shape — these don't exist in the kit clone at all; they're only ever real if
   this install has generated them.

4. NEVER TOUCH — confirm you have not written to any of: `docs/coordination/STATE.md`,
   `.coordinator-scratch/`, `telegram-bridge/.env`, `telegram-bridge/allowed-members.json`, or any
   gitignored bridge runtime-state file named in step 3.

5. `memory-seed/*` (only if `~/.claude/projects/<slug>/memory/` exists — `<slug>` = this
   project's absolute path with every `/` replaced by `-`):
   - **Before doing anything else in this step, read the currently-installed `kit-version.md`'s
     `## Notes` section (if any)** for a prior memory-seed conflict resolution. A conflict this step
     would otherwise raise may already be a decided question — a prior (b) skip or (c) keep-both
     recorded there is not re-asked from scratch. The one exception: if the specific kit seed's
     content has changed since that prior decision (compare it against the version referenced by the
     old recorded SHA, the same baseline check used elsewhere in this step), the old decision was
     made against a different file — treat it as unresolved and raise it fresh rather than assuming
     the stale answer still applies.
   - For each file the fresh clone's `memory-seed/` has and the installed memory directory
     lacks: **before copying it in, check for a doctrine conflict, not just a name collision.**
     A brand-new kit seed can assert a rule that contradicts a file the founder/coordinator already
     has in the installed memory directory *under a different filename* — same-named-file diffing
     (the next bullet) never catches this, because there's no same name to diff. Read the new kit
     seed's actual content, then skim the description/content of every file already in the
     installed memory directory (not just ones with a matching or similar name) for a rule that
     asserts the opposite. This is a semantic check, not a filename or hash comparison — a
     mechanical diff cannot find it.
     - No conflicting file found: copy the new kit seed in as normal.
     - A conflicting file is found: do NOT install the new kit seed silently — installing it next
       to an unrelated-looking local file leaves both in the memory directory with no signal they
       disagree, so a future session loads contradictory doctrine with no way to tell which one is
       authoritative. Instead, surface the pair to the founder: name both files, give a one-line
       summary of each one's stance/rule, and ask which of these three the founder wants:
       a. **Adopt the kit's rule** — delete the local file, install the new kit seed as-is.
       b. **Keep the local override** — do not install the new kit seed; the local file stands.
       c. **Keep both, deliberately** — rare; only on an explicit founder call that the two really
          do coexist (e.g. one is scoped narrower than the other). Install the kit seed alongside
          the local file.
       Whichever the founder picks, record the decision — which two files, one-line stance each,
       and the outcome — in this update's final report (step 9) and in the `kit-version.md` Notes
       section from step 7, the same place a REPLACE-class divergence gets recorded. A skip (b) or
       a deliberate keep-both (c) is exactly the kind of decision a future update needs to know
       about, so it doesn't ask the same question again from scratch.
   - For each file present in both: if you have a recorded baseline SHA (kit-version.md), compare
     the installed file against `git show <old-sha>:memory-seed/<name>` from the clone. Identical →
     safe to refresh with the fresh clone's current version. Different → the coordinator has
     edited it since install; leave it alone entirely, even if the kit's own version also changed.
     With no recorded baseline SHA, reconstruct one the same way section 3 step 3(a) does for
     REPLACE-class files — walk the kit repo's own history for `memory-seed/<name>` to find the
     version matching what's installed, and diff against that, never against the fresh clone's
     current HEAD. If nothing in that history matches, treat the file as diverged-with-unknown-
     baseline and leave it alone rather than guessing.
   - For `MEMORY.md` specifically: never wholesale-replace it. Diff the old baseline's `MEMORY.md`
     (or, with no baseline, the fresh clone's current one) against the installed one to find lines
     that are new in the kit, and append only those as new index lines — keep every existing line,
     including the resolved `<PROJECT>`/`<BRIDGE_DIR>` substitutions already in the installed copy.
     Skip the index line for any kit seed that step 5's conflict check resolved as (b) skip — an
     index line pointing at a file that was deliberately not installed is worse than no line at
     all. A (c) keep-both resolution gets an index line same as any other installed file.

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
   This step **rewrites the fixed shape above wholesale, but the `## Notes` section below it is
   carried forward, not erased** — a future update relies on reading a still-relevant Notes entry
   (per step 5's carry-forward check above), and a wholesale rewrite that silently drops it would
   defeat that. Build the new `## Notes` section as: every entry from the *existing*
   `kit-version.md`'s `## Notes` (if it has one) that is still relevant, plus this update's own new
   entries appended after. Omit the whole section only if the carried-forward list and this
   update's new entries are both empty.
   - Carrying forward: a prior REPLACE-class divergence entry stays if that file is still diverged
     right now (this update left it in place again, or the file wasn't touched this update at all)
     — drop it once the divergence is actually resolved (the backport landed in the kit and this
     update pulled the merged version down, or the founder chose to overwrite the local change). A
     prior memory-seed conflict entry stays as long as both files (the kit seed and the local
     override) still exist and step 5 didn't re-raise it as changed — drop it once step 5 resolves
     it fresh (that produces a new entry below, superseding the old one). A prior "baseline was
     reconstructed" entry (section 1) is one-time only — this update is what writes a real SHA into
     the file, so don't carry that specific entry into the rewritten file.
   - This update's own new entries:
     - If step 1 found no prior `kit-version.md` (pre-stamp install): a line saying the pre-update
       baseline was reconstructed by diffing installed files against kit commit history, not read
       from a prior stamp.
     - For every file step 3 found diverged from its baseline this update: one line per file naming
       it, a one-phrase description of the divergence, and the decision made (kept in place pending
       upstream backport / intentionally overwritten and why).
     - For every memory-seed doctrine conflict step 5 found or re-raised this update: one line
       naming the kit seed and the conflicting local file, a one-phrase stance for each, and the
       founder's decision (adopted the kit's rule / kept the local override, kit seed skipped /
       kept both deliberately). A future update reads this (per step 5's carry-forward check) to
       avoid re-asking the same resolved question.

8. Remove `/tmp/coordinator-kit-update` — the clone from step 2 is a named exception to keeping
   writes inside the project, but only for its own lifetime; it does not get to linger after this
   update finishes.

9. Report back: exactly what was REPLACEd (and, for each, that the diff-first check in step 3
   passed clean), what MERGEd (and how, for CLAUDE.md and memory-seed), what you deliberately left
   untouched, every file step 3 found diverged from its baseline with the decision made on each
   (kept pending upstream backport, or intentionally overwritten and why), every memory-seed
   doctrine conflict step 5 found with the founder's decision on each, whether step 1's baseline
   was reconstructed rather than read from a stamp, and anything you couldn't reconcile
   automatically (a CLAUDE.md conflict, a coordinator-edited memory file the kit also changed, a
   changed template needing a manual service reload).

10. Tell the founder plainly, as the last line of your report: this session is still running under
    the OLD CLAUDE.md — Claude Code loaded it at session start and a file changed on disk mid-
    session does not change this session's own behavior. The new rules take effect only after the
    founder restarts the session (starts a fresh Claude Code session in this project). Say this
    even if CLAUDE.md wasn't approved/changed this run, so the founder never has to wonder.
```

## 4. If you'd rather do it by hand

The prompt above is the main path; this is the fallback for a founder who wants to drive the diff
themselves.

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
  # sub-structure note (Knowledge base layout section) that README invites editing per-project,
  # that's the invited customization, not an unexpected one — keep your note, take the rest of the
  # new file by hand instead of a straight cp. Any other difference is a real divergence — reconcile
  # per section 3 step 3 (show yourself the diff, decide keep-local/backport vs. drop) before
  # touching the file.
  echo "DIVERGED - do not overwrite, see section 3 step 3: docs/coordination/PROCESS.md"
fi
if git -C /tmp/coordinator-kit-update show "${OLD_SHA}:codex-setup.md" | diff -q - docs/coordination/codex-setup.md >/dev/null; then
  cp /tmp/coordinator-kit-update/codex-setup.md docs/coordination/codex-setup.md
else
  echo "DIVERGED - do not overwrite, see section 3 step 3: docs/coordination/codex-setup.md"
fi

# Bridge scripts/docs/templates: same divergence-first idea, per file (only the kit-owned names —
# never a directory-level copy). This directory is the highest-risk one for a real local hotfix,
# since the bridge commonly runs outside this project's own git tracking — do NOT skip straight to
# copying just because the names match.
#
# BRIDGE_DIR is the bridge's actual install location, a sibling directory OUTSIDE this project (see
# README's install steps) — NOT a path inside this repo. Set it to the same absolute path recorded
# in kit-version.md's "Telegram bridge: installed at <BRIDGE_DIR>" line before running this block.
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
        echo "DIVERGED, reconcile by hand before overwriting (see section 3 step 3): ${rel}"
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
# silently skips the coordinator-edited-since-install check section 3 step 5 requires.
SLUG=$(pwd | sed 's/\//-/g')
MEMDIR="$HOME/.claude/projects/${SLUG}/memory"
for f in $(git -C /tmp/coordinator-kit-update ls-tree -r --name-only HEAD -- memory-seed/ | sed 's#^memory-seed/##'); do
  installed="${MEMDIR}/${f}"
  if [ "${f}" = "MEMORY.md" ]; then
    echo "MEMORY.md: never wholesale-replace - diff the old baseline's MEMORY.md (or, with no baseline, the fresh clone's current one) against the installed one, append only the new-in-the-kit lines as index lines, keep every existing line. Skip the index line for any seed you decide below not to install."
    continue
  fi
  if [ ! -f "${installed}" ]; then
    echo "NEW kit seed, not yet installed: ${f} — before copying it in, this needs a content/doctrine check, not a diff: read ${f}'s actual content, then skim every file already in ${MEMDIR} (not just similarly-named ones) for a rule that contradicts it. Found a conflict? Don't copy it in silently — pick adopt-the-kit's-rule / keep-the-local-override / keep-both-deliberately (rare) and record the decision in kit-version.md's Notes (section 3 step 7's shape) so a later update doesn't re-ask. See section 3 step 5 for the full procedure."
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
with the fresh clone's HEAD SHA and today's date — same `## Notes` addition as the prompt path's
step 7 if you reconstructed the baseline or left any file diverged pending an upstream backport.
Then restart your Claude Code session — same requirement as the prompt path, since the rules you
just edited on disk don't apply retroactively to the session that edited them.

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
