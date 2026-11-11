#!/usr/bin/env python3
"""
ask.py - Send a question to the founder as a Telegram card with one tap-able
button per option, or clear a card's buttons.

Usage:
    python3 ask.py [--group] [--reply-to MESSAGE_ID] "Question text" "Option A" "Option B" ...
    python3 ask.py [--group] --clear CARD_MESSAGE_ID

On success prints the card's message_id on stdout (keep it: pass it to
--clear if the founder answers some other way) and exits 0.

What happens next is handled by bot.py, no session work needed:
- The founder taps a button -> bot.py removes the buttons, appends
  "✅ <choice>" to the card, and relays the choice into relay-inbox.jsonl as
  a record with `"kind": "button"`, `text` = the option label, `button`
  = {index, label} and `reply_to.message_id` = this card's id.
- The founder answers by Telegram-replying to the card -> bot.py removes the
  buttons and relays the reply as an ordinary message (its `reply_to`
  names the card).
- The founder answers in a plain, non-reply message -> call --clear with
  the card's id so stale buttons don't linger.

Button presses are routed by option index (callback_data "opt:<n>"), never
by label text, so any label works - only its display length is limited.

Reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from the .env next to this
script (never the caller's cwd), same as notify.sh. The token is never
printed; exception text is passed through redact_secrets() first.
"""

import argparse
import json
import sys
from pathlib import Path

import telegram_common

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
BRIDGE_CONFIG_FILE = SCRIPT_DIR / "bridge-config.json"
EXCHANGE_FILE = SCRIPT_DIR / ".last-exchange"

MAX_OPTIONS = 8
MAX_LABEL_CHARS = 60
CALLBACK_PREFIX = "opt:"


def build_keyboard(options):
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": f"{CALLBACK_PREFIX}{i}"}]
            for i, label in enumerate(options)
        ]
    }


def validate_options(options):
    if not options:
        return "at least one option is required"
    if len(options) > MAX_OPTIONS:
        return f"at most {MAX_OPTIONS} options are supported (got {len(options)})"
    for label in options:
        if not label.strip():
            return "options must be non-empty"
        if len(label) > MAX_LABEL_CHARS:
            return f"option longer than {MAX_LABEL_CHARS} chars: {label[:20]}..."
    return None


def resolve_chat_id(env: dict, group: bool):
    if not group:
        return env.get("TELEGRAM_CHAT_ID", "").strip() or None
    try:
        data = json.loads(BRIDGE_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("active_group_chat_id")


def parse_args(argv):
    p = argparse.ArgumentParser(prog="ask", description="Send a Telegram question card with option buttons.")
    p.add_argument("--group", action="store_true", help="send to the auto-discovered group instead of the founder DM")
    p.add_argument("--reply-to", type=int, help="thread the card as a reply to this message id")
    p.add_argument("--clear", type=int, metavar="CARD_MESSAGE_ID", help="remove the buttons from an earlier card")
    p.add_argument("question", nargs="?")
    p.add_argument("options", nargs="*")
    return p.parse_args(argv)


def main(argv=None, api=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = telegram_common.parse_env_file(ENV_FILE)
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(f"Error: TELEGRAM_BOT_TOKEN not set in {ENV_FILE}", file=sys.stderr)
        return 1
    chat_id = resolve_chat_id(env, args.group)
    if chat_id is None:
        what = "active_group_chat_id in bridge-config.json" if args.group else "TELEGRAM_CHAT_ID in .env"
        print(f"Error: no target chat ({what} is not set)", file=sys.stderr)
        return 1

    if api is None:
        def api(method, payload):
            return telegram_common.api_call(token, method, payload)

    if args.clear is not None:
        try:
            resp = api("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": args.clear,
                "reply_markup": {"inline_keyboard": []},
            })
        except Exception as exc:
            print(f"Error: Telegram request failed: {telegram_common.redact_secrets(exc)}", file=sys.stderr)
            return 1
        desc = str(resp.get("description", "")).lower()
        if resp.get("ok") or "not modified" in desc:
            return 0
        print(f"Error: Telegram refused to clear the card: {resp.get('description')}", file=sys.stderr)
        return 1

    if not args.question or not args.question.strip():
        print('Error: usage: ask "<question>" "<option 1>" ["<option 2>" ...]', file=sys.stderr)
        return 1
    problem = validate_options(args.options)
    if problem:
        print(f"Error: {problem}", file=sys.stderr)
        return 1

    payload = {
        "chat_id": chat_id,
        "text": args.question,
        "reply_markup": build_keyboard(args.options),
    }
    if args.reply_to is not None:
        payload["reply_parameters"] = {"message_id": args.reply_to, "allow_sending_without_reply": True}
    try:
        resp = api("sendMessage", payload)
    except Exception as exc:
        print(f"Error: Telegram request failed: {telegram_common.redact_secrets(exc)}", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(f"Error: Telegram API returned an error: {resp.get('description')}", file=sys.stderr)
        return 1
    telegram_common.mark_exchange(EXCHANGE_FILE)
    print((resp.get("result") or {}).get("message_id", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
