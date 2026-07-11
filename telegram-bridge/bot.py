#!/usr/bin/env python3
"""
bot.py - Telegram <-> Claude Code bridge.

Runs exactly ONE poll cycle per process invocation: a single long-poll
`getUpdates` call, handling whatever messages (zero, one, or more) come back
from a single authorized chat id, relaying each to `claude -p` (optionally
with `--continue` to keep conversation context), sending the response back
to the same Telegram chat, then exiting.

"Keep polling forever" is provided by an OS-level supervisor that relaunches
this process immediately after every exit - a launchd agent with
KeepAlive=true on macOS, or a systemd unit with Restart=always on Linux (see
SETUP.md for both templates). This means every cycle is a fresh process:
config/code changes on disk take effect on the very next cycle with no
separate restart step.

The Telegram update offset is persisted to OFFSET_FILE (.offset.json, next
to this script) so cycles resume where the previous one left off instead of
reprocessing or skipping messages.

Only stdlib + `requests` are used (no python-dotenv, no other third-party
deps) - .env is parsed manually below.

Run manually for testing:
    python3 bot.py

Or install via the provided launchd/systemd templates for always-on
operation. See SETUP.md for full setup instructions.
"""

import json
import logging
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import requests

import telegram_common

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
LOG_FILE = SCRIPT_DIR / "bot.log"
OFFSET_FILE = SCRIPT_DIR / ".offset.json"
RELAY_INBOX_FILE = SCRIPT_DIR / "relay-inbox.jsonl"

POLL_TIMEOUT = 25  # seconds, Telegram long-poll timeout (safely under Telegram's server-side max)
HTTP_TIMEOUT = POLL_TIMEOUT + 10  # requests timeout, must exceed poll timeout
CLAUDE_TIMEOUT = 600  # 10 minutes
TRUNCATE_LOG_CHARS = 200
TYPING_INTERVAL_SECONDS = 4  # Telegram's typing indicator lasts ~5s client-side

REACTION_SEEN = "\U0001F440"  # 👀 - received, about to process
# Telegram's setMessageReaction only accepts a fixed, curated set of emoji
# for `type: emoji` reactions; ✅/❌ are NOT in that set and are rejected
# with 400 REACTION_INVALID (see react.sh for the same fix, applied there
# first). 👍/👎 are the closest allowed equivalents.
REACTION_OK = "👍"  # 👍 - completed successfully
REACTION_FAIL = "👎"  # 👎 - failed (nonzero exit, timeout, exception)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("claude-telegram-bridge")


def parse_env_file(path: Path) -> dict:
    """Tiny manual .env parser: KEY=VALUE per line, '#' comments, no deps."""
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip inline comments that follow a '#' preceded by whitespace.
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        # Strip matching surrounding quotes, if present.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_config() -> dict:
    env = parse_env_file(ENV_FILE)

    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
    default_cwd = env.get("CLAUDE_DEFAULT_CWD", "").strip()

    missing = [
        name
        for name, val in (
            ("TELEGRAM_BOT_TOKEN", token),
            ("TELEGRAM_CHAT_ID", chat_id),
            ("CLAUDE_DEFAULT_CWD", default_cwd),
        )
        if not val
    ]
    if missing:
        log.error(
            "Missing required .env variable(s): %s. "
            "Copy .env.example to .env and fill them in.",
            ", ".join(missing),
        )
        sys.exit(1)

    return {
        "token": token,
        "chat_id": chat_id,
        "default_cwd": default_cwd,
        # RELAY_MODE=1: don't invoke the claude CLI at all. Instead, append each
        # authorized incoming message to RELAY_INBOX_FILE as a JSON line; a live
        # Claude Code session tails that file and replies via notify.sh + react.sh.
        # This routes Telegram messages into the SAME session/context as the
        # live coordinator session, rather than a separate headless claude instance.
        "relay_mode": env.get("RELAY_MODE", "").strip() in ("1", "true", "yes"),
    }


def truncate(text: str, limit: int = TRUNCATE_LOG_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def load_offset():
    """Read the persisted update offset. Returns None if unset/missing/corrupt.

    A missing file (first run ever) and a malformed file (corrupted write)
    are both treated the same way: fall back to an unset offset, same as
    the original in-memory default. A corrupt file is logged as a warning,
    not a crash.
    """
    if not OFFSET_FILE.exists():
        return None
    try:
        raw = OFFSET_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        offset = data.get("offset")
        if offset is None:
            return None
        return int(offset)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        log.warning(
            "Offset file %s is missing/corrupt (%s); starting from unset offset.",
            OFFSET_FILE,
            exc,
        )
        return None


def save_offset(offset) -> None:
    """Persist the update offset. Writes atomically (temp file + rename)."""
    tmp_path = OFFSET_FILE.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps({"offset": offset}), encoding="utf-8")
        tmp_path.replace(OFFSET_FILE)
    except OSError as exc:
        log.error("Failed to persist offset (%s) to %s: %s", offset, OFFSET_FILE, exc)


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset=None, timeout=POLL_TIMEOUT):
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        resp = requests.get(
            f"{self.base_url}/getUpdates",
            params=params,
            timeout=timeout + 10,
        )
        resp.raise_for_status()
        return resp.json()

    def send_message(self, chat_id, text):
        return telegram_common.send_message(self.token, chat_id, text)

    def send_message_chunked(self, chat_id, text):
        return telegram_common.send_message_chunked(self.token, chat_id, text)

    def set_reaction(self, chat_id, message_id, emoji):
        """Set (replace) the reaction on a message. Raises on HTTP failure."""
        resp = requests.post(
            f"{self.base_url}/setMessageReaction",
            data={
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": json.dumps([{"type": "emoji", "emoji": emoji}]),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def send_chat_action(self, chat_id, action="typing"):
        resp = requests.post(
            f"{self.base_url}/sendChatAction",
            data={"chat_id": chat_id, "action": action},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def safe_set_reaction(client: TelegramClient, chat_id, message_id, emoji):
    """Best-effort setMessageReaction: never let a reaction failure propagate."""
    try:
        client.set_reaction(chat_id, message_id, emoji)
    except Exception as exc:
        log.warning(
            "Failed to set reaction %r on chat_id=%s message_id=%s: %s",
            emoji,
            chat_id,
            message_id,
            exc,
        )


class TypingIndicator:
    """Background thread that pings Telegram's 'typing' chat action on an
    interval, since the indicator only lasts ~5s client-side and `claude -p`
    can run for minutes. Start it right before launching the subprocess and
    always stop() it in a finally block once the subprocess completes.
    """

    def __init__(self, client: TelegramClient, chat_id, interval=TYPING_INTERVAL_SECONDS):
        self.client = client
        self.chat_id = chat_id
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self.client.send_chat_action(self.chat_id, "typing")
            except Exception as exc:
                log.warning("Failed to send typing action: %s", exc)
            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)


def run_claude(args, cwd):
    """Run a claude CLI invocation, returning (ok, output_text)."""
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.error("claude command timed out after %s seconds: %s", CLAUDE_TIMEOUT, args)
        return False, "Claude command timed out after 10 minutes."
    except Exception as exc:  # defensive: never let a subprocess issue crash the loop
        log.error("Failed to run claude command %s: %s", args, exc)
        return False, f"Failed to run Claude: {exc}"

    if result.returncode != 0:
        stderr_excerpt = truncate(result.stderr, 500)
        log.error(
            "claude exited with code %s. stderr: %s", result.returncode, stderr_excerpt
        )
        return False, f"Claude exited with an error: {stderr_excerpt}"

    return True, result.stdout


def run_claude_with_typing(client: TelegramClient, chat_id, args, cwd):
    """run_claude(), with a typing indicator active for its whole duration."""
    indicator = TypingIndicator(client, chat_id)
    indicator.start()
    try:
        return run_claude(args, cwd)
    finally:
        indicator.stop()


def relay_message(client: TelegramClient, chat_id, message_id, text: str):
    """RELAY_MODE handler: 👀-react and append the message to the relay inbox.

    The reply and the final 👍/👎 reaction are the responsibility of the live
    Claude Code session watching RELAY_INBOX_FILE (via notify.sh / react.sh) -
    this process only acknowledges receipt and hands the message off.
    """
    safe_set_reaction(client, chat_id, message_id, REACTION_SEEN)
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    with RELAY_INBOX_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("[relay] queued message_id=%s incoming=%r", message_id, truncate(text))


def handle_message(client: TelegramClient, config: dict, chat_id, message_id, text: str):
    text = text or ""
    stripped = text.strip()

    if config.get("relay_mode"):
        relay_message(client, chat_id, message_id, text)
        return

    safe_set_reaction(client, chat_id, message_id, REACTION_SEEN)

    ok = True
    try:
        if stripped == "/new" or stripped.startswith("/new "):
            remainder = stripped[len("/new"):].strip()

            if remainder:
                ok, output = run_claude_with_typing(
                    client, chat_id, ["claude", "-p", remainder], config["default_cwd"]
                )
                reply = "New session started.\n\n" + output
            else:
                ok = True
                output = ""
                reply = "New session started."

            log.info(
                "[/new] incoming=%r ok=%s response=%r",
                truncate(text),
                ok,
                truncate(output),
            )
            sent_ok = client.send_message_chunked(chat_id, reply)
            # A reply that failed to actually reach Telegram is still a
            # failure from the user's point of view, even if Claude itself
            # succeeded - reflect that in the 👍/👎 reaction below.
            ok = ok and sent_ok
            return

        ok, output = run_claude_with_typing(
            client, chat_id, ["claude", "-p", "--continue", text], config["default_cwd"]
        )

        log.info(
            "[continue] incoming=%r ok=%s response=%r",
            truncate(text),
            ok,
            truncate(output),
        )

        reply = output if output else "(no output from Claude)"
        sent_ok = client.send_message_chunked(chat_id, reply)
        ok = ok and sent_ok
    except Exception:
        ok = False
        raise
    finally:
        safe_set_reaction(
            client, chat_id, message_id, REACTION_OK if ok else REACTION_FAIL
        )


def poll_once(client: TelegramClient, config: dict) -> int:
    """Run exactly one getUpdates cycle. Returns a process exit code.

    Returns 0 for a normal cycle - including a timeout with no updates at
    all, and including updates that were handled but whose individual
    handling failed (those are reported back to the user via chat and a
    👎 reaction, not via process exit code). Returns 1 only when the poll
    itself failed (network error, malformed response, etc.) so such
    failures are still visible in logs/launchd/systemd.
    """
    authorized_chat_id = config["chat_id"]
    offset = load_offset()

    try:
        data = client.get_updates(offset=offset, timeout=POLL_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        log.error("Network error while polling Telegram: %s", exc)
        return 1
    except ValueError as exc:  # includes JSONDecodeError
        log.error("Failed to decode Telegram response: %s", exc)
        return 1

    if not data.get("ok", False):
        log.error("getUpdates returned ok=false: %s", data)
        return 1

    updates = data.get("result", [])
    if not updates:
        log.info("No updates this poll cycle.")
        return 0

    for update in updates:
        offset = update["update_id"] + 1
        # Persist immediately, before handling, so a crash mid-handling
        # never causes this same update to be reprocessed on next launch.
        save_offset(offset)

        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        chat = message.get("chat", {})
        incoming_chat_id = str(chat.get("id", ""))
        text = message.get("text")
        message_id = message.get("message_id")

        if incoming_chat_id != str(authorized_chat_id):
            sender = message.get("from", {})
            log.warning(
                "Rejected message from unauthorized chat_id=%s (sender=%s): %r",
                incoming_chat_id,
                sender.get("username") or sender.get("first_name") or "unknown",
                truncate(text or ""),
            )
            continue

        if not text:
            log.info("Ignoring non-text message from authorized chat.")
            continue

        try:
            handle_message(client, config, chat.get("id"), message_id, text)
        except Exception as exc:
            log.error("Error handling message %r: %s", truncate(text), exc)
            try:
                client.send_message_chunked(
                    chat.get("id"), f"Internal error handling your message: {exc}"
                )
            except Exception as send_exc:
                log.error("Failed to send error message to chat: %s", send_exc)

    return 0


def main() -> int:
    config = load_config()
    client = TelegramClient(config["token"])
    log.info(
        "claude-telegram-bridge: starting single poll cycle. default_cwd=%s",
        config["default_cwd"],
    )
    try:
        exit_code = poll_once(client, config)
    except Exception as exc:  # never let an unexpected error crash without logging
        log.error("Unexpected error during poll cycle: %s", exc)
        exit_code = 1
    log.info("Poll cycle complete, exit_code=%s", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
