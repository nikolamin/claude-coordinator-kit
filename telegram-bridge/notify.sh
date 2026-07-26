#!/usr/bin/env bash
#
# notify.sh - Ping your phone via Telegram from any shell session or hook.
#
# Usage:
#   ./notify.sh "some message"                 # send to the founder's DM (default, unchanged)
#   ./notify.sh --group "some message"          # send to the auto-discovered group chat
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is.
#
# --group reads the group chat id from bridge-config.json's
# "active_group_chat_id" (next to this script), auto-populated by bot.py
# the first time it observes a message in a group it's a member of - no
# manual setup step. See SETUP.md "Group chat support".

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET="dm"
if [[ "${1:-}" == "--group" ]]; then
  TARGET="group"
  shift
fi

MESSAGE="${1:-}"

if [[ -z "$MESSAGE" ]]; then
  echo "Error: usage: $(basename "$0") [--group] \"<message>\"" >&2
  echo "  A non-empty message is required as the first argument." >&2
  exit 1
fi

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

TARGET_CHAT_ID="$TELEGRAM_CHAT_ID"

if [[ "$TARGET" == "group" ]]; then
  BRIDGE_CONFIG_FILE="$SCRIPT_DIR/bridge-config.json"
  if [[ ! -f "$BRIDGE_CONFIG_FILE" ]]; then
    echo "Error: no group chat known yet ($BRIDGE_CONFIG_FILE not found)." >&2
    echo "  Add the bot to the group and send any message that mentions it first - bot.py auto-discovers the group chat id." >&2
    exit 1
  fi
  TARGET_CHAT_ID="$(python3 -c '
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
chat_id = data.get("active_group_chat_id")
if chat_id is None:
    sys.exit(1)
print(chat_id)
' "$BRIDGE_CONFIG_FILE")" || {
    echo "Error: bridge-config.json has no active_group_chat_id yet - group not discovered." >&2
    exit 1
  }
fi

RESPONSE="$(curl --silent --show-error --fail \
  --data-urlencode "chat_id=${TARGET_CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}" \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage")" || {
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
