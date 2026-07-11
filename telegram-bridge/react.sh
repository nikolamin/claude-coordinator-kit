#!/usr/bin/env bash
#
# react.sh - Set the final 👍/👎 reaction on a relayed Telegram message.
#
# Usage:
#   ./react.sh <message_id> <ok|fail>
#
# Companion to relay mode (RELAY_MODE=1 in .env): bot.py 👀-reacts and
# appends each incoming message to relay-inbox.jsonl; the live Claude Code
# session watching that file replies via notify.sh and then calls this
# script to replace the 👀 with a final 👍 (ok) or 👎 (fail) reaction.
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is.

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MESSAGE_ID="${1:-}"
RESULT="${2:-}"

if [[ -z "$MESSAGE_ID" || -z "$RESULT" ]]; then
  echo "Error: usage: $(basename "$0") <message_id> <ok|fail>" >&2
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

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "Error: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set in $ENV_FILE" >&2
  exit 1
fi

# Telegram's setMessageReaction takes `reaction` as a JSON array of reaction
# objects. --data-urlencode handles the URL-encoding of the JSON payload;
# single quotes around the JSON keep the inner double quotes literal.
REACTION_JSON='[{"type":"emoji","emoji":"'"$EMOJI"'"}]'

RESPONSE="$(curl --silent --show-error --fail \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
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
