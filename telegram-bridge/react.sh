#!/usr/bin/env bash
#
# react.sh - Set the final 👍/👎 reaction on a relayed Telegram message.
#
# Usage:
#   ./react.sh [--chat <chat_id>] <message_id> <ok|fail>
#
# Companion to relay mode (RELAY_MODE=1 in .env): bot.py 👀-reacts and
# appends each incoming message to relay-inbox.jsonl; the live Claude Code
# session watching that file replies via notify.sh and then calls this
# script to replace the 👀 with a final 👍 (ok) or 👎 (fail) reaction.
#
# By default the reaction is set in TELEGRAM_CHAT_ID (the founder's private
# DM) - unchanged behavior. Pass --chat <chat_id> to react on a message in a
# different chat instead (e.g. a group chat_id from relay-inbox.jsonl's
# "chat_id" field for a group-relayed message) - this is what lets a
# coordinator session acknowledge group messages, not just founder DMs.
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is.

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CHAT_ID_OVERRIDE=""
if [[ "${1:-}" == "--chat" ]]; then
  CHAT_ID_OVERRIDE="${2:-}"
  if [[ -z "$CHAT_ID_OVERRIDE" ]]; then
    echo "Error: --chat requires a chat_id argument" >&2
    exit 1
  fi
  shift 2
fi

MESSAGE_ID="${1:-}"
RESULT="${2:-}"

if [[ -z "$MESSAGE_ID" || -z "$RESULT" ]]; then
  echo "Error: usage: $(basename "$0") [--chat <chat_id>] <message_id> <ok|fail>" >&2
  exit 1
fi

if ! [[ "$MESSAGE_ID" =~ ^[0-9]+$ ]]; then
  echo "Error: <message_id> must be a positive integer, got: $MESSAGE_ID" >&2
  exit 1
fi

case "$RESULT" in
  # Telegram's setMessageReaction only accepts a fixed, curated set of emoji
  # for `type: emoji` reactions (see the Bot API docs' ReactionTypeEmoji
  # list). ✅ and ❌ are NOT in that set and are rejected with 400
  # REACTION_INVALID, even though the request shape is otherwise correct.
  # 👍/👎 are the closest allowed equivalents.
  ok)   EMOJI="👍" ;;
  fail) EMOJI="👎" ;;
  *)
    echo "Error: second argument must be 'ok' or 'fail', got: $RESULT" >&2
    exit 1
    ;;
esac

ENV_FILE="$SCRIPT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env not found at $ENV_FILE" >&2
  echo "  Copy .env.example to .env and fill in TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID." >&2
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

if [[ -n "$CHAT_ID_OVERRIDE" ]]; then
  TARGET_CHAT_ID="$CHAT_ID_OVERRIDE"
elif [[ -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  TARGET_CHAT_ID="$TELEGRAM_CHAT_ID"
else
  echo "Error: TELEGRAM_CHAT_ID not set in $ENV_FILE (or pass --chat <chat_id>)" >&2
  exit 1
fi

# Telegram's setMessageReaction takes `reaction` as a JSON array of reaction
# objects. --data-urlencode handles the URL-encoding of the JSON payload;
# single quotes around the JSON keep the inner double quotes literal.
REACTION_JSON='[{"type":"emoji","emoji":"'"$EMOJI"'"}]'

RESPONSE="$(curl --silent --show-error --fail \
  --data-urlencode "chat_id=${TARGET_CHAT_ID}" \
  --data-urlencode "message_id=${MESSAGE_ID}" \
  --data-urlencode "reaction=${REACTION_JSON}" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMessageReaction")" || {
  echo "Error: curl request to Telegram API failed." >&2
  exit 1
}

# Telegram returns HTTP 200 with {"ok":false,...} for some error cases too,
# so check the body even when curl itself succeeded.
if ! grep -q '"ok":true' <<< "$RESPONSE"; then
  echo "Error: Telegram API returned an error response: $RESPONSE" >&2
  exit 1
fi

exit 0
