#!/usr/bin/env python3
"""
get_chat_id.py - One-shot helper to discover your Telegram chat id.

Usage:
    1. Message your bot at least once on Telegram (any text, e.g. "hi").
    2. Run: python3 get_chat_id.py
    3. Copy the printed chat id into TELEGRAM_CHAT_ID in your .env file.

Reads TELEGRAM_BOT_TOKEN from .env next to this script.

Equivalent one-liner if you'd rather not run a script (see SETUP.md step (a)):
    curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool
"""

import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"


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
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def main():
    env = parse_env_file(ENV_FILE)
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        print(
            f"Error: TELEGRAM_BOT_TOKEN not found in {ENV_FILE}. "
            "Copy .env.example to .env and fill it in first.",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as exc:
        print(f"Error: request to Telegram API failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: could not decode Telegram API response: {exc}", file=sys.stderr)
        sys.exit(1)

    if not data.get("ok", False):
        print(f"Error: Telegram API returned an error: {data}", file=sys.stderr)
        sys.exit(1)

    results = data.get("result", [])
    if not results:
        print(
            "No updates found yet.\n"
            "Send your bot a message on Telegram first (any text), then re-run this script."
        )
        return

    seen_chat_ids = {}
    for update in results:
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        name = (
            chat.get("username")
            or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name")])
            )
            or chat.get("title")
            or "unknown"
        )
        seen_chat_ids[chat_id] = name

    if not seen_chat_ids:
        print(
            "No chat information found in updates.\n"
            "Send your bot a message on Telegram first (any text), then re-run this script."
        )
        return

    print("Found the following chat id(s):")
    for chat_id, name in seen_chat_ids.items():
        print(f"  chat_id={chat_id}  (name/username: {name})")
    print(
        "\nCopy the chat_id that corresponds to you into TELEGRAM_CHAT_ID in your .env file."
    )


if __name__ == "__main__":
    main()
