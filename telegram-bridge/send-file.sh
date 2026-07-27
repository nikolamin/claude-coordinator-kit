#!/usr/bin/env bash
#
# send-file.sh - Deliver a file to the founder over Telegram from any shell
# session or hook, picking the right Bot API method from the file's
# extension so it arrives usefully on the phone instead of always landing
# as a flat, unpreviewable document:
#
#   .jpg .jpeg .png .webp               -> sendPhoto      (inline image;
#                                          over Telegram's ~10MB photo
#                                          limit, falls back to
#                                          sendDocument instead of a
#                                          confusing API error)
#   .gif                                 -> sendAnimation  (looping, as
#                                          Telegram expects for a GIF)
#   .mp4 .mov .mkv .webm .m4v .avi .3gp  -> sendVideo      (inline player)
#   everything else                      -> sendDocument   (pdf, xlsx,
#                                          docx, csv, md, txt, zip, logs, ...)
#
# Usage:
#   ./send-file.sh <path> [caption]
#
# This replaces the hand-rolled `curl .../sendDocument` recipe SETUP.md used
# to document for file delivery - that recipe meant the coordinator itself
# had to source .env and compose a raw Bot API call, which collides with
# rules against investigative curl/handling credential files directly.
# Calling this script instead keeps that entirely out of the coordinator's
# own hands.
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is - same resolution as notify.sh.
#
# Unconfigured-bridge contract: same as notify.sh/react.sh - if .env is
# missing, or TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID aren't set, this script
# exits 1 with a clear error. A vanished status ping or file delivery is a
# worse failure than a loud one, so all four standalone scripts in this
# directory agree on this exit code.
#
# Real failures (bad usage, missing/unreadable file, over Telegram's ~50MB
# bot-upload cap, an actual Telegram API error) also exit 1 with a clear
# message.
#
# Testing hook (no live token/network involved): the extension -> Bot API
# method routing below is factored into resolve_send_method(), a pure
# function with no I/O. This script guards its own top-level body with
# `[[ "${BASH_SOURCE[0]}" == "${0}" ]]` so it can be `source`d (e.g. by
# test_send_file.py) to call resolve_send_method() directly with synthetic
# inputs, without that source triggering argument parsing, .env access, or
# any network call. This is the one departure from this directory's
# existing bash scripts' flat, no-functions style - done specifically so
# the routing logic can be unit-tested offline, the same "pure decision
# function, tested in isolation" pattern telegram_common.py already uses in
# Python for evaluate_incoming_message()/is_bot_mentioned().

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Telegram Bot API limits (see https://core.telegram.org/bots/api#sendphoto
# and the general file-upload note): sendPhoto caps a photo at ~10MB before
# it must go through sendDocument instead; the Bot API overall refuses any
# bot upload over ~50MB regardless of method.
PHOTO_MAX_BYTES=$((10 * 1024 * 1024))
UPLOAD_MAX_BYTES=$((50 * 1024 * 1024))

# resolve_send_method: pure, no I/O. Given a lowercase file extension (no
# leading dot) and a file size in bytes, prints "<METHOD> <FIELD>" - the
# Bot API method and multipart form field name this file should be sent
# with. See the file header for why this is a standalone function.
resolve_send_method() {
  local ext="$1" bytes="$2"
  case "$ext" in
    jpg|jpeg|png|webp)
      if (( bytes > PHOTO_MAX_BYTES )); then
        echo "sendDocument document"
      else
        echo "sendPhoto photo"
      fi
      ;;
    gif)
      echo "sendAnimation animation"
      ;;
    mp4|mov|mkv|webm|m4v|avi|3gp)
      echo "sendVideo video"
      ;;
    *)
      echo "sendDocument document"
      ;;
  esac
}

# Only run the script body below when executed directly - not when
# `source`d for testing (see the file header's "Testing hook" note).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

FILE_PATH="${1:-}"
CAPTION="${2:-}"

if [[ -z "$FILE_PATH" ]]; then
  echo "Error: usage: $(basename "$0") <path> [caption]" >&2
  echo "  A file path is required as the first argument." >&2
  exit 1
fi

if [[ ! -e "$FILE_PATH" ]]; then
  echo "Error: file not found: $FILE_PATH" >&2
  exit 1
fi

if [[ ! -f "$FILE_PATH" ]]; then
  echo "Error: not a regular file: $FILE_PATH" >&2
  exit 1
fi

if [[ ! -r "$FILE_PATH" ]]; then
  echo "Error: file not readable: $FILE_PATH" >&2
  exit 1
fi

# stat's flag differs between BSD/macOS (-f%z) and GNU/Linux (-c%s) - try
# both, same fallback pattern process-media.sh's ffmpeg/whisper-cli lookup
# uses for cross-platform binary names.
BYTES="$(stat -f%z "$FILE_PATH" 2>/dev/null || stat -c%s "$FILE_PATH" 2>/dev/null || echo "-1")"
if [[ "$BYTES" -lt 0 ]]; then
  echo "Error: could not determine the size of $FILE_PATH" >&2
  exit 1
fi

if (( BYTES > UPLOAD_MAX_BYTES )); then
  echo "Error: $FILE_PATH is ${BYTES} bytes - over Telegram's ~50MB bot-upload cap. Not sent." >&2
  echo "  Split it into smaller pieces, or transfer it to the founder's device directly." >&2
  exit 1
fi

EXT="${FILE_PATH##*.}"
if [[ "$EXT" == "$FILE_PATH" ]]; then
  EXT_LOWER=""  # no '.' in the filename at all
else
  EXT_LOWER="$(echo "$EXT" | tr '[:upper:]' '[:lower:]')"
fi

read -r METHOD FIELD <<< "$(resolve_send_method "$EXT_LOWER" "$BYTES")"

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

# --form-string (not -F) for chat_id/caption: never let a caption starting
# with '@' or '<' be read as a file reference or an stdin redirect by
# curl's own -F/-@ parsing. The file itself is quoted (@"...") so a path
# containing a space or semicolon can't be misparsed either.
CURL_ARGS=(--silent --show-error --fail --max-time 300
  --form-string "chat_id=${TARGET_CHAT_ID}")
if [[ -n "$CAPTION" ]]; then
  CURL_ARGS+=(--form-string "caption=${CAPTION}")
fi
CURL_ARGS+=(-F "${FIELD}=@\"${FILE_PATH}\"")

RESPONSE="$(curl "${CURL_ARGS[@]}" "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${METHOD}")" || {
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

fi
