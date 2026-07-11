#!/usr/bin/env python3
"""
telegram_common.py - Shared Telegram helpers used by bot.py and daily_report.py.

Factors out the message-length chunking and chunked-sendMessage logic, since
both bot.py (live replies) and daily_report.py (daily digest) need to post
arbitrarily long text back to a single Telegram chat, safely split under
Telegram's 4096-character per-message limit.

Only stdlib + `requests` are used, matching the rest of this module.
"""

import logging

import requests

TELEGRAM_MAX_MESSAGE_LEN = 4096

log = logging.getLogger("claude-telegram-bridge")


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
            log.error("Failed to send message chunk to Telegram: %s", exc)
            all_ok = False
    return all_ok
