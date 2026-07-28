#!/usr/bin/env bash
#
# register-commands.sh - Register this bot's slash-command menu with Telegram.
#
# Usage:
#   ./register-commands.sh            # merge the commands below into the bot's menu
#   ./register-commands.sh --list     # print the currently registered menu, change nothing
#
# What this is FOR: the command menu is discoverability only - the little
# list Telegram shows next to the paperclip when you type "/" on your phone.
# It does NOT change how messages are handled. In RELAY_MODE, bot.py relays
# every text message verbatim into relay-inbox.jsonl, slash commands
# included (see relay_message() and handle_message()'s relay_mode branch) -
# so a registered command is just a typing shortcut for text the live
# coordinator session was already going to receive.
#
# THE KIT SHIPS AN EMPTY MENU. The COMMANDS array below is deliberately all
# comments: which commands make sense is a per-project question, so each
# project fills in its own (see the sample line). With the array empty this
# script is a safe no-op that only reports the currently registered menu.
#
# IDEMPOTENT AND ADDITIVE: reads the existing menu via getMyCommands first
# and merges, so re-running never drops a command some other setup step
# registered, and running it twice is a no-op. A command listed below whose
# description changed is updated in place.
#
# Reads TELEGRAM_BOT_TOKEN from a .env file located next to this script (NOT
# the caller's cwd), same convention as notify.sh / react.sh / send-file.sh,
# so it is safe to call from any shell session or project directory.
#
# The token is never printed: it is only ever interpolated into the curl URL
# argument, and no command here echoes that URL. Note that curl's own error
# output can contain the URL, so failures are reported by this script's own
# message rather than by dumping curl's verbose output.

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# The commands this bridge registers. One "name|description" per line.
# Telegram rules: name is lowercase a-z, 0-9 and underscores, 1-32 chars;
# description is 1-256 chars. Add a line here to add a command to the menu.
#
# Empty by default - this is the per-project slot. Uncomment the sample below
# (or write your own) to publish a menu; a command only needs to exist here to
# show up in the phone's "/" list, because relay mode hands the text straight
# to the live coordinator session and nothing else has to know about it.
#
# Sample (from the project this bridge was extracted from - a command that
# relays to a coordinator session running a project-local Claude Code skill):
#   "personas|Run a persona beta-test round on this project"
# ---------------------------------------------------------------------------
COMMANDS=(
  # "yourcommand|What your project's coordinator does when it sees this"
)

LIST_ONLY=0
if [[ "${1:-}" == "--list" ]]; then
  LIST_ONLY=1
  shift
fi

ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env not found at $ENV_FILE" >&2
  echo "  Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "Error: TELEGRAM_BOT_TOKEN not set in $ENV_FILE" >&2
  exit 1
fi

EXISTING="$(curl --silent --show-error --fail \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMyCommands")" || {
  echo "Error: getMyCommands request to the Telegram API failed." >&2
  exit 1
}

if ! grep -q '"ok":true' <<< "$EXISTING"; then
  echo "Error: getMyCommands returned an error response: $EXISTING" >&2
  exit 1
fi

if [[ "$LIST_ONLY" -eq 1 ]]; then
  echo "$EXISTING"
  exit 0
fi

# An empty COMMANDS array is the shipped default, and it is a legitimate
# state, not an error: this bridge simply has no commands of its own to
# publish yet. Stop before the merge - "${COMMANDS[@]}" on an empty array is
# an unbound-variable error under `set -u` in bash 3.2 (still the /bin/bash
# on macOS), and because the merge is purely additive an empty list could
# never change the menu anyway.
if [[ "${#COMMANDS[@]}" -eq 0 ]]; then
  echo "No commands defined in this script's COMMANDS array; nothing to register."
  echo "  Add a \"name|description\" line to COMMANDS in $0 to publish one."
  echo "Currently registered menu:"
  echo "$EXISTING"
  exit 0
fi

# Merge: start from whatever is already registered, then add/update ours.
# Order is preserved (existing commands first, in their existing order), so a
# re-run never reshuffles the founder's menu.
MERGED="$(python3 -c '
import json, sys

existing_raw = sys.argv[1]
wanted = []
for spec in sys.argv[2:]:
    name, _, desc = spec.partition("|")
    wanted.append({"command": name, "description": desc})

existing = json.loads(existing_raw).get("result", [])
merged = [dict(c) for c in existing]
by_name = {c.get("command"): c for c in merged}

for cmd in wanted:
    if cmd["command"] in by_name:
        by_name[cmd["command"]]["description"] = cmd["description"]
    else:
        merged.append(cmd)
        by_name[cmd["command"]] = cmd

print(json.dumps(merged, ensure_ascii=False))
' "$EXISTING" "${COMMANDS[@]}")"

if [[ "$MERGED" == "$(python3 -c '
import json, sys
print(json.dumps(json.loads(sys.argv[1]).get("result", []), ensure_ascii=False))
' "$EXISTING")" ]]; then
  echo "Command menu already up to date; nothing to do."
  echo "$EXISTING"
  exit 0
fi

RESPONSE="$(curl --silent --show-error --fail \
  --data-urlencode "commands=${MERGED}" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands")" || {
  echo "Error: setMyCommands request to the Telegram API failed." >&2
  exit 1
}

# Telegram returns HTTP 200 with {"ok":false,...} for some error cases too,
# so check the body even when curl itself succeeded.
if ! grep -q '"ok":true' <<< "$RESPONSE"; then
  echo "Error: Telegram API returned an error response: $RESPONSE" >&2
  exit 1
fi

# Read the menu back so the caller sees what is actually registered now
# (this response carries no secrets - safe to print and paste).
VERIFY="$(curl --silent --show-error --fail \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMyCommands")" || {
  echo "Error: verification getMyCommands request failed (the set itself succeeded)." >&2
  exit 1
}

echo "Command menu registered. getMyCommands now returns:"
echo "$VERIFY"

exit 0
