#!/usr/bin/env bash
#
# ask.sh - Send the founder a question card with one button per option.
#
# Usage:
#   ./ask.sh "Which database?" "Postgres (recommended)" "SQLite" "Park this"
#   ./ask.sh --reply-to 1234 "Ship it?" "Yes" "Not yet"
#   ./ask.sh --clear <card_message_id>    # remove a card's buttons
#
# Prints the card's message_id on success. Thin wrapper around ask.py so the
# Unix and Windows (ask.ps1) entry points share one implementation - see
# ask.py's header for what bot.py does when a button is tapped.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Same interpreter choice as the service: the bridge's venv when SETUP.md (b)
# created one (requests may only be installed there), else python3 on PATH.
PYTHON="python3"
if [[ -x "$SCRIPT_DIR/venv/bin/python3" ]]; then
  PYTHON="$SCRIPT_DIR/venv/bin/python3"
fi
exec "$PYTHON" "$SCRIPT_DIR/ask.py" "$@"
