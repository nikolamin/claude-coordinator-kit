#!/usr/bin/env python3
"""
test_bot.py - Offline unit tests for bot.py's group-chat seen-members
capture and media-relay handling (voice/audio/video/video_note/photo/
document), including the unified "photo_path" convenience field for image
media (photo, or a document whose mime_type starts with image/).

No real network or disk I/O: Telegram calls are faked via a minimal stub
client, real filesystem writes for downloaded media/relay-inbox.jsonl are
redirected to a temp directory (never this repo's real media-inbox/ or
relay-inbox.jsonl - the latter would be tailed by a live Claude Code session
and must never see synthetic test data), and bot.py's persistence functions
(save_offset/save_bridge_config/save_seen_members) are patched out so tests
never touch this repo's real runtime-state files. As a backstop for when a
test class forgets one of those, this module sets TELEGRAM_BRIDGE_TEST_MODE=1
before importing bot, which arms bot.py's guard_production_write(): while it
is set, any write aimed at a real live-service state path raises instead of
landing on disk (see ProductionStateWriteGuardTests). The actual Telegram file
download (resolve_telegram_file_path/download_telegram_file) is patched at
the module level rather than faked through a client method, since that's
how bot.py itself calls it.

Run:
    python3 test_bot.py
    python3 -m unittest test_bot.py -v
"""

import json
import logging
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import requests

# Announce "this is a test process" BEFORE importing bot, so bot.py's
# production-state write guard is armed for everything this module does.
# While this is set, bot.py refuses to write any of the repo's real
# live-service state files (relay-inbox.jsonl, .offset.json,
# bridge-config.json, seen-members.json, media-inbox/) and raises instead -
# so a test class that forgets to redirect those paths at a temp directory
# fails loudly here rather than silently injecting synthetic messages into
# the live relay inbox a running Claude Code session is tailing. See
# guard_production_write() in bot.py.
os.environ["TELEGRAM_BRIDGE_TEST_MODE"] = "1"

import bot as bot_module  # noqa: E402  (must follow the env var above)

# bot.py's module-level logging.basicConfig() attaches a FileHandler pointed
# at the real bot.log (next to bot.py), on the ROOT logger, as an import
# side effect - fine for the live service (one process, one log), but
# importing the module here would otherwise make every test run leak
# synthetic log lines (fake sender names, fake chat activity) into that
# production log file, since bot.py's own "claude-telegram-bridge" logger
# has no handlers of its own and simply propagates up to root. Replace the
# root logger's handlers for the duration of this test module so
# `python3 test_bot.py` / `python3 -m unittest test_bot.py` never writes to
# bot.log.
logging.getLogger().handlers = [logging.NullHandler()]

FOUNDER_CHAT_ID = 1000000001
BOT_ID = 999888777
BOT_USERNAME = "ExampleBridgeBot"
GROUP_CHAT_ID = -100999888
GROUP_TITLE = "Example Group"


def _redirect_state_paths_to_tempdir(self):
    """setUp helper: point bot.py's on-disk state paths at a fresh temp
    directory for the duration of one test.

    Any test that calls bot.poll_once() MUST use this (or do the equivalent
    patching itself, as MediaRelayTests' own setUp does). poll_once() can
    reach relay_message()/relay_media(), both of which append to
    bot.RELAY_INBOX_FILE - and the unpatched value of that constant is this
    repo's LIVE relay-inbox.jsonl, which a running Claude Code session
    tails and treats as real incoming Telegram traffic. Patching only the
    save_* persistence helpers is NOT enough: that was the 2026-07-27 bug,
    where GroupActivationGatingTests' founder-mention fixture (synthetic
    group -100999888, synthetic "founder" sender) was appended to the live
    inbox on every test run and read as an intrusion. bot.py's
    guard_production_write() now also refuses such a write outright, but
    redirecting the paths here is what makes these tests actually exercise
    the write path.
    """
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    tmp_path = Path(tmpdir.name)
    self.relay_inbox_file = tmp_path / "relay-inbox.jsonl"
    self.media_inbox_dir = tmp_path / "media-inbox"
    for patcher in (
        mock.patch.object(bot_module, "RELAY_INBOX_FILE", self.relay_inbox_file),
        mock.patch.object(bot_module, "MEDIA_INBOX_DIR", self.media_inbox_dir),
    ):
        patcher.start()
        self.addCleanup(patcher.stop)


class ProductionStateWriteGuardTests(unittest.TestCase):
    """The defense-in-depth backstop itself: with TELEGRAM_BRIDGE_TEST_MODE
    set (this module sets it at import), bot.py must refuse to write any of
    the repo's real live-service state paths, and must still allow writes to
    a redirected temp path.
    """

    def test_guard_raises_for_each_real_production_state_path(self):
        for path, name in (
            (bot_module.SCRIPT_DIR / "relay-inbox.jsonl", "RELAY_INBOX_FILE"),
            (bot_module.SCRIPT_DIR / ".offset.json", "OFFSET_FILE"),
            (bot_module.SCRIPT_DIR / "bridge-config.json", "BRIDGE_CONFIG_FILE"),
            (bot_module.SCRIPT_DIR / "seen-members.json", "SEEN_MEMBERS_FILE"),
            (bot_module.SCRIPT_DIR / "media-inbox", "MEDIA_INBOX_DIR"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    bot_module.guard_production_write(path, name)

    def test_guard_allows_a_redirected_temp_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            bot_module.guard_production_write(Path(tmp) / "relay-inbox.jsonl", "RELAY_INBOX_FILE")

    def test_guard_is_a_no_op_when_the_env_var_is_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            bot_module.guard_production_write(bot_module.RELAY_INBOX_FILE, "RELAY_INBOX_FILE")

    def test_poll_once_refuses_to_run_against_the_live_relay_inbox(self):
        """The exact 2026-07-27 regression: a poll_once() test that patches
        only the save_* helpers, leaving RELAY_INBOX_FILE pointing at the
        live file, must now fail loudly instead of appending to it.
        """
        client = _FakeClient([])
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": True, "default_cwd": "/tmp"}
        with mock.patch.object(bot_module, "save_offset"), \
                mock.patch.object(bot_module, "save_bridge_config"), \
                mock.patch.object(bot_module, "save_seen_members"):
            with self.assertRaises(RuntimeError):
                bot_module.poll_once(
                    client, config, {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}, set(), {}
                )

    def test_relay_message_refuses_to_append_to_the_live_relay_inbox(self):
        before = bot_module.RELAY_INBOX_FILE.read_bytes() if bot_module.RELAY_INBOX_FILE.exists() else None
        decision = {"chat_id": FOUNDER_CHAT_ID, "chat_type": "private", "from_id": FOUNDER_CHAT_ID}
        with self.assertRaises(RuntimeError):
            bot_module.relay_message(_FakeClient([]), 12345, decision, "synthetic test text")
        after = bot_module.RELAY_INBOX_FILE.read_bytes() if bot_module.RELAY_INBOX_FILE.exists() else None
        self.assertEqual(before, after)

    def test_save_helpers_refuse_to_write_real_runtime_state(self):
        with self.assertRaises(RuntimeError):
            bot_module.save_offset(1)
        with self.assertRaises(RuntimeError):
            bot_module.save_bridge_config({})
        with self.assertRaises(RuntimeError):
            bot_module.save_seen_members({})


class UpdateSeenMembersTests(unittest.TestCase):
    """Pure-function tests for bot.update_seen_members() - no I/O."""

    def test_first_seen_preserved_and_mentioned_bot_ors_in(self):
        seen = {}
        sender = {
            "id": 111,
            "is_bot": False,
            "username": "alice",
            "first_name": "Alice",
            "last_name": "A",
        }

        seen = bot_module.update_seen_members(
            seen, sender, chat_id=-100, mentioned=False, now="2026-01-01T10:00:00"
        )
        entry = seen["111"]
        self.assertEqual(entry["user_id"], 111)
        self.assertEqual(entry["username"], "alice")
        self.assertEqual(entry["chat_id"], -100)
        self.assertEqual(entry["first_seen_ts"], "2026-01-01T10:00:00")
        self.assertEqual(entry["last_seen_ts"], "2026-01-01T10:00:00")
        self.assertFalse(entry["mentioned_bot"])

        # A later message that DOES mention the bot must flip the flag on,
        # but must NOT move first_seen_ts.
        seen = bot_module.update_seen_members(
            seen, sender, chat_id=-100, mentioned=True, now="2026-01-01T10:05:00"
        )
        entry = seen["111"]
        self.assertEqual(entry["first_seen_ts"], "2026-01-01T10:00:00")
        self.assertEqual(entry["last_seen_ts"], "2026-01-01T10:05:00")
        self.assertTrue(entry["mentioned_bot"])

        # mentioned_bot is a rolling OR - a later non-mentioning message
        # must not flip it back off.
        seen = bot_module.update_seen_members(
            seen, sender, chat_id=-100, mentioned=False, now="2026-01-01T10:10:00"
        )
        self.assertTrue(seen["111"]["mentioned_bot"])
        self.assertEqual(seen["111"]["last_seen_ts"], "2026-01-01T10:10:00")

    def test_bot_sender_is_skipped(self):
        seen = {}
        sender = {"id": 999, "is_bot": True, "username": "SomeBot"}
        seen = bot_module.update_seen_members(seen, sender, chat_id=-100, mentioned=False)
        self.assertEqual(seen, {})

    def test_missing_sender_id_is_skipped(self):
        seen = {}
        seen = bot_module.update_seen_members(seen, {}, chat_id=-100, mentioned=False)
        self.assertEqual(seen, {})


class _FakeClient:
    """Minimal stand-in for bot.TelegramClient: get_updates() replays a
    fixed list of updates; set_reaction()/send_message_chunked() are
    recorded rather than hitting the network.
    """

    def __init__(self, updates):
        self._updates = updates
        self.reactions = []
        self.sent_messages = []

    def get_updates(self, offset=None, timeout=None):
        return {"ok": True, "result": self._updates}

    def set_reaction(self, chat_id, message_id, emoji):
        self.reactions.append((chat_id, message_id, emoji))
        return {"ok": True}

    def send_message_chunked(self, chat_id, text):
        self.sent_messages.append((chat_id, text))
        return True


class SeenMemberCaptureDuringPollTests(unittest.TestCase):
    """Integration-ish tests through bot.poll_once(): confirm seen-members
    capture fires for a real group update even when the relay decision is
    False - the exact situation of a not-yet-allowlisted member chatting in
    the group, or mentioning the bot before being allowlisted.
    """

    setUp = _redirect_state_paths_to_tempdir

    def _run_poll_once(self, update, allowlist):
        client = _FakeClient([update])
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": True, "default_cwd": "/tmp"}
        bridge_config = {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}
        seen_members = {}

        with mock.patch.object(bot_module, "save_offset"), \
                mock.patch.object(bot_module, "save_bridge_config"), \
                mock.patch.object(bot_module, "save_seen_members"):
            exit_code = bot_module.poll_once(client, config, bridge_config, allowlist, seen_members)

        return exit_code, seen_members

    def test_non_relayed_group_message_is_still_recorded(self):
        update = {
            "update_id": 42,
            "message": {
                "message_id": 500,
                "date": 1700000000,
                "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
                "from": {
                    "id": 222333444,
                    "is_bot": False,
                    "username": "someone",
                    "first_name": "Some",
                    "last_name": "One",
                },
                "text": "just chatting, no mention, no reply",
            },
        }

        exit_code, seen_members = self._run_poll_once(update, allowlist=set())

        self.assertEqual(exit_code, 0)
        # Not relayed (unauthorized sender + no mention/reply)...
        self.assertIn("222333444", seen_members)
        entry = seen_members["222333444"]
        # ...but still captured, with no message text stored anywhere.
        self.assertEqual(entry["username"], "someone")
        self.assertEqual(entry["first_name"], "Some")
        self.assertEqual(entry["last_name"], "One")
        self.assertEqual(entry["chat_id"], GROUP_CHAT_ID)
        self.assertFalse(entry["mentioned_bot"])
        self.assertNotIn("text", entry)

    def test_mentioning_but_not_yet_allowlisted_sender_is_recorded(self):
        text = "@ExampleBridgeBot hi"
        update = {
            "update_id": 43,
            "message": {
                "message_id": 501,
                "date": 1700000001,
                "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
                "from": {
                    "id": 333444555,
                    "is_bot": False,
                    "username": "newperson",
                    "first_name": "New",
                    "last_name": "Person",
                },
                "text": text,
                "entities": [{"type": "mention", "offset": 0, "length": len("@ExampleBridgeBot")}],
            },
        }

        exit_code, seen_members = self._run_poll_once(update, allowlist=set())

        self.assertEqual(exit_code, 0)
        self.assertIn("333444555", seen_members)
        self.assertTrue(seen_members["333444555"]["mentioned_bot"])


class GroupActivationGatingTests(unittest.TestCase):
    """Regression tests for the fix that stopped a stranger's group from
    silently hijacking active_group_chat_id (what notify.sh --group sends
    to). record_group_discovery() (id/title bookkeeping in
    discovered_groups) must still run for every group message the bot
    observes - but activate_group() (which sets active_group_chat_id) must
    ONLY ever run for a message that has already passed the relay gate
    (founder or allowlisted sender, AND mentioned/replied). Before this
    fix, a stranger merely adding the bot to an unrelated group - before
    the founder's own group was ever seen - could capture
    active_group_chat_id, and a later `notify.sh --group` would send
    founder/coordinator status straight to that stranger's group.
    """

    setUp = _redirect_state_paths_to_tempdir

    def _run(self, update, allowlist=None, bridge_config=None):
        client = _FakeClient([update])
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": True, "default_cwd": "/tmp"}
        bridge_config = bridge_config if bridge_config is not None else {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}
        seen_members = {}
        with mock.patch.object(bot_module, "save_offset"), \
                mock.patch.object(bot_module, "save_bridge_config"), \
                mock.patch.object(bot_module, "save_seen_members"):
            exit_code = bot_module.poll_once(client, config, bridge_config, allowlist or set(), seen_members)
        return exit_code, bridge_config

    def test_unauthorized_stranger_group_message_discovers_but_does_not_activate(self):
        update = {
            "update_id": 60,
            "message": {
                "message_id": 700,
                "date": 1700000000,
                "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
                "from": {"id": 555000111, "is_bot": False, "username": "stranger"},
                "text": "hi everyone, join my unrelated group",
            },
        }
        exit_code, bridge_config = self._run(update)

        self.assertEqual(exit_code, 0)
        # Discovery metadata is still recorded (harmless, zero-setup UX
        # preserved) ...
        self.assertIn(str(GROUP_CHAT_ID), bridge_config.get("discovered_groups", {}))
        # ... but a message that never passed the relay gate must NEVER be
        # able to set active_group_chat_id.
        self.assertNotIn("active_group_chat_id", bridge_config)

    def test_founder_group_message_that_passes_the_gate_activates(self):
        text = f"@{BOT_USERNAME} status?"
        update = {
            "update_id": 61,
            "message": {
                "message_id": 701,
                "date": 1700000001,
                "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
                "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
                "text": text,
                "entities": [{"type": "mention", "offset": 0, "length": len(BOT_USERNAME) + 1}],
            },
        }
        exit_code, bridge_config = self._run(update)

        self.assertEqual(exit_code, 0)
        self.assertEqual(bridge_config.get("active_group_chat_id"), GROUP_CHAT_ID)

    def test_stranger_message_in_a_different_group_does_not_steal_an_already_active_group(self):
        update = {
            "update_id": 62,
            "message": {
                "message_id": 702,
                "date": 1700000002,
                "chat": {"id": -1, "type": "group", "title": "Some Other Group"},
                "from": {"id": 555000111, "is_bot": False, "username": "stranger"},
                "text": "spam message",
            },
        }
        bridge_config = {"bot_id": BOT_ID, "bot_username": BOT_USERNAME, "active_group_chat_id": GROUP_CHAT_ID}
        exit_code, bridge_config = self._run(update, bridge_config=bridge_config)

        self.assertEqual(exit_code, 0)
        self.assertEqual(bridge_config["active_group_chat_id"], GROUP_CHAT_ID)


def _photo_update(update_id, message_id, caption=None, chat_id=FOUNDER_CHAT_ID):
    message = {
        "message_id": message_id,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": chat_id, "is_bot": False, "username": "founder"},
        "photo": [
            {"file_id": "small1", "file_unique_id": "us1", "width": 90, "height": 90, "file_size": 1000},
            {"file_id": "large1", "file_unique_id": "ul1", "width": 1280, "height": 1280, "file_size": 90000},
        ],
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": update_id, "message": message}


def _document_update(update_id, message_id, mime_type, chat_id=FOUNDER_CHAT_ID, caption=None, file_name="file.bin"):
    message = {
        "message_id": message_id,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": chat_id, "is_bot": False, "username": "founder"},
        "document": {"file_id": "doc1", "file_name": file_name, "mime_type": mime_type},
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": update_id, "message": message}


def _voice_update(update_id, message_id, chat_id=FOUNDER_CHAT_ID, duration=12):
    message = {
        "message_id": message_id,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": chat_id, "is_bot": False, "username": "founder"},
        "voice": {"file_id": "voice1", "mime_type": "audio/ogg", "duration": duration, "file_size": 5000},
    }
    return {"update_id": update_id, "message": message}


def _group_photo_update(update_id, message_id, from_id, from_username="stranger"):
    message = {
        "message_id": message_id,
        "date": 1700000000,
        "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
        "from": {"id": from_id, "is_bot": False, "username": from_username},
        "photo": [{"file_id": "grouppic1", "file_unique_id": "gu1", "width": 800, "height": 800}],
    }
    return {"update_id": update_id, "message": message}


def _text_update(update_id, message_id, text, chat_id=FOUNDER_CHAT_ID):
    message = {
        "message_id": message_id,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": chat_id, "is_bot": False, "username": "founder"},
        "text": text,
    }
    return {"update_id": update_id, "message": message}


class MediaRelayTests(unittest.TestCase):
    """Integration-ish tests through bot.poll_once(): confirm media handling
    in RELAY_MODE downloads the file, writes a `media` block into
    relay-inbox.jsonl with the caption as `text`, and that image kinds
    (photo, or an image-mime document) additionally get a `photo_path`
    convenience field pointing at the same downloaded file - the merge of
    the two forks' photo-relay and general-media-relay behaviors into one
    path. Everything else (non-media documents' mime type, plain text,
    RELAY_MODE off, unauthorized senders) is unaffected.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.relay_inbox_file = tmp_path / "relay-inbox.jsonl"
        self.media_inbox_dir = tmp_path / "media-inbox"

        patches = [
            mock.patch.object(bot_module, "RELAY_INBOX_FILE", self.relay_inbox_file),
            mock.patch.object(bot_module, "MEDIA_INBOX_DIR", self.media_inbox_dir),
            mock.patch.object(bot_module, "save_offset"),
            mock.patch.object(bot_module, "save_bridge_config"),
            mock.patch.object(bot_module, "save_seen_members"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmpdir.cleanup)

    def _run_poll(self, client, allowlist=None):
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": True, "default_cwd": "/tmp"}
        bridge_config = {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}
        exit_code = bot_module.poll_once(
            client, config, bridge_config, allowlist=allowlist or set(), seen_members={}
        )
        return exit_code

    def _read_records(self):
        if not self.relay_inbox_file.exists():
            return []
        lines = self.relay_inbox_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def _fake_download(self, remote_file_path="voice/file_1.oga", payload=b"fake-media-bytes"):
        """Patch bot.resolve_telegram_file_path/download_telegram_file so no
        real network call is made; download_telegram_file writes a small
        fixed payload so tests can assert a file actually landed on disk.
        """
        def _fake_download_telegram_file(client, remote_path, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(payload)

        return (
            mock.patch.object(bot_module, "resolve_telegram_file_path", return_value=remote_file_path),
            mock.patch.object(bot_module, "download_telegram_file", side_effect=_fake_download_telegram_file),
        )

    def test_photo_with_caption_is_relayed_with_media_and_photo_path(self):
        client = _FakeClient([_photo_update(1, 900, caption="check this out")])
        p1, p2 = self._fake_download(remote_file_path="photos/file_10.jpg")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["text"], "check this out")
        self.assertEqual(record["media"]["kind"], "photo")
        self.assertTrue(Path(record["media"]["path"]).exists())
        self.assertIn("photo_path", record)
        self.assertEqual(record["photo_path"], record["media"]["path"])

    def test_photo_without_caption_is_relayed_not_dropped(self):
        client = _FakeClient([_photo_update(2, 901, caption=None)])
        p1, p2 = self._fake_download(remote_file_path="photos/file_11.jpg")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["text"], "")
        self.assertIn("photo_path", records[0])

    def test_image_document_gets_photo_path_like_a_photo(self):
        client = _FakeClient(
            [_document_update(3, 902, mime_type="image/png", caption="scanned doc", file_name="scan.png")]
        )
        p1, p2 = self._fake_download(remote_file_path="documents/scan.png")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["text"], "scanned doc")
        self.assertEqual(record["media"]["kind"], "document")
        self.assertIn("photo_path", record)
        self.assertEqual(record["photo_path"], record["media"]["path"])

    def test_non_image_document_has_media_but_no_photo_path(self):
        client = _FakeClient(
            [_document_update(4, 903, mime_type="application/pdf", caption="a report", file_name="report.pdf")]
        )
        p1, p2 = self._fake_download(remote_file_path="documents/report.pdf")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["media"]["kind"], "document")
        self.assertNotIn("photo_path", record)

    def test_voice_message_is_relayed_with_media_block_and_no_photo_path(self):
        client = _FakeClient([_voice_update(5, 904, duration=17)])
        p1, p2 = self._fake_download(remote_file_path="voice/file_5.oga")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["media"]["kind"], "voice")
        self.assertEqual(record["media"]["duration"], 17)
        self.assertNotIn("photo_path", record)
        self.assertEqual(record["note"], bot_module.UNTRUSTED_MEDIA_NOTE)

    def test_plain_text_message_is_unaffected(self):
        client = _FakeClient([_text_update(6, 905, text="hello there")])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        # The original four-field shape (ts/chat_id/message_id/text) must
        # keep meaning exactly what it always meant for a plain text DM -
        # group-support/media fields are additive, never a replacement, and
        # a consumer written against the pre-merge kit's relay-inbox.jsonl
        # shape must still work unmodified.
        self.assertIn("ts", record)
        self.assertIsInstance(record["ts"], str)
        self.assertTrue(record["ts"])  # non-empty
        self.assertEqual(record["chat_id"], FOUNDER_CHAT_ID)
        self.assertEqual(record["message_id"], 905)
        self.assertEqual(record["text"], "hello there")
        self.assertNotIn("media", record)
        self.assertNotIn("photo_path", record)
        self.assertNotIn("reply_to", record)  # not a reply - field must be absent, not null

    def test_text_message_that_is_a_reply_carries_reply_to(self):
        message = {
            "message_id": 950,
            "date": 1700000000,
            "chat": {"id": FOUNDER_CHAT_ID, "type": "private"},
            "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
            "text": "yes, that one",
            "reply_to_message": {
                "message_id": 940,
                "from": {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
                "text": "Which deploy do you mean?",
            },
        }
        client = _FakeClient([{"update_id": 70, "message": message}])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIn("reply_to", record)
        self.assertEqual(record["reply_to"]["message_id"], 940)
        self.assertEqual(record["reply_to"]["text_prefix"], "Which deploy do you mean?")

    def test_reply_to_text_prefix_is_truncated_to_120_chars(self):
        long_text = "x" * 500
        message = {
            "message_id": 951,
            "date": 1700000000,
            "chat": {"id": FOUNDER_CHAT_ID, "type": "private"},
            "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
            "text": "replying to the long one",
            "reply_to_message": {"message_id": 941, "from": {"id": BOT_ID, "is_bot": True}, "text": long_text},
        }
        client = _FakeClient([{"update_id": 71, "message": message}])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        record = self._read_records()[0]
        self.assertEqual(len(record["reply_to"]["text_prefix"]), 120)
        self.assertEqual(record["reply_to"]["text_prefix"], "x" * 120)

    def test_svg_document_has_media_but_no_photo_path(self):
        """SVG is markup, not a raster screenshot - it must NOT get the
        photo_path convenience field even though its mime_type starts with
        image/ (see bot.is_image_media()/NON_RASTER_IMAGE_MIME_TYPES).
        """
        client = _FakeClient(
            [_document_update(20, 950, mime_type="image/svg+xml", caption="a diagram", file_name="diagram.svg")]
        )
        p1, p2 = self._fake_download(remote_file_path="documents/diagram.svg")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["media"]["kind"], "document")
        self.assertNotIn("photo_path", record)

    def test_same_message_id_different_chats_produce_distinct_files_and_records(self):
        """Regression test for a real collision: Telegram message_ids are
        per-CHAT sequential, not global, so a DM and a group message can
        legitimately share the same message_id on the same day. Before the
        <date>-<chat_id>-<message_id> naming fix, both downloads landed at
        the same <date>-<message_id> path and the second write silently
        clobbered the first (data loss - the earlier sender's file was
        destroyed, and both relay records pointed at whatever was left).
        """
        dm_update = _photo_update(1, 42, caption="from dm", chat_id=FOUNDER_CHAT_ID)
        group_message = {
            "message_id": 42,
            "date": 1700000000,
            "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
            "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
            "reply_to_message": {
                "message_id": 0,
                "from": {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
                "text": "(bot's earlier message)",
            },
            "photo": [{"file_id": "groupfile1", "file_unique_id": "gu1", "width": 800, "height": 800}],
            "caption": "from group",
        }
        group_update = {"update_id": 2, "message": group_message}

        client = _FakeClient([dm_update, group_update])

        def _fake_download_telegram_file(client_, remote_path, dest_path):
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            # Content is derived from the destination filename itself, so a
            # collision (the second download overwriting the first) would
            # leave the first file's content wrong - this is exactly the
            # "one sender's image destroyed" symptom the bug reproduction
            # described.
            dest_path.write_bytes(f"payload-for-{dest_path.name}".encode())

        with mock.patch.object(bot_module, "resolve_telegram_file_path", return_value="photos/file_1.jpg"), \
                mock.patch.object(bot_module, "download_telegram_file", side_effect=_fake_download_telegram_file):
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 2)

        paths = [Path(r["media"]["path"]) for r in records]
        self.assertEqual(
            len({str(p) for p in paths}), 2,
            "expected two distinct file paths for the same message_id in different chats, got a collision",
        )
        for record, path in zip(records, paths):
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), f"payload-for-{path.name}".encode())
            self.assertEqual(record["photo_path"], str(path))

        # Both filenames must encode their OWN chat id, not just date +
        # message_id - the actual fix, not just "paths happen to differ".
        self.assertIn(str(FOUNDER_CHAT_ID), paths[0].name)
        self.assertIn(bot_module.sanitize_chat_id_for_filename(GROUP_CHAT_ID), paths[1].name)
        self.assertTrue(paths[1].name.split("-")[1].startswith("g"))  # negative group id -> 'g' prefix

    def test_failed_download_sends_failure_reply_and_writes_no_record(self):
        client = _FakeClient([_photo_update(7, 906, caption="please still send this")])
        with mock.patch.object(
            bot_module, "resolve_telegram_file_path",
            side_effect=requests.exceptions.RequestException("simulated failure"),
        ):
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        self.assertEqual(self._read_records(), [])
        self.assertIn((str(FOUNDER_CHAT_ID), 906, bot_module.REACTION_FAIL), [
            (str(c), m, e) for c, m, e in client.reactions
        ])
        self.assertTrue(any(
            bot_module.MEDIA_DOWNLOAD_FAILED_REPLY == text for _chat, text in client.sent_messages
        ))

    def test_media_dropped_outside_relay_mode(self):
        client = _FakeClient([_voice_update(8, 907)])
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": False, "default_cwd": "/tmp"}
        bridge_config = {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}
        with mock.patch.object(bot_module, "save_offset"), \
                mock.patch.object(bot_module, "save_bridge_config"), \
                mock.patch.object(bot_module, "save_seen_members"):
            exit_code = bot_module.poll_once(client, config, bridge_config, allowlist=set(), seen_members={})

        self.assertEqual(exit_code, 0)
        self.assertEqual(self._read_records(), [])
        self.assertEqual(client.reactions, [])  # never even 👀-reacted

    def test_media_from_unauthorized_group_sender_is_never_downloaded(self):
        """Group gating (evaluate_incoming_message) runs BEFORE media
        handling - an unauthorized/non-mentioning group sender's photo must
        never trigger a download attempt at all, not just never get
        relayed. This is the group-support + media-relay merge point.
        """
        client = _FakeClient([_group_photo_update(9, 908, from_id=444555666)])
        with mock.patch.object(bot_module, "resolve_telegram_file_path") as mock_resolve:
            exit_code = self._run_poll(client, allowlist=set())

        self.assertEqual(exit_code, 0)
        self.assertEqual(self._read_records(), [])
        mock_resolve.assert_not_called()
        self.assertEqual(client.reactions, [])

    def test_media_message_that_is_a_reply_also_carries_reply_to(self):
        """reply_to threading isn't text-only - relay_media() must carry the
        same optional field when a photo/voice/etc. message is itself a
        reply, using the same shape relay_message() does.
        """
        message = {
            "message_id": 909,
            "date": 1700000000,
            "chat": {"id": FOUNDER_CHAT_ID, "type": "private"},
            "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
            "photo": [{"file_id": "replyphoto1", "file_unique_id": "rp1", "width": 800, "height": 800}],
            "caption": "here's the screenshot",
            "reply_to_message": {
                "message_id": 899,
                "from": {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
                "text": "Can you send a screenshot of the error?",
            },
        }
        client = _FakeClient([{"update_id": 10, "message": message}])
        p1, p2 = self._fake_download(remote_file_path="photos/reply.jpg")
        with p1, p2:
            exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIn("media", record)
        self.assertIn("reply_to", record)
        self.assertEqual(record["reply_to"]["message_id"], 899)
        self.assertEqual(record["reply_to"]["text_prefix"], "Can you send a screenshot of the error?")


class LongTextArtifactTests(unittest.TestCase):
    """Integration-ish tests through bot.poll_once(): confirm the
    downstream-truncation defense - a plain-text message over
    LONG_TEXT_ARTIFACT_THRESHOLD_CHARS gets its full body written to a file
    in MEDIA_INBOX_DIR (the same directory media downloads already use) and
    referenced via an additive `text_path` field on its relay-inbox.jsonl
    record - see write_inbound_text_artifact()/relay_message() in bot.py.

    Same "integration-ish through poll_once(), redirect state paths to a
    temp dir" shape as MediaRelayTests above, since the feature reuses
    MEDIA_INBOX_DIR rather than a directory of its own.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)
        self.relay_inbox_file = tmp_path / "relay-inbox.jsonl"
        self.media_inbox_dir = tmp_path / "media-inbox"

        patches = [
            mock.patch.object(bot_module, "RELAY_INBOX_FILE", self.relay_inbox_file),
            mock.patch.object(bot_module, "MEDIA_INBOX_DIR", self.media_inbox_dir),
            mock.patch.object(bot_module, "save_offset"),
            mock.patch.object(bot_module, "save_bridge_config"),
            mock.patch.object(bot_module, "save_seen_members"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmpdir.cleanup)

    def _run_poll(self, client):
        config = {"chat_id": str(FOUNDER_CHAT_ID), "relay_mode": True, "default_cwd": "/tmp"}
        bridge_config = {"bot_id": BOT_ID, "bot_username": BOT_USERNAME}
        return bot_module.poll_once(
            client, config, bridge_config, allowlist=set(), seen_members={}
        )

    def _read_records(self):
        if not self.relay_inbox_file.exists():
            return []
        lines = self.relay_inbox_file.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_short_message_gets_no_text_path_and_is_byte_identical_in_shape(self):
        """Under the threshold: `text_path` must be entirely absent, and
        every other field must be exactly what MediaRelayTests'
        test_plain_text_message_is_unaffected already asserts for a plain
        text DM - proving this feature is additive, not a reshape.
        """
        client = _FakeClient([_text_update(100, 1000, text="hello there")])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIn("ts", record)
        self.assertIsInstance(record["ts"], str)
        self.assertTrue(record["ts"])
        self.assertEqual(record["chat_id"], FOUNDER_CHAT_ID)
        self.assertEqual(record["message_id"], 1000)
        self.assertEqual(record["text"], "hello there")
        self.assertEqual(record["chat_type"], "private")
        self.assertEqual(record["from_id"], FOUNDER_CHAT_ID)
        self.assertEqual(record["from_name"], "founder")
        self.assertFalse(record["is_reply_to_bot"])
        self.assertFalse(record["mentioned"])
        self.assertNotIn("media", record)
        self.assertNotIn("photo_path", record)
        self.assertNotIn("reply_to", record)
        self.assertNotIn("text_path", record)
        # Exactly the 9-key shape MediaRelayTests' short-text test expects -
        # nothing added, nothing removed, for a message under the threshold.
        self.assertEqual(
            set(record.keys()),
            {
                "ts", "chat_id", "message_id", "text", "chat_type",
                "from_id", "from_name", "is_reply_to_bot", "mentioned",
            },
        )
        # No artifact directory traffic at all for a short message.
        self.assertFalse(self.media_inbox_dir.exists())

    def test_message_exactly_at_threshold_gets_no_text_path(self):
        """Boundary check: exactly LONG_TEXT_ARTIFACT_THRESHOLD_CHARS chars
        is NOT "over" the threshold (relay_message() uses a strict `>`), so
        no artifact should be written.
        """
        text = "y" * bot_module.LONG_TEXT_ARTIFACT_THRESHOLD_CHARS
        client = _FakeClient([_text_update(101, 1001, text=text)])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        record = self._read_records()[0]
        self.assertEqual(record["text"], text)
        self.assertNotIn("text_path", record)

    def test_long_multibyte_message_writes_full_text_artifact_and_references_it(self):
        """Over the threshold, with multibyte characters (so a byte-vs-
        character counting bug would surface): the inline `text` field must
        still carry the complete text (bot.py itself never truncates it -
        the truncation this defends against happens in a layer above this
        bridge), AND the referenced file must hold the exact same complete
        text, char for char.
        """
        unit = "café 日本語 \U0001F600 "  # accents, CJK, emoji
        text = unit * (bot_module.LONG_TEXT_ARTIFACT_THRESHOLD_CHARS // len(unit) + 5)
        self.assertGreater(len(text), bot_module.LONG_TEXT_ARTIFACT_THRESHOLD_CHARS)

        client = _FakeClient([_text_update(102, 1002, text=text)])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["text"], text)
        self.assertIn("text_path", record)

        artifact_path = Path(record["text_path"])
        self.assertTrue(artifact_path.exists())
        self.assertEqual(artifact_path.read_text(encoding="utf-8"), text)
        self.assertEqual(len(artifact_path.read_text(encoding="utf-8")), len(text))

        # Same naming convention as media downloads: <YYYYMMDD>-<chat_id>-<message_id>.txt
        date_str = datetime.now().strftime("%Y%m%d")
        expected_name = f"{date_str}-{FOUNDER_CHAT_ID}-1002.txt"
        self.assertEqual(artifact_path.name, expected_name)
        self.assertEqual(artifact_path.parent, self.media_inbox_dir)

    def test_long_message_in_a_group_chat_gets_g_prefixed_filename(self):
        """Same chat-id sanitization relay_media() relies on: a negative
        group chat id must render with a 'g' prefix rather than a literal
        leading '-' in the artifact filename.
        """
        text = "z" * (bot_module.LONG_TEXT_ARTIFACT_THRESHOLD_CHARS + 50)
        message = {
            "message_id": 1003,
            "date": 1700000000,
            "chat": {"id": GROUP_CHAT_ID, "type": "group", "title": GROUP_TITLE},
            "from": {"id": FOUNDER_CHAT_ID, "is_bot": False, "username": "founder"},
            "text": text,
            "reply_to_message": {
                "message_id": 0,
                "from": {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME},
                "text": "(bot's earlier message)",
            },
        }
        client = _FakeClient([{"update_id": 103, "message": message}])
        exit_code = self._run_poll(client)

        self.assertEqual(exit_code, 0)
        record = self._read_records()[0]
        self.assertIn("text_path", record)
        artifact_path = Path(record["text_path"])
        self.assertTrue(artifact_path.name.startswith(
            datetime.now().strftime("%Y%m%d") + "-g"
        ))
        self.assertEqual(artifact_path.read_text(encoding="utf-8"), text)

    def test_artifact_write_failure_degrades_gracefully_event_still_produced(self):
        """Force the write to fail (occupy MEDIA_INBOX_DIR's path with a
        plain file, so mkdir(parents=True, exist_ok=True) raises OSError)
        and confirm poll_once() neither raises nor drops the message - the
        relay record is still produced, just without `text_path`. This is
        the "degrade gracefully, don't kill the poll cycle" requirement.
        """
        # A regular file sitting where the directory should be - mkdir()
        # with exist_ok=True still raises FileExistsError (an OSError
        # subclass) when the existing entry isn't itself a directory.
        self.media_inbox_dir.parent.mkdir(parents=True, exist_ok=True)
        self.media_inbox_dir.write_bytes(b"occupied by a plain file, not a directory")

        text = "w" * (bot_module.LONG_TEXT_ARTIFACT_THRESHOLD_CHARS + 20)
        client = _FakeClient([_text_update(104, 1004, text=text)])

        exit_code = self._run_poll(client)  # must not raise

        self.assertEqual(exit_code, 0)
        records = self._read_records()
        self.assertEqual(len(records), 1)
        record = records[0]
        # The event is still produced, in full, with the untouched inline
        # text - just no text_path, since the artifact write failed.
        self.assertEqual(record["text"], text)
        self.assertNotIn("text_path", record)
        self.assertEqual(record["message_id"], 1004)


class WriteInboundTextArtifactTests(unittest.TestCase):
    """Direct unit tests for bot.write_inbound_text_artifact() itself. This
    function does not check the length threshold (relay_message() does that
    before calling it) - these tests call it directly regardless of length.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.media_inbox_dir = Path(self._tmpdir.name) / "media-inbox"
        patcher = mock.patch.object(bot_module, "MEDIA_INBOX_DIR", self.media_inbox_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)

    def test_writes_full_text_and_returns_path(self):
        result = bot_module.write_inbound_text_artifact(FOUNDER_CHAT_ID, 4242, "the full text body")
        self.assertIsNotNone(result)
        path = Path(result)
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(encoding="utf-8"), "the full text body")
        self.assertEqual(path.suffix, ".txt")
        self.assertEqual(path.parent, self.media_inbox_dir)

    def test_no_leftover_tmp_file_after_a_successful_write(self):
        result = bot_module.write_inbound_text_artifact(FOUNDER_CHAT_ID, 4243, "another body")
        path = Path(result)
        tmp_path = path.with_name(path.name + ".tmp")
        self.assertFalse(tmp_path.exists())

    def test_returns_none_and_logs_on_write_failure_without_raising(self):
        self.media_inbox_dir.parent.mkdir(parents=True, exist_ok=True)
        self.media_inbox_dir.write_bytes(b"occupied")
        result = bot_module.write_inbound_text_artifact(FOUNDER_CHAT_ID, 4244, "won't be written")
        self.assertIsNone(result)

    def test_refuses_to_write_the_live_media_inbox_dir_under_test_mode(self):
        """The same production-state write guard media downloads already
        get (see ProductionStateWriteGuardTests) must also cover this
        function - it writes into the same MEDIA_INBOX_DIR.
        """
        with mock.patch.object(bot_module, "MEDIA_INBOX_DIR", bot_module.SCRIPT_DIR / "media-inbox"):
            with self.assertRaises(RuntimeError):
                bot_module.write_inbound_text_artifact(FOUNDER_CHAT_ID, 4245, "x")


class ExtractMediaTests(unittest.TestCase):
    """Pure-function tests for bot.extract_media() and bot.is_image_media() -
    no I/O, no Telegram calls; just message-shape inspection.
    """

    def test_photo_message_returns_largest_size_file_id(self):
        message = {
            "photo": [
                {"file_id": "small", "file_unique_id": "us", "width": 90, "height": 90},
                {"file_id": "medium", "file_unique_id": "um", "width": 320, "height": 320},
                {"file_id": "large", "file_unique_id": "ul", "width": 1280, "height": 1280},
            ],
            "caption": "look at this",
        }
        media = bot_module.extract_media(message)
        self.assertEqual(media["kind"], "photo")
        self.assertEqual(media["file_id"], "large")
        self.assertTrue(bot_module.is_image_media(media))

    def test_image_mime_document_is_detected_as_image(self):
        message = {
            "document": {
                "file_id": "doc123",
                "file_name": "photo.png",
                "mime_type": "image/png",
            },
        }
        media = bot_module.extract_media(message)
        self.assertEqual(media["kind"], "document")
        self.assertEqual(media["file_id"], "doc123")
        self.assertTrue(bot_module.is_image_media(media))

    def test_non_image_mime_document_is_not_image(self):
        message = {
            "document": {
                "file_id": "doc456",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
            },
        }
        media = bot_module.extract_media(message)
        self.assertEqual(media["kind"], "document")
        self.assertFalse(bot_module.is_image_media(media))

    def test_voice_audio_video_video_note_are_never_image(self):
        for key, extra in (
            ("voice", {"file_id": "v1", "duration": 5}),
            ("audio", {"file_id": "a1", "duration": 5}),
            ("video", {"file_id": "vd1", "duration": 5}),
            ("video_note", {"file_id": "vn1", "duration": 5}),
        ):
            message = {key: extra}
            media = bot_module.extract_media(message)
            self.assertEqual(media["kind"], key)
            self.assertFalse(bot_module.is_image_media(media), key)

    def test_plain_text_message_has_no_media(self):
        message = {"text": "just words"}
        self.assertIsNone(bot_module.extract_media(message))

    def test_svg_mime_document_is_not_image_despite_image_prefix(self):
        media = {"kind": "document", "file_id": "svg1", "mime": "image/svg+xml", "size": 100, "duration": None}
        self.assertFalse(bot_module.is_image_media(media))

    def test_svg_mime_is_case_insensitive(self):
        media = {"kind": "document", "file_id": "svg2", "mime": "Image/SVG+XML", "size": 100, "duration": None}
        self.assertFalse(bot_module.is_image_media(media))


class SanitizeChatIdForFilenameTests(unittest.TestCase):
    """Pure-function tests for bot.sanitize_chat_id_for_filename() - no I/O."""

    def test_positive_private_chat_id_passes_through_unchanged(self):
        self.assertEqual(bot_module.sanitize_chat_id_for_filename(1000000001), "1000000001")

    def test_negative_group_chat_id_gets_g_prefix_not_a_literal_minus(self):
        self.assertEqual(bot_module.sanitize_chat_id_for_filename(-100999888), "g100999888")

    def test_result_never_starts_with_a_hyphen(self):
        for chat_id in (1000000001, -100999888, -1, 0):
            self.assertFalse(bot_module.sanitize_chat_id_for_filename(chat_id).startswith("-"))


class ExtractReplyToTests(unittest.TestCase):
    """Pure-function tests for bot.extract_reply_to() - no I/O, no Telegram
    calls; just message-shape inspection. See relay_message()/relay_media()
    (and MediaRelayTests/test_text_message_that_is_a_reply_carries_reply_to
    etc. above) for the integration-level coverage confirming this actually
    lands in a relay-inbox.jsonl record as the optional `reply_to` field.
    """

    def test_non_reply_message_returns_none(self):
        message = {"text": "just a regular message"}
        self.assertIsNone(bot_module.extract_reply_to(message))

    def test_reply_to_a_text_message_carries_id_and_text_prefix(self):
        message = {
            "text": "yes that one",
            "reply_to_message": {"message_id": 42, "text": "Which one do you mean?"},
        }
        reply_to = bot_module.extract_reply_to(message)
        self.assertEqual(reply_to, {"message_id": 42, "text_prefix": "Which one do you mean?"})

    def test_reply_to_a_media_message_falls_back_to_caption(self):
        # A quoted message with no `text` (e.g. a photo) still has a caption
        # if one was attached - use that as the text_prefix source instead.
        message = {
            "text": "look at this",
            "reply_to_message": {"message_id": 43, "caption": "check out this chart"},
        }
        reply_to = bot_module.extract_reply_to(message)
        self.assertEqual(reply_to["text_prefix"], "check out this chart")

    def test_reply_to_a_message_with_neither_text_nor_caption_gets_empty_prefix(self):
        # E.g. replying to a bare photo with no caption at all - message_id
        # is still meaningful even though there's no text to preview.
        message = {
            "text": "nice",
            "reply_to_message": {"message_id": 44},
        }
        reply_to = bot_module.extract_reply_to(message)
        self.assertEqual(reply_to, {"message_id": 44, "text_prefix": ""})

    def test_text_prefix_is_truncated_to_120_chars(self):
        long_text = "a" * 300
        message = {"text": "reply", "reply_to_message": {"message_id": 45, "text": long_text}}
        reply_to = bot_module.extract_reply_to(message)
        self.assertEqual(len(reply_to["text_prefix"]), bot_module.REPLY_TEXT_PREFIX_CHARS)
        self.assertEqual(reply_to["text_prefix"], "a" * 120)

    def test_short_text_is_not_padded_or_altered(self):
        message = {"text": "reply", "reply_to_message": {"message_id": 46, "text": "short"}}
        reply_to = bot_module.extract_reply_to(message)
        self.assertEqual(reply_to["text_prefix"], "short")


if __name__ == "__main__":
    unittest.main(verbosity=2)
