---
name: feedback-never-dump-env-files
description: "Never print a credential file's contents (cat/head/tail/echo on .env or similar, local or remote) - transcripts persist on disk, so a printed secret is a leaked secret. Inspect variable names only; source the file and reference ${VAR} without expanding it to stdout."
metadata:
  type: feedback
---

Printing a credential file to see what's in it feels like an innocuous debugging step, but the
output doesn't disappear when the command finishes.

**Why:** a real incident — a build agent ran `cat .env` on a server while investigating a config
issue, which printed a live SMTP password and API key straight into its persisted transcript. Both
credentials had to be rotated afterward. The transcript isn't ephemeral like a terminal scrollback;
it's saved, and a secret that lands in it is compromised the moment it's written, whether or not
anyone reads the transcript later.

**How to apply:**
- Never print a credential file's contents — no `cat`, `head`, `tail`, `echo`, or equivalent on
  `.env` or similar files, whether local or on a remote host.
- To check what a credential file *contains* (as opposed to its values), inspect variable names
  only: `grep -o '^[A-Z_]*=' file` lists the keys without their values.
- To actually *use* a secret in a command, `source` the file and reference `${VAR}` — the shell
  expands it in-place for the command that needs it, without ever printing the expanded value to
  stdout or a log.
- This applies to every credential file, not just `.env` — the same rule covers SSH configs,
  cloud CLI credential files, and any other file holding live secrets.
