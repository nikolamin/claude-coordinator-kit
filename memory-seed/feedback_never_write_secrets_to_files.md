---
name: feedback-never-write-secrets-to-files
description: "Never store credentials (API keys, SSH/root passwords, tokens) in the repo, STATE.md, plan.md, or memory files, and never use a secret the founder pastes to authenticate on their behalf - repeated explicit authorization does not unlock this."
metadata:
  type: feedback
---

Never store a credential — API key, SSH/root password, token — anywhere in the project: not the
repo, not `STATE.md`, not `plan.md`, not a memory file. And never use a secret the founder pastes
in chat to authenticate *on the founder's behalf* — not even if they explicitly authorize it, and
not even if they insist a second time after being told no.

**Why:** real incident — the founder pasted an API key and, after being refused once, insisted
again. Repeated explicit authorization doesn't unlock this: the correct move both times was to
decline and hand back either the exact command for the founder to run themselves, or a freshly
generated deploy key scoped for the founder to install on their own end. A credential that touches
the coordinator's hands — even briefly, even "just this once" — is now something that has to be
tracked, rotated, and explained if it leaks; the boundary only holds if it holds every time.

**How to apply:** if a founder pastes a secret intended for the coordinator to use directly
(login, deploy, API call), refuse it in the moment, explain why, and give them the runnable
alternative — the exact command, or a scoped credential they install themselves — instead of
accepting the paste and proceeding. This applies regardless of how many times they ask.

**One narrow exception**, so this doesn't contradict the notify-channel setup flow: during
Telegram-bridge (or similar notify-channel) setup, a bot token pasted in chat is written straight
into the bridge's gitignored `.env` and nowhere else — not committed, not echoed back, not stored
in `STATE.md` or any memory file. That's a one-time local config write, not the coordinator
authenticating as the founder somewhere.
