#!/usr/bin/env bash
#
# notify.sh - Ping your phone via Telegram from any shell session or hook.
#
# Usage:
#   ./notify.sh "some message"
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is.

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MESSAGE="${1:-}"

if [[ -z "$MESSAGE" ]]; then
  echo "Error: usage: $(basename "$0") \"<message>\"" >&2
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

RESPONSE="$(curl --silent --show-error --fail \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
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
