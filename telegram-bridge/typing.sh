#!/usr/bin/env bash
#
# typing.sh - Post Telegram's "typing..." chat action so the founder sees
# the coordinator is actively working on a reply, not silence.
#
# Usage:
#   ./typing.sh              # one-shot sendChatAction (Telegram auto-expires
#                             # it client-side after ~5s)
#   ./typing.sh <seconds>     # keep-alive: re-sends every ~4s for <seconds>
#                             # seconds, then stops on its own. Runs as a
#                             # detached background job with its own
#                             # stdout/stderr redirected to /dev/null, so
#                             # this script itself returns immediately no
#                             # matter how the caller invokes it - including
#                             # `typing.sh 30 | cat` or `out="$(typing.sh
#                             # 30)"`, which would otherwise block the
#                             # caller for the full duration (a pipe/command-
#                             # substitution reader waits for EOF, i.e. for
#                             # every process holding the write end open to
#                             # close it, and a naive `&` background job
#                             # keeps that write end open by inheriting it).
#                             # The caller never has to clean anything up
#                             # either way (no PID to track, no process left
#                             # running once <seconds> elapses).
#
# Why this exists: bot.py's TypingIndicator (see run_claude_with_typing() in
# bot.py) only fires around the classic-mode `claude -p` subprocess call. In
# RELAY_MODE - the mode SETUP.md steers a coordinator setup toward - a
# relayed message only ever gets the initial 👀 reaction from bot.py; there
# is no periodic "still working" signal while the live coordinator session
# is composing its reply, which can be a long silent wait on a slow turn.
# Call this script as soon as a relayed message is picked up, before
# starting work on the reply (see SETUP.md section (g)/(j)).
#
# Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from a .env file located
# next to this script (NOT the caller's cwd), so it is safe to call from
# any other shell session, project, or Claude Code hook regardless of
# where that caller's working directory is - same resolution as notify.sh.
#
# Unconfigured-bridge contract: same as notify.sh/react.sh/send-file.sh - a
# missing .env or missing TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID exits 1 with a
# clear error. A missing typing signal is a worse failure than a loud one,
# so all four standalone scripts in this directory agree on this exit code.

set -euo pipefail

# Resolve the directory this script lives in, regardless of caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DURATION="${1:-0}"

if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
  echo "Error: usage: $(basename "$0") [seconds]" >&2
  echo "  <seconds>, if given, must be a non-negative integer." >&2
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

# send_typing_once: fires exactly one sendChatAction "typing" call. Returns
# non-zero on any curl failure or a {"ok":false,...} response body - same
# two-stage check (curl exit code, then response body) notify.sh/react.sh
# use, factored into a function here only because it's called twice below
# (once for the one-shot path, repeatedly for the keep-alive loop).
send_typing_once() {
  local response
  response="$(curl --silent --show-error --fail --max-time 10 \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "action=typing" \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendChatAction")" || return 1
  grep -q '"ok":true' <<< "$response"
}

if [[ "$DURATION" -le 0 ]]; then
  if ! send_typing_once; then
    echo "Error: curl request to Telegram API failed, or Telegram API returned an error response." >&2
    exit 1
  fi
  exit 0
fi

# Keep-alive: re-send every ~4s (TYPING_INTERVAL_SECONDS in bot.py uses the
# same interval, since Telegram's typing indicator lasts ~5s client-side)
# for DURATION seconds, in a detached background subshell, then return
# immediately so the caller is never blocked.
#
# `disown` removes the subshell from this shell's job table so it's never
# reported or waited-on and won't be killed by this shell exiting - but the
# loop still ends on its own after DURATION seconds regardless, so nothing
# is ever left running indefinitely; there is no PID for the caller to
# track or clean up. Best-effort: a single failed ping (`|| true`) never
# aborts the rest of the keep-alive loop, matching bot.py's own
# TypingIndicator, which logs and swallows the same kind of failure.
#
# `>/dev/null 2>&1` on the subshell itself (not on this script's own
# earlier output) is required, not cosmetic: without it, the subshell
# inherits this script's stdout/stderr file descriptors, including a pipe
# or command-substitution fd a caller may have put there. A pipe reader
# (`| cat`) or command substitution (`$(...)`) blocks until every process
# holding the write end open closes it - `&` backgrounding this script's
# own shell doesn't release that fd, so the subshell silently keeps the
# caller waiting for the full DURATION even though this script already
# returned. Redirecting the subshell's own fds to /dev/null closes its
# copies of them immediately, so a pipe/capture on this script's output
# sees EOF right away. This produces no loss of visible output: nothing in
# the background loop ever printed anything to begin with (send_typing_once
# failures are swallowed by `|| true`, same as before), and the foreground
# unconfigured-bridge error paths above this block are unaffected since
# they run - and exit - before this subshell is ever started.
(
  END=$(( $(date +%s) + DURATION ))
  send_typing_once || true
  while [[ "$(date +%s)" -lt "$END" ]]; do
    sleep 4
    send_typing_once || true
  done
) >/dev/null 2>&1 &
disown 2>/dev/null || true

exit 0
