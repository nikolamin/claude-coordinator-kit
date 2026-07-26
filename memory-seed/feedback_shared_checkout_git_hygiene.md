---
name: feedback-shared-checkout-git-hygiene
description: "In a shared (non-worktree) checkout, check git status before committing and commit only intended paths, check what's actually ahead of origin before pushing, and never run destructive git ops (checkout --, reset, clean) on a tree that may hold another agent's uncommitted work."
metadata:
  type: feedback
---

Three real incidents in one project, all from treating a shared working tree as if it were
exclusively owned by the current action.

**Why:**
1. A targeted `git add <file> && git commit` in a shared checkout swept in a concurrent agent's
   staged-but-uncommitted files under an unrelated commit message — `git add <file>` only names
   what's added to *this* commit, it doesn't limit what else is already staged.
2. A push meant to land one reviewed commit also pushed a second agent's in-flight, unreviewed
   commit along with it — caught only by inspecting `git log` afterward, not before.
3. A `git checkout --` intended to discard one file's changes destroyed a different agent's
   uncommitted work on that same tree — the file was only recovered by reconstructing it from that
   agent's transcript.

**How to apply:**
- Before any commit in a shared (non-worktree) checkout, run `git status` first and commit only
  the paths that are actually intended — don't assume the staging area or working tree reflects
  only your own change.
- Before any push, check what is actually ahead of origin (`git log origin/<branch>..`) and push
  only the reviewed/verified commit(s) — don't assume "my commit" is the only thing about to go
  out.
- Never run a destructive git operation (`checkout --`, `reset`, `clean`, or equivalent) on a tree
  that may hold another agent's uncommitted work.
- Inspecting or mutation-testing another agent's worktree is itself dispatched-agent work, not
  something the coordinator does directly — the coordinator's own git surface stays limited to
  performing an already-authorized commit/push plus the two read-only checks above (`git status`,
  `git log origin/<branch>..`). Any brief that dispatches an agent to inspect or mutation-test a
  worktree that might hold someone else's in-progress changes must require that agent to
  snapshot-commit the worktree first (even to a throwaway commit), so a destructive step during
  inspection can't lose work regardless of what happens next.
- This applies to every git operation touching a shared or another agent's tree — the incidents
  above included the coordinator itself running a destructive command; the fix is a rule that
  holds regardless of who's driving.
