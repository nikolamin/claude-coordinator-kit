#!/usr/bin/env python3
"""
test_filter.py - Offline unit tests for the group-chat relay gating logic in
telegram_common.evaluate_incoming_message(), plus telegram_common.redact_secrets().

Pure function, no network/Telegram calls: feeds synthetic Telegram Bot API
`Message` dicts through the filter and asserts the relay decision. Covers
the gating protocol end to end (see telegram_common.py module docstring for
the rules themselves).

Run:
    python3 test_filter.py
    python3 -m unittest test_filter.py -v
"""

import unittest

import telegram_common as tc

FOUNDER_ID = 1000000001
BOT_ID = 999888777
BOT_USERNAME = "ExampleBridgeBot"
ALLOWLISTED_ID = 555666777
STRANGER_ID = 111222333

ALLOWLIST = {ALLOWLISTED_ID}


def mention_entity(offset, length):
    return {"type": "mention", "offset": offset, "length": length}


def make_message(
    *,
    chat_id,
    chat_type,
    from_id,
    from_username="user",
    from_is_bot=False,
    text="hello",
    entities=None,
    reply_from_id=None,
    reply_is_bot=False,
):
    message = {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": from_id, "is_bot": from_is_bot, "username": from_username},
        "text": text,
    }
    if entities is not None:
        message["entities"] = entities
    if reply_from_id is not None:
        message["reply_to_message"] = {
            "message_id": 0,
            "from": {"id": reply_from_id, "is_bot": reply_is_bot, "username": "bot"},
            "text": "(bot's earlier message)",
        }
    return message


def evaluate(message):
    return tc.evaluate_incoming_message(
        message,
        founder_chat_id=FOUNDER_ID,
        bot_id=BOT_ID,
        bot_username=BOT_USERNAME,
        allowlist=ALLOWLIST,
    )


class FilterTests(unittest.TestCase):
    def test_founder_dm_is_relayed(self):
        msg = make_message(chat_id=FOUNDER_ID, chat_type="private", from_id=FOUNDER_ID)
        result = evaluate(msg)
        self.assertTrue(result["relay"], result)
        self.assertEqual(result["reason"], "founder_dm")

    def test_stranger_dm_is_dropped(self):
        msg = make_message(chat_id=STRANGER_ID, chat_type="private", from_id=STRANGER_ID)
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "unauthorized_private_chat")

    def test_no_group_config_dm_behaves_like_original_1to1_check(self):
        """With bot_id/bot_username unset and an empty allowlist - the state
        of a bridge instance where nobody has ever configured group support
        - a private chat's relay decision must reduce to exactly the
        original "does chat_id match TELEGRAM_CHAT_ID" check.
        """
        result_ok = tc.evaluate_incoming_message(
            make_message(chat_id=FOUNDER_ID, chat_type="private", from_id=FOUNDER_ID),
            founder_chat_id=FOUNDER_ID, bot_id=None, bot_username=None, allowlist=set(),
        )
        self.assertTrue(result_ok["relay"])
        self.assertEqual(result_ok["reason"], "founder_dm")

        result_bad = tc.evaluate_incoming_message(
            make_message(chat_id=STRANGER_ID, chat_type="private", from_id=STRANGER_ID),
            founder_chat_id=FOUNDER_ID, bot_id=None, bot_username=None, allowlist=set(),
        )
        self.assertFalse(result_bad["relay"])
        self.assertEqual(result_bad["reason"], "unauthorized_private_chat")

    def test_founder_group_message_with_mention_is_relayed(self):
        text = "hey @ExampleBridgeBot status?"
        entities = [mention_entity(4, len("@ExampleBridgeBot"))]
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=FOUNDER_ID,
            text=text, entities=entities,
        )
        result = evaluate(msg)
        self.assertTrue(result["relay"], result)
        self.assertTrue(result["mentioned"])
        self.assertEqual(result["reason"], "founder_group")

    def test_founder_group_message_without_mention_is_dropped(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=FOUNDER_ID,
            text="just chatting, no mention here",
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "no_mention_or_reply")

    def test_founder_group_reply_to_bot_without_mention_is_relayed(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=FOUNDER_ID,
            text="yes please", reply_from_id=BOT_ID, reply_is_bot=True,
        )
        result = evaluate(msg)
        self.assertTrue(result["relay"], result)
        self.assertTrue(result["is_reply_to_bot"])
        self.assertEqual(result["reason"], "founder_group")

    def test_stranger_group_message_with_mention_is_dropped(self):
        text = "hey @ExampleBridgeBot status?"
        entities = [mention_entity(4, len("@ExampleBridgeBot"))]
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=STRANGER_ID,
            text=text, entities=entities,
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertTrue(result["mentioned"])  # mentioned, but sender isn't authorized
        self.assertEqual(result["reason"], "sender_not_authorized")

    def test_allowlisted_member_with_mention_is_relayed(self):
        text = "@ExampleBridgeBot ping"
        entities = [mention_entity(0, len("@ExampleBridgeBot"))]
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=ALLOWLISTED_ID,
            text=text, entities=entities,
        )
        result = evaluate(msg)
        self.assertTrue(result["relay"], result)
        self.assertEqual(result["reason"], "allowlisted_group")

    def test_allowlisted_member_without_mention_is_dropped(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=ALLOWLISTED_ID,
            text="no mention, no reply",
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "no_mention_or_reply")

    def test_allowlisted_member_reply_to_bot_is_relayed(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=ALLOWLISTED_ID,
            text="sure thing", reply_from_id=BOT_ID, reply_is_bot=True,
        )
        result = evaluate(msg)
        self.assertTrue(result["relay"], result)
        self.assertEqual(result["reason"], "allowlisted_group")

    def test_non_allowlisted_non_founder_reply_to_bot_is_dropped(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=STRANGER_ID,
            text="replying anyway", reply_from_id=BOT_ID, reply_is_bot=True,
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "sender_not_authorized")

    def test_bots_own_message_in_group_is_never_relayed(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=BOT_ID,
            from_is_bot=True, text="I am the bot talking",
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "own_message")

    def test_bots_own_message_in_private_is_never_relayed(self):
        # Defensive: shouldn't normally occur (Telegram doesn't echo a
        # bot's own sent messages back via getUpdates in private chats),
        # but the guard must hold regardless of chat type.
        msg = make_message(
            chat_id=FOUNDER_ID, chat_type="private", from_id=BOT_ID, from_is_bot=True,
        )
        result = evaluate(msg)
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "own_message")

    def test_redact_secrets_strips_bot_token_from_url(self):
        """Regression test for a real class of incident: a getUpdates 409
        conflict's RequestException.__str__ embeds the full request URL,
        including the bot token, and would get logged verbatim without this
        fix. redact_secrets() must strip that pattern from arbitrary text
        (str(exc), not just a bare URL) without touching anything else.
        """
        msg = (
            "409 Client Error: Conflict for url: "
            "https://api.telegram.org/bot123456789:AAExampleTokenExampleTokenExampleTok"
            "/getUpdates?timeout=25&offset=1"
        )
        redacted = tc.redact_secrets(msg)
        self.assertNotIn("AAExampleTokenExampleTokenExampleTok", redacted)
        self.assertIn("bot<redacted>", redacted)
        self.assertIn("409 Client Error", redacted)  # rest of the message survives

    def test_redact_secrets_is_a_noop_on_token_free_text(self):
        self.assertEqual(tc.redact_secrets("plain network timeout, no token here"),
                          "plain network timeout, no token here")

    def test_reply_to_a_non_bot_message_does_not_count_as_reply_to_bot(self):
        msg = make_message(
            chat_id=-100123, chat_type="supergroup", from_id=FOUNDER_ID,
            text="replying to a human", reply_from_id=STRANGER_ID, reply_is_bot=False,
        )
        result = evaluate(msg)
        self.assertFalse(result["is_reply_to_bot"])
        self.assertFalse(result["relay"], result)
        self.assertEqual(result["reason"], "no_mention_or_reply")

    def test_redact_secrets_strips_token_from_file_download_url(self):
        """Regression test for the media-relay feature: the file-download
        URL (https://api.telegram.org/file/bot<token>/<path>) embeds the
        token in the exact same "bot<digits>:<token>" shape as the regular
        Bot API base URL, so it must be caught by the same redact_secrets()
        pattern with no changes needed - this locks that in.
        """
        msg = (
            "404 Client Error: Not Found for url: "
            "https://api.telegram.org/file/bot123456789:AAExampleTokenExampleTokenExampleTok"
            "/photos/file_1.jpg"
        )
        redacted = tc.redact_secrets(msg)
        self.assertNotIn("AAExampleTokenExampleTokenExampleTok", redacted)
        self.assertIn("bot<redacted>", redacted)
        self.assertIn("404 Client Error", redacted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
