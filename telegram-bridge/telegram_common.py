#!/usr/bin/env python3
"""
telegram_common.py - Shared Telegram helpers used by bot.py and daily_report.py.

Factors out the message-length chunking and chunked-sendMessage logic, since
both bot.py (live replies) and daily_report.py (daily digest) need to post
arbitrarily long text back to a single Telegram chat, safely split under
Telegram's 4096-character per-message limit. Also factors out the group-chat
relay-gating logic (pure functions, no I/O) and secret-redaction helper
shared with bot.py.

Only stdlib + `requests` are used, matching the rest of this module.
"""

import json
import logging
import re
from pathlib import Path

import requests

TELEGRAM_MAX_MESSAGE_LEN = 4096

log = logging.getLogger("claude-telegram-bridge")

# Matches the bot-token segment of a Telegram Bot API URL, e.g.
# "https://api.telegram.org/bot123456:AAExampleTokenExample/getUpdates".
# `requests` exceptions (HTTPError, ConnectionError, Timeout, ...) commonly
# embed the full request URL in their str() representation - if one of
# those gets logged verbatim, the bot token leaks into bot.log/stdout. Every
# call site that logs a caught exception from a Telegram API call MUST pass
# it through redact_secrets() first; see bot.py's exception-logging sites.
_TOKEN_URL_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def redact_secrets(text) -> str:
    """Replace any Telegram bot-token-shaped substring in `text` with a
    placeholder. Safe to call on arbitrary text (e.g. str(exc)) - a no-op
    when no token-shaped substring is present.
    """
    return _TOKEN_URL_RE.sub("bot<redacted>", str(text))


def chunk_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LEN):
    """Split text into chunks <= limit chars, preferring line boundaries."""
    if not text:
        return [""]

    chunks = []
    current = ""

    for line in text.splitlines(keepends=True):
        # A single line longer than the limit must be hard-split.
        if len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(line):
                chunks.append(line[start:start + limit])
                start += limit
            continue

        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line

    if current:
        chunks.append(current)

    return chunks or [""]


def send_message(token: str, chat_id, text: str, timeout: int = 30):
    """Send a single Telegram message. Caller must pre-chunk to <= 4096 chars."""
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def download_file(token: str, file_path: str, dest_path, timeout: int = 60) -> Path:
    """Download a Telegram-hosted file (its `file_path`, as resolved by a
    prior `getFile` call) to `dest_path` on local disk.

    Streams the response instead of buffering it fully in memory, and writes
    via a temp-file + rename (same atomic-write pattern used for this repo's
    JSON state files) so a crash or interrupted download never leaves a
    half-written file at `dest_path`.

    The download URL is `https://api.telegram.org/file/bot<token>/<file_path>`
    - it embeds the bot token exactly like the regular Bot API base URL, so
    any exception raised here (e.g. `requests.HTTPError`, whose `str()`
    commonly includes the full request URL) MUST be passed through
    `redact_secrets()` before logging - never log/print `url` directly.
    """
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".tmp")
    with tmp_path.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    tmp_path.replace(dest_path)
    return dest_path


def send_message_chunked(token: str, chat_id, text: str) -> bool:
    """Send text to a Telegram chat, splitting into <=4096-char chunks.

    Best-effort per chunk: a failed chunk is logged and skipped rather than
    raising, so one bad chunk doesn't prevent the rest of a long reply from
    going out. Returns True iff every non-empty chunk was sent successfully
    (callers that need to know whether the send fully succeeded - e.g. to
    decide whether it's safe to advance a "last reported" marker - should
    check this return value).
    """
    all_ok = True
    for chunk in chunk_message(text):
        if chunk == "":
            continue
        try:
            send_message(token, chat_id, chunk)
        except requests.exceptions.RequestException as exc:
            log.error("Failed to send message chunk to Telegram: %s", redact_secrets(exc))
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# Scheduled-digest send-target resolution
#
# Shared by any SCHEDULED/AUTOMATED script (daily_report.py and similar) that
# wants an opt-in way to send to the auto-discovered group instead of the
# founder's private DM. Scoped ONLY to whatever script explicitly calls it -
# does NOT change bot.py's live relay behavior, notify.sh's default DM
# target, or react.sh; those keep targeting TELEGRAM_CHAT_ID / the chat a
# message actually came from, unless the caller opts in (e.g. notify.sh
# --group), unchanged.
# ---------------------------------------------------------------------------

def resolve_group_send_target(bridge_config_path: Path):
    """Resolve the Telegram chat id a SCHEDULED digest script should send to.

    Returns (chat_id, error_message):
      - On success: (chat_id, None).
      - On failure (file missing, corrupt, or lacking active_group_chat_id):
        (None, "<human-readable reason>").

    Callers MUST treat a (None, ...) result as fatal for that run - log the
    error clearly and exit non-zero WITHOUT sending anywhere. Silently
    falling back to some other chat id (e.g. the founder's private
    TELEGRAM_CHAT_ID) would mean a scheduled digest goes to the wrong place
    with no visible signal that anything was wrong - worse than a skipped
    run, which can simply be retried on the next scheduled invocation.
    """
    if not bridge_config_path.exists():
        return None, (
            f"{bridge_config_path} not found - no group discovered yet. "
            "Add the bot to the group and send any message that mentions it "
            "first; bot.py auto-discovers the group chat id (see SETUP.md "
            "'Group chat support')."
        )
    try:
        data = json.loads(bridge_config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{bridge_config_path} is missing/corrupt: {exc}"

    if not isinstance(data, dict):
        return None, f"{bridge_config_path} does not contain a JSON object."

    chat_id = data.get("active_group_chat_id")
    if chat_id is None:
        return None, (
            f"{bridge_config_path} has no active_group_chat_id yet - group "
            "not discovered. See SETUP.md 'Group chat support'."
        )
    return chat_id, None


# ---------------------------------------------------------------------------
# Group-chat relay gating
#
# Pure functions (no I/O, no Telegram calls) so the gating rules can be
# unit-tested by feeding in synthetic `message` dicts shaped like Telegram's
# Bot API `Message` object. See test_filter.py for the test matrix.
#
# Gating protocol:
#   - Private chat: relay iff the chat is the authorized founder's own
#     private chat (unchanged from the original 1:1 behavior - this is the
#     ONLY path exercised when no group config exists).
#   - Group/supergroup chat: relay iff the sender is EITHER the founder OR a
#     member on the allowlist, AND the message either @mentions the bot or
#     is a reply to one of the bot's own messages. Everything else in a
#     group is dropped.
#   - The bot's own messages are never relayed, in any chat type.
# ---------------------------------------------------------------------------

def sender_display_name(sender: dict) -> str:
    """Best-effort human-readable name for a Telegram `from` user object."""
    sender = sender or {}
    return (
        sender.get("username")
        or " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")]))
        or "unknown"
    )


def _extract_entity_text(text: str, entity: dict) -> str:
    """Slice `text` for a Telegram message entity.

    NOTE: Telegram's `offset`/`length` are UTF-16 code-unit counts, while
    Python string slicing is code-point based. These only diverge when
    characters outside the Basic Multilingual Plane (e.g. some emoji)
    appear before the entity in the same message - an accepted, narrow
    edge case for this bridge's purposes (bot @mentions are plain ASCII).
    """
    offset = entity.get("offset", 0)
    length = entity.get("length", 0)
    return text[offset:offset + length]


def is_bot_mentioned(text: str, entities, bot_username) -> bool:
    """True if `entities` contains an @mention of `bot_username`."""
    if not bot_username:
        return False
    text = text or ""
    target = ("@" + bot_username).lower()
    for entity in entities or []:
        etype = entity.get("type")
        if etype == "mention":
            if _extract_entity_text(text, entity).lower() == target:
                return True
        elif etype == "text_mention":
            # Only applies to users without a @username, so practically
            # never fires for a bot mention - included for completeness.
            user = entity.get("user") or {}
            if (user.get("username") or "").lower() == bot_username.lower():
                return True
    return False


def is_reply_to_bot_message(message: dict, bot_id) -> bool:
    """True if `message` is a reply to a message sent by the bot itself."""
    reply = message.get("reply_to_message")
    if not reply or bot_id is None:
        return False
    sender = reply.get("from") or {}
    return bool(sender.get("is_bot")) and sender.get("id") == bot_id


def evaluate_incoming_message(message: dict, *, founder_chat_id, bot_id, bot_username, allowlist) -> dict:
    """Decide whether an incoming Telegram `message` should be relayed.

    Returns a dict always containing the relay-metadata fields (regardless
    of the relay decision, so callers can log why a message was dropped):
        relay            bool   - whether this message should be relayed
        chat_id          int
        chat_type        str    - "private" | "group" | "supergroup" | ...
        from_id          int | None
        from_name        str
        is_reply_to_bot  bool
        mentioned        bool
        reason           str    - short machine-readable reason code

    With bot_id/bot_username unset and allowlist empty (the state when no
    group features have been configured), the ONLY reachable outcomes are
    "founder_dm" (relay=True) and "unauthorized_private_chat" (relay=False)
    for private chats - group chats always fall through to
    "sender_not_authorized"/"no_mention_or_reply" and are dropped, since
    there is nothing to opt into. This mirrors the original 1:1
    TELEGRAM_CHAT_ID-only allowlisting exactly for the private-chat case.
    """
    sender = message.get("from") or {}
    from_id = sender.get("id")
    from_name = sender_display_name(sender)

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "")

    text = message.get("text") or ""
    entities = message.get("entities") or []

    mentioned = is_bot_mentioned(text, entities, bot_username)
    reply_to_bot = is_reply_to_bot_message(message, bot_id)

    result = {
        "relay": False,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "from_id": from_id,
        "from_name": from_name,
        "is_reply_to_bot": reply_to_bot,
        "mentioned": mentioned,
        "reason": "",
    }

    # The bot must never relay its own messages, in any chat type.
    if sender.get("is_bot") and bot_id is not None and from_id == bot_id:
        result["reason"] = "own_message"
        return result

    if chat_type == "private":
        if founder_chat_id is not None and str(chat_id) == str(founder_chat_id):
            result["relay"] = True
            result["reason"] = "founder_dm"
        else:
            result["reason"] = "unauthorized_private_chat"
        return result

    if chat_type in ("group", "supergroup"):
        is_founder = founder_chat_id is not None and str(from_id) == str(founder_chat_id)
        is_allowlisted = bool(allowlist) and (from_id in allowlist or str(from_id) in allowlist)
        authorized_sender = is_founder or is_allowlisted

        if not authorized_sender:
            result["reason"] = "sender_not_authorized"
            return result

        if not (mentioned or reply_to_bot):
            result["reason"] = "no_mention_or_reply"
            return result

        result["relay"] = True
        result["reason"] = "founder_group" if is_founder else "allowlisted_group"
        return result

    result["reason"] = "unsupported_chat_type:%s" % chat_type
    return result
