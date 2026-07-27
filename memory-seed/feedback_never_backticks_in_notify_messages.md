---
name: feedback-never-backticks-in-notify-messages
description: "Never put a backtick in a notify.sh message body - a double-quoted notify.sh '...' call is still a shell command line, so backtick-wrapped text triggers bash command substitution and can execute the embedded command instead of just displaying it. Describe commands in prose or point at a file in .coordinator-scratch/ instead."
metadata:
  type: feedback
---

A notify message that quotes a shell command for the founder's benefit looks harmless — until the
shell that's sending the notification reads it too.

**Why:** observed 3 times across sessions. `notify.sh "<message>"` is a normal double-quoted shell
argument, and double quotes do not suppress backtick command substitution. Backtick-wrapped
command text embedded in a notify message has actually **executed** twice — once running `scp`
plus `systemctl daemon-reload` against production, once running `nginx -t && systemctl reload
nginx` locally — and a third time it silently mangled the message instead of executing anything
dangerous. None of these were intended; the backticks were meant purely as inline-code formatting
for a human reader.

**How to apply:**
- Never put a backtick in a notify message body, full stop — not even for the common "inline code"
  formatting instinct.
- To reference a command in a notify message, describe it in prose ("ran the deploy script and
  reloaded nginx") instead of quoting it literally.
- If the literal command text genuinely needs to reach the founder, write it to a file in
  `.coordinator-scratch/` and reference the file's path in the notify message, rather than
  embedding it inline.
- This applies to every notify-style call built the same way (double-quoted shell string handed to
  a script) — not just this kit's specific `notify.sh`.
