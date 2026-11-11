#!/usr/bin/env python3
"""
test_founder_ux.py - Offline tests for the founder-facing Telegram features:

- idle_status.py: silence-triggered status post, edit-only-on-change,
  delete on the next exchange - unit cases plus a randomized state-machine
  sweep checked against invariants (never two live posts, a post never
  outlives an exchange, nothing posted before the silence threshold, never
  an edit without a content change).
- ask.py: question cards (inline keyboard), --reply-to threading, --clear.
- bot.py: button presses (authorization, stamping, relay record, stale
  card), clearing a card's buttons when the founder replies to it, the
  exchange marker, allowed_updates.
- notify.sh / send-file.sh: --reply-to and the exchange-marker touch,
  against a fake curl on PATH (no network, no real token).

Run:
    python3 -m unittest test_founder_ux.py -v
"""

import io
import json
import os
import random
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ["TELEGRAM_BRIDGE_TEST_MODE"] = "1"

import logging  # noqa: E402

import ask  # noqa: E402
import configure_bridge  # noqa: E402
import bot as bot_module  # noqa: E402
import idle_status  # noqa: E402

# bot.py's import attaches a FileHandler on the real bot.log; detach it so
# tests never write synthetic lines into the production log.
for _h in list(logging.getLogger().handlers):
    logging.getLogger().removeHandler(_h)
logging.getLogger().addHandler(logging.NullHandler())

SCRIPT_DIR = Path(__file__).resolve().parent
FAKE_TOKEN = "123456:TESTtokenTESTtokenTESTtoken"
FOUNDER = 4242
BOT_ID = 999


class FakeApi:
    """Records Bot API calls; answers from a scripted queue or a default."""

    def __init__(self):
        self.calls = []
        self.next_id = 100
        self.responses = {}  # method -> list of responses (dict or Exception)

    def __call__(self, method, payload):
        self.calls.append((method, payload))
        queue = self.responses.get(method)
        if queue:
            resp = queue.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        if method == "sendMessage":
            self.next_id += 1
            return {"ok": True, "result": {"message_id": self.next_id}}
        return {"ok": True, "result": True}

    def methods(self):
        return [m for m, _ in self.calls]


def settings(**over):
    base = idle_status.load_settings({})
    base.update(over)
    return base


class IdleStatusBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.state = d / "idle-status.json"
        self.exchange = d / ".last-exchange"
        self.api = FakeApi()
        self.t0 = 1_700_000_000.0
        self.set_exchange(self.t0)

    def tearDown(self):
        self.tmp.cleanup()

    def set_exchange(self, ts):
        self.exchange.touch()
        os.utime(self.exchange, (ts, ts))

    def tick(self, at, s=None):
        return idle_status.tick(self.api, FOUNDER, s or settings(), now=at,
                                state_path=self.state, exchange_path=self.exchange)


class IdleStatusTests(IdleStatusBase):
    def test_defaults_are_45_and_40_minutes_silent(self):
        s = idle_status.load_settings({})
        self.assertEqual(45 * 60, s["after_seconds"])
        self.assertEqual(40 * 60, s["refresh_seconds"])
        self.assertTrue(s["silent"])
        self.assertTrue(s["enabled"])

    def test_nothing_before_threshold_then_one_silent_post(self):
        self.assertEqual("quiet_not_long_enough", self.tick(self.t0 + 44 * 60))
        self.assertEqual([], self.api.calls)
        self.assertEqual("posted", self.tick(self.t0 + 45 * 60))
        method, payload = self.api.calls[-1]
        self.assertEqual("sendMessage", method)
        self.assertTrue(payload["disable_notification"])
        self.assertEqual(FOUNDER, payload["chat_id"])
        self.assertEqual("waiting", self.tick(self.t0 + 46 * 60))
        self.assertEqual(1, self.api.methods().count("sendMessage"))

    def test_refresh_edits_only_when_status_changed(self):
        status = Path(self.tmp.name) / "STATE.md"
        status.write_text("## Current\n- Phase: Build. 2 agents.\n## Agent log\nold\n")
        s = settings(status_files=[str(status)])
        self.tick(self.t0 + 45 * 60, s)
        self.assertIn("2 agents", self.api.calls[-1][1]["text"])
        self.assertNotIn("old", self.api.calls[-1][1]["text"])
        # Unchanged after the refresh interval: no edit.
        self.assertEqual("unchanged", self.tick(self.t0 + 86 * 60, s))
        self.assertNotIn("editMessageText", self.api.methods())
        # Changed: exactly one edit of the same post.
        status.write_text("## Current\n- Phase: Build. 3 agents.\n")
        self.assertEqual("waiting", self.tick(self.t0 + 100 * 60, s))
        self.assertEqual("edited", self.tick(self.t0 + 127 * 60, s))
        method, payload = self.api.calls[-1]
        self.assertEqual("editMessageText", method)
        self.assertEqual(101, payload["message_id"])
        self.assertIn("3 agents", payload["text"])

    def test_exchange_deletes_the_post(self):
        self.tick(self.t0 + 45 * 60)
        self.set_exchange(self.t0 + 50 * 60)
        self.assertEqual("deleted", self.tick(self.t0 + 50 * 60 + 5))
        self.assertEqual(("deleteMessage", {"chat_id": FOUNDER, "message_id": 101}), self.api.calls[-1])
        self.assertEqual({}, idle_status.load_state(self.state))
        # New silence clock starts at the exchange.
        self.assertEqual("quiet_not_long_enough", self.tick(self.t0 + 90 * 60))
        self.assertEqual("posted", self.tick(self.t0 + 95 * 60))

    def test_exchange_in_same_second_as_post_on_coarse_mtime_fs(self):
        post_at = self.t0 + 45 * 60 + 0.7
        self.assertEqual("posted", self.tick(post_at))
        # A filesystem with 1s mtime resolution floors the exchange time.
        self.set_exchange(float(int(post_at)))
        self.assertEqual("deleted", self.tick(post_at + 0.2))

    def test_settings_read_status_commands_list_and_legacy_single(self):
        s = idle_status.load_settings({"STATUS_COMMANDS": "a --root /x status ;; b --root /y status",
                                       "STATUS_COMMAND": "legacy"})
        self.assertEqual(["a --root /x status", "b --root /y status", "legacy"], s["status_commands"])

    def test_delete_network_error_retries(self):
        self.tick(self.t0 + 45 * 60)
        self.set_exchange(self.t0 + 50 * 60)
        self.api.responses["deleteMessage"] = [OSError("down")]
        self.assertEqual("retry_delete", self.tick(self.t0 + 51 * 60))
        self.assertIn("post", idle_status.load_state(self.state))
        self.assertEqual("deleted", self.tick(self.t0 + 52 * 60))

    def test_already_deleted_post_is_dropped(self):
        self.tick(self.t0 + 45 * 60)
        self.set_exchange(self.t0 + 50 * 60)
        self.api.responses["deleteMessage"] = [{"ok": False, "error_code": 400, "description": "Bad Request: message to delete not found"}]
        self.assertEqual("deleted", self.tick(self.t0 + 51 * 60))
        self.assertEqual({}, idle_status.load_state(self.state))

    def test_send_failure_backs_off(self):
        self.api.responses["sendMessage"] = [OSError("down")]
        self.assertEqual("send_failed", self.tick(self.t0 + 45 * 60))
        self.assertEqual("backoff", self.tick(self.t0 + 46 * 60))
        self.assertEqual("posted", self.tick(self.t0 + 51 * 60))

    def test_old_post_is_rotated_before_48h(self):
        self.tick(self.t0 + 45 * 60)
        self.assertEqual("rotated", self.tick(self.t0 + 45 * 60 + idle_status.ROTATE_AFTER_SECONDS))
        self.assertEqual(["sendMessage", "deleteMessage", "sendMessage"], self.api.methods())

    def test_disabling_cleans_up(self):
        self.tick(self.t0 + 45 * 60)
        self.assertEqual("deleted", self.tick(self.t0 + 46 * 60, settings(enabled=False)))
        self.assertEqual("disabled", self.tick(self.t0 + 200 * 60, settings(enabled=False)))

    def test_missing_marker_starts_the_clock_instead_of_posting(self):
        self.exchange.unlink()
        self.assertEqual("init", self.tick(self.t0))
        self.assertTrue(self.exchange.exists())
        self.assertEqual([], self.api.calls)

    def test_command_and_files_combine_and_failures_are_visible(self):
        f = Path(self.tmp.name) / "STATE.md"
        f.write_text("## Current\n- file project busy\n")
        s = settings(status_commands=["printf 'from command'", "printf 'second project'"], status_files=[str(f)])
        self.tick(self.t0 + 45 * 60, s)
        self.assertIn("from command", self.api.calls[-1][1]["text"])
        self.assertIn("file project busy", self.api.calls[-1][1]["text"])
        self.assertIn("second project", self.api.calls[-1][1]["text"])
        body = idle_status.build_status_body(settings(status_commands=["echo boom >&2; exit 3"]))
        self.assertIn("exit 3", body)
        self.assertIn("boom", body)

    def test_no_source_names_the_missing_setting(self):
        self.assertIn("STATUS_FILES", idle_status.build_status_body(settings()))

    def test_long_body_is_truncated_under_telegram_limit(self):
        f = Path(self.tmp.name) / "big.txt"
        f.write_text("x" * 10000)
        body = idle_status.build_status_body(settings(status_files=[str(f)]))
        self.assertLessEqual(len(idle_status.render_post(body, self.t0, self.t0)), 4096)


class IdleStatusPropertyTests(IdleStatusBase):
    """Randomized sweep: arbitrary interleavings of time passing, exchanges,
    status changes and API failures, checked against the invariants."""

    def test_random_sequences_hold_invariants(self):
        rng = random.Random(20261111)
        status = Path(self.tmp.name) / "status.txt"
        for run in range(150):
            if self.state.exists():
                self.state.unlink()
            self.api = FakeApi()
            status.write_text("v0")
            s = settings(status_files=[str(status)])
            now = self.t0
            last_ex = now
            self.set_exchange(now)
            version = 0
            for _ in range(60):
                step = rng.choice(["wait_s", "wait_m", "wait_l", "exchange", "change", "fail_next"])
                if step == "wait_s":
                    now += rng.randint(10, 120)
                elif step == "wait_m":
                    now += rng.randint(5, 30) * 60
                elif step == "wait_l":
                    now += rng.randint(40, 120) * 60
                elif step == "exchange":
                    now += 1
                    last_ex = now
                    self.set_exchange(now)
                elif step == "change":
                    version += 1
                    status.write_text(f"v{version}")
                else:
                    m = rng.choice(["sendMessage", "editMessageText", "deleteMessage"])
                    self.api.responses.setdefault(m, []).append(OSError("transient"))
                before = len(self.api.calls)
                hash_before = (idle_status.load_state(self.state).get("post") or {}).get("hash")
                action = idle_status.tick(self.api, FOUNDER, s, now=now,
                                          state_path=self.state, exchange_path=self.exchange)
                for method, payload in self.api.calls[before:]:
                    if method == "sendMessage":
                        # Never before the silence threshold.
                        self.assertGreaterEqual(now - last_ex, s["after_seconds"], (run, action))
                    if method == "editMessageText":
                        self.assertNotEqual(hash_before, idle_status.body_hash(idle_status.build_status_body(s)),
                                            (run, "edit without a content change"))
                sends = [m for m, _ in self.api.calls[before:]].count("sendMessage")
                self.assertLessEqual(sends, 1, (run, "two posts in one tick"))
                post = idle_status.load_state(self.state).get("post")
                if post and post["posted_at"] < last_ex:
                    # A post may outlive an exchange only while its delete is
                    # being retried after a transient failure.
                    self.assertEqual("retry_delete", action, run)
                    if sends:
                        self.fail((run, "posted while an old post was still live"))

    def test_every_sent_post_is_eventually_deleted_after_an_exchange(self):
        rng = random.Random(7)
        for _ in range(100):
            if self.state.exists():
                self.state.unlink()
            self.api = FakeApi()
            now = self.t0
            self.set_exchange(now)
            for _ in range(rng.randint(1, 20)):
                now += rng.randint(1, 90) * 60
                idle_status.tick(self.api, FOUNDER, settings(), now=now,
                                 state_path=self.state, exchange_path=self.exchange)
            now += 1
            self.set_exchange(now)
            idle_status.tick(self.api, FOUNDER, settings(), now=now + 1,
                             state_path=self.state, exchange_path=self.exchange)
            sent_ids = [100 + i + 1 for i in range([m for m, _ in self.api.calls].count("sendMessage"))]
            deleted = [p["message_id"] for m, p in self.api.calls if m == "deleteMessage"]
            self.assertEqual(sorted(sent_ids), sorted(deleted), "a status post was orphaned")
            self.assertEqual({}, idle_status.load_state(self.state))


class AskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / ".env").write_text(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID={FOUNDER}\n")
        self.patches = [
            mock.patch.object(ask, "ENV_FILE", d / ".env"),
            mock.patch.object(ask, "EXCHANGE_FILE", d / ".last-exchange"),
            mock.patch.object(ask, "BRIDGE_CONFIG_FILE", d / "bridge-config.json"),
        ]
        for p in self.patches:
            p.start()
        self.dir = d
        self.api = FakeApi()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_ask(self, *argv):
        with mock.patch("sys.stdout") as out, mock.patch("sys.stderr") as err:
            code = ask.main(list(argv), api=self.api)
        printed = "".join(c.args[0] for c in out.write.call_args_list)
        errors = "".join(c.args[0] for c in err.write.call_args_list)
        return code, printed, errors

    def test_card_has_one_button_row_per_option_indexed(self):
        code, printed, _ = self.run_ask("Which DB?", "Postgres", "SQLite", "Park this")
        self.assertEqual(0, code)
        method, payload = self.api.calls[-1]
        self.assertEqual("sendMessage", method)
        rows = payload["reply_markup"]["inline_keyboard"]
        self.assertEqual([[{"text": "Postgres", "callback_data": "opt:0"}],
                          [{"text": "SQLite", "callback_data": "opt:1"}],
                          [{"text": "Park this", "callback_data": "opt:2"}]], rows)
        self.assertEqual("101", printed.strip())
        self.assertTrue((self.dir / ".last-exchange").exists())

    def test_reply_to_threads_the_card(self):
        self.run_ask("--reply-to", "55", "Ship?", "Yes", "No")
        self.assertEqual({"message_id": 55, "allow_sending_without_reply": True},
                         self.api.calls[-1][1]["reply_parameters"])

    def test_clear_removes_buttons_and_tolerates_not_modified(self):
        self.assertEqual(0, self.run_ask("--clear", "77")[0])
        self.assertEqual(("editMessageReplyMarkup", {"chat_id": str(FOUNDER), "message_id": 77,
                                                     "reply_markup": {"inline_keyboard": []}}), self.api.calls[-1])
        self.api.responses["editMessageReplyMarkup"] = [{"ok": False, "description": "Bad Request: message is not modified"}]
        self.assertEqual(0, self.run_ask("--clear", "77")[0])
        self.assertFalse((self.dir / ".last-exchange").exists(), "clearing is not an exchange")

    def test_bad_input_is_rejected_without_a_call(self):
        for argv in (["Q"], ["Q", ""], ["Q"] + [f"o{i}" for i in range(9)], ["Q", "x" * 61]):
            code, _, err = self.run_ask(*argv)
            self.assertEqual(1, code, argv)
            self.assertTrue(err)
        self.assertEqual([], self.api.calls)

    def test_api_rejection_and_network_error_exit_1_without_token(self):
        self.api.responses["sendMessage"] = [{"ok": False, "description": "Bad Request: chat not found"},
                                             OSError(f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage failed")]
        code, _, err = self.run_ask("Q", "A")
        self.assertEqual(1, code)
        code, _, err = self.run_ask("Q", "A")
        self.assertEqual(1, code)
        self.assertNotIn(FAKE_TOKEN, err)
        self.assertFalse((self.dir / ".last-exchange").exists())


class FakeClient:
    def __init__(self):
        self.api_calls = []
        self.reactions = []

    def api(self, method, payload):
        self.api_calls.append((method, payload))
        return {"ok": True, "result": True}

    def set_reaction(self, chat_id, message_id, emoji):
        self.reactions.append((chat_id, message_id, emoji))

    def send_message_chunked(self, chat_id, text):
        return True


def card_callback(from_id=FOUNDER, chat_id=FOUNDER, chat_type="private", data="opt:1", markup=True):
    message = {"message_id": 300, "chat": {"id": chat_id, "type": chat_type},
               "text": "Which DB?", "from": {"id": BOT_ID, "is_bot": True}}
    if markup:
        message["reply_markup"] = {"inline_keyboard": [[{"text": "Postgres", "callback_data": "opt:0"}],
                                                       [{"text": "SQLite", "callback_data": "opt:1"}]]}
    return {"id": "cb1", "from": {"id": from_id, "first_name": "Founder"}, "message": message, "data": data}


class BotTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.inbox = d / "relay-inbox.jsonl"
        self.exchange = d / ".last-exchange"
        self.patches = [
            mock.patch.object(bot_module, "RELAY_INBOX_FILE", self.inbox),
            mock.patch.object(bot_module, "EXCHANGE_FILE", self.exchange),
            mock.patch.object(bot_module, "IDLE_STATE_FILE", d / "idle-status.json"),
            mock.patch.object(bot_module, "ANSWERED_CARDS_FILE", d / "answered-cards.json"),
            mock.patch.object(bot_module, "MEDIA_INBOX_DIR", d / "media-inbox"),
            mock.patch.object(bot_module, "save_offset", lambda *_: None),
            mock.patch.object(bot_module, "load_offset", lambda: None),
            mock.patch.object(bot_module, "save_bridge_config", lambda *_: None),
            mock.patch.object(bot_module, "save_seen_members", lambda *_: None),
        ]
        for p in self.patches:
            p.start()
        self.client = FakeClient()
        self.config = {"token": FAKE_TOKEN, "chat_id": str(FOUNDER), "default_cwd": "/", "relay_mode": True}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def records(self):
        if not self.inbox.exists():
            return []
        return [json.loads(line) for line in self.inbox.read_text().splitlines()]


class ButtonPressTests(BotTestBase):
    def test_press_relays_choice_stamps_card_and_marks_exchange(self):
        bot_module.handle_callback_query(self.client, self.config, card_callback(), set())
        methods = [m for m, _ in self.client.api_calls]
        self.assertEqual(["answerCallbackQuery", "editMessageText"], methods)
        edit = self.client.api_calls[1][1]
        self.assertEqual("Which DB?\n\n✅ SQLite", edit["text"])
        self.assertNotIn("reply_markup", edit, "omitting reply_markup is what removes the buttons")
        (rec,) = self.records()
        self.assertEqual("button", rec["kind"])
        self.assertEqual("SQLite", rec["text"])
        self.assertEqual({"index": 1, "label": "SQLite"}, rec["button"])
        self.assertEqual(300, rec["message_id"])
        self.assertEqual(300, rec["reply_to"]["message_id"])
        self.assertTrue(self.exchange.exists())

    def test_second_press_on_same_card_is_not_relayed(self):
        # Both callbacks carry the keyboard snapshot from press time.
        bot_module.handle_callback_query(self.client, self.config, card_callback(data="opt:0"), set())
        bot_module.handle_callback_query(self.client, self.config, card_callback(data="opt:1"), set())
        self.assertEqual(["Postgres"], [r["text"] for r in self.records()])
        self.assertIn("already answered", self.client.api_calls[-2][1]["text"])

    def test_choice_is_recorded_before_it_is_acknowledged(self):
        order = []
        real_api = self.client.api

        def api(method, payload):
            order.append(("api:" + method, len(self.records())))
            return real_api(method, payload)
        self.client.api = api
        bot_module.handle_callback_query(self.client, self.config, card_callback(), set())
        self.assertEqual(("api:answerCallbackQuery", 1), order[0], "ack only after the record is durable")

    def test_unauthorized_press_is_refused_and_not_relayed(self):
        bot_module.handle_callback_query(self.client, self.config, card_callback(from_id=1, chat_id=1), set())
        self.assertEqual(["answerCallbackQuery"], [m for m, _ in self.client.api_calls])
        self.assertEqual([], self.records())
        self.assertFalse(self.exchange.exists())

    def test_group_press_needs_founder_or_allowlist(self):
        cb = card_callback(from_id=77, chat_id=-100, chat_type="supergroup")
        bot_module.handle_callback_query(self.client, self.config, cb, set())
        self.assertEqual([], self.records())
        bot_module.handle_callback_query(self.client, self.config, cb, {77})
        self.assertEqual("SQLite", self.records()[0]["text"])

    def test_stale_card_is_not_relayed_twice(self):
        bot_module.handle_callback_query(self.client, self.config, card_callback(markup=False), set())
        self.assertEqual([], self.records())
        self.assertIn("already answered", self.client.api_calls[0][1]["text"])

    def test_poll_routes_callback_and_clears_card_on_reply(self):
        reply = {"message_id": 301, "chat": {"id": FOUNDER, "type": "private"}, "from": {"id": FOUNDER},
                 "text": "Postgres please", "reply_to_message": {"message_id": 300, "from": {"id": BOT_ID}, "text": "Which DB?"}}
        updates = {"ok": True, "result": [
            {"update_id": 1, "callback_query": card_callback()},
            {"update_id": 2, "message": reply},
        ]}
        self.client.get_updates = mock.Mock(return_value=updates)
        bridge_config = {"bot_id": BOT_ID, "bot_username": "testbot"}
        code = bot_module.poll_once(self.client, self.config, bridge_config, set(), {})
        self.assertEqual(0, code)
        self.assertIn(("editMessageReplyMarkup", {"chat_id": FOUNDER, "message_id": 300,
                                                  "reply_markup": {"inline_keyboard": []}}), self.client.api_calls)
        kinds = [r.get("kind") for r in self.records()]
        self.assertEqual(["button", None], kinds)
        self.assertEqual((FOUNDER, 301, "👀"), self.client.reactions[-1])

    def test_reply_to_founder_message_does_not_touch_buttons(self):
        reply = {"message_id": 302, "chat": {"id": FOUNDER, "type": "private"}, "from": {"id": FOUNDER},
                 "text": "x", "reply_to_message": {"message_id": 5, "from": {"id": FOUNDER}, "text": "mine"}}
        self.client.get_updates = mock.Mock(return_value={"ok": True, "result": [{"update_id": 3, "message": reply}]})
        bot_module.poll_once(self.client, self.config, {"bot_id": BOT_ID}, set(), {})
        self.assertNotIn("editMessageReplyMarkup", [m for m, _ in self.client.api_calls])

    def test_group_menu_command_addressed_to_bot_is_relayed(self):
        msg = {"message_id": 400, "chat": {"id": -100, "type": "supergroup", "title": "g"},
               "from": {"id": FOUNDER, "first_name": "F"}, "text": "/status@testbot",
               "entities": [{"type": "bot_command", "offset": 0, "length": 15}]}
        self.client.get_updates = mock.Mock(return_value={"ok": True, "result": [{"update_id": 9, "message": msg}]})
        bot_module.poll_once(self.client, self.config, {"bot_id": BOT_ID, "bot_username": "testbot"}, set(), {})
        self.assertEqual(["/status@testbot"], [r["text"] for r in self.records()])

    def test_relay_off_cleans_up_a_leftover_post_but_never_posts(self):
        state = bot_module.IDLE_STATE_FILE
        config = dict(self.config, relay_mode=False)
        with mock.patch.object(bot_module, "parse_env_file", return_value={}):
            bot_module.run_idle_status(self.client, config)
            self.assertEqual([], self.client.api_calls)
            state.write_text(json.dumps({"post": {"chat_id": FOUNDER, "message_id": 5, "posted_at": 1.0,
                                                  "checked_at": 1.0, "hash": "x"}}))
            bot_module.run_idle_status(self.client, config)
        self.assertEqual([("deleteMessage", {"chat_id": FOUNDER, "message_id": 5})], self.client.api_calls)

    def test_bot_still_imports_and_polls_without_idle_status_module(self):
        """A partially-updated install (new bot.py, no idle_status.py) must keep relaying."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("bot.py", "telegram_common.py"):
                (Path(tmp) / name).write_text((SCRIPT_DIR / name).read_text())
            r = subprocess.run(
                ["python3", "-c", "import bot; print(bot.idle_status is None); bot.run_idle_status(None, {'relay_mode': True})"],
                cwd=tmp, capture_output=True, text=True, timeout=30,
                env=dict(os.environ, TELEGRAM_BRIDGE_TEST_MODE="1"),
            )
        self.assertEqual(0, r.returncode, r.stderr[-500:])
        self.assertEqual("True", r.stdout.strip())

    def test_get_updates_requests_callback_queries(self):
        self.assertIn("callback_query", bot_module.ALLOWED_UPDATES)
        with mock.patch.object(bot_module.requests, "get") as get:
            get.return_value.json.return_value = {"ok": True, "result": []}
            bot_module.TelegramClient(FAKE_TOKEN).get_updates()
        params = get.call_args.kwargs["params"]
        self.assertIn("callback_query", json.loads(params["allowed_updates"]))

    def test_exchange_and_idle_paths_are_guarded_under_test(self):
        with mock.patch.object(bot_module, "EXCHANGE_FILE", idle_status.EXCHANGE_FILE):
            with self.assertRaises(RuntimeError):
                bot_module.note_exchange()


class ShellReplyToTests(unittest.TestCase):
    """notify.sh / send-file.sh against a fake curl that logs its argv."""

    def run_script(self, name, *args):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bridge = d / "bridge"
            bridge.mkdir()
            script = bridge / name
            script.write_text((SCRIPT_DIR / name).read_text())
            script.chmod(0o755)
            (bridge / ".env").write_text(f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID={FOUNDER}\n")
            fake_bin = d / "bin"
            fake_bin.mkdir()
            log = d / "curl.log"
            curl = fake_bin / "curl"
            curl.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "{log}"\necho \'{{"ok":true,"result":{{"message_id":9}}}}\'\n')
            curl.chmod(0o755)
            payload = d / "f.txt"
            payload.write_text("hi")
            args = [str(payload) if a == "@FILE" else a for a in args]
            env = dict(os.environ, PATH=f"{fake_bin}:{os.environ['PATH']}")
            result = subprocess.run([str(script), *args], capture_output=True, text=True, env=env, timeout=20)
            argv = log.read_text() if log.exists() else ""
            return result, argv, (bridge / ".last-exchange").exists()

    def test_notify_reply_to(self):
        result, argv, touched = self.run_script("notify.sh", "--reply-to", "1234", "hello")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('reply_parameters={"message_id":1234,"allow_sending_without_reply":true}', argv)
        self.assertIn("text=hello", argv)
        self.assertTrue(touched)

    def test_notify_flags_any_order_and_plain_send_unchanged(self):
        result, argv, _ = self.run_script("notify.sh", "hello")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("reply_parameters", argv)
        result, _, _ = self.run_script("notify.sh", "--reply-to", "abc", "hello")
        self.assertEqual(1, result.returncode)
        self.assertIn("numeric", result.stderr)

    def test_send_file_reply_to(self):
        result, argv, touched = self.run_script("send-file.sh", "--reply-to", "77", "@FILE", "cap")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('reply_parameters={"message_id":77,"allow_sending_without_reply":true}', argv)
        self.assertTrue(touched)

    def test_failed_send_does_not_mark_exchange(self):
        result, _, touched = self.run_script("notify.sh")
        self.assertEqual(1, result.returncode)
        self.assertFalse(touched)


class ConfigureBridgeTests(unittest.TestCase):
    BASE = f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID={FOUNDER}\n"

    def plan(self, text, files=(), command=None):
        values = {}
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(text)
            values = configure_bridge.telegram_common.parse_env_file(env)
            new, report = configure_bridge.plan_changes(text, values, list(files), command)
            env.write_text(new)
            return new, report, configure_bridge.telegram_common.parse_env_file(env)

    def test_adds_missing_defaults_and_never_touches_existing_values(self):
        new, report, values = self.plan(self.BASE + "IDLE_STATUS_AFTER_MINUTES=60\n")
        self.assertEqual("1", values["RELAY_MODE"])
        self.assertEqual("60", values["IDLE_STATUS_AFTER_MINUTES"], "an existing choice is kept")
        self.assertEqual("40", values["IDLE_STATUS_REFRESH_MINUTES"])
        self.assertEqual(FAKE_TOKEN, values["TELEGRAM_BOT_TOKEN"])
        self.assertTrue(all(FAKE_TOKEN not in line for line in report), "no secret in the report")

    def test_explicit_relay_off_is_not_overridden_but_flagged(self):
        _, _, values = self.plan(self.BASE + "RELAY_MODE=0\n")
        self.assertEqual("0", values["RELAY_MODE"])
        self.assertFalse(configure_bridge.readiness(values)[0][0])

    def test_missing_required_key_is_reported_as_bridge_down(self):
        # Found in the update dry run on a real install: every feature line read
        # "ok" while bot.py refused to start for want of CLAUDE_DEFAULT_CWD.
        _, _, values = self.plan(self.BASE)
        problems = [m for ok, m in configure_bridge.readiness(values) if not ok]
        self.assertTrue(any(m.startswith(configure_bridge.BRIDGE_DOWN_PREFIX) and "CLAUDE_DEFAULT_CWD" in m
                            for m in problems), problems)
        self.assertTrue(all(FAKE_TOKEN not in m for m in problems))
        _, _, values = self.plan(self.BASE + "CLAUDE_DEFAULT_CWD=/p/a\n")
        self.assertEqual([], [m for ok, m in configure_bridge.readiness(values) if not ok
                              and m.startswith(configure_bridge.BRIDGE_DOWN_PREFIX)])
        # main() exits 2 for a bridge that cannot start, same as relay off.
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(self.BASE + "RELAY_MODE=1\n")
            with mock.patch.object(configure_bridge, "ENV_FILE", env), \
                 mock.patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(2, configure_bridge.main(["--check"]))

    def test_idempotent(self):
        once, _, _ = self.plan(self.BASE, files=["/p/a/docs/coordination/STATE.md"])
        twice, report, _ = self.plan(once, files=["/p/a/docs/coordination/STATE.md"])
        self.assertEqual(once, twice)
        self.assertEqual([], report)

    def test_status_files_merge_across_projects(self):
        once, _, _ = self.plan(self.BASE, files=["/p/a/STATE.md"])
        _, _, values = self.plan(once, files=["/p/b/STATE.md"])
        self.assertEqual(["/p/a/STATE.md", "/p/b/STATE.md"],
                         [x for x in values["STATUS_FILES"].split(",")])

    def test_written_values_are_inert_when_bash_sources_the_env(self):
        marker = Path(tempfile.mkdtemp()) / "ran"
        cmd = f"touch {marker} && echo hi"
        new, _, values = self.plan(self.BASE, command=cmd)
        self.assertEqual(cmd, values["STATUS_COMMANDS"])
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(new)
            r = subprocess.run(["bash", "-c", f'set -a; source "{env}"; set +a; printf %s "$STATUS_COMMANDS"'],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(cmd, r.stdout)
        self.assertFalse(marker.exists(), "sourcing .env must not execute STATUS_COMMAND")

    def test_status_commands_merge_per_project_and_replace_same_root(self):
        a1 = "python3 /plug/0.12/coord.py --root /p/a status"
        b = "python3 /plug/0.12/coord.py --root /p/b status"
        a2 = "python3 /plug/0.13/coord.py --root /p/a status"
        t, _, _ = self.plan(self.BASE, command=a1)
        t, _, _ = self.plan(t, command=b)
        t, report, values = self.plan(t, command=a2)
        self.assertEqual([b, a2], configure_bridge.split_commands(values["STATUS_COMMANDS"]))
        self.assertTrue(any("replaced older entry" in line for line in report))
        _, report, _ = self.plan(t, command=a2)
        self.assertEqual([], report, "idempotent")

    def test_remove_status_file(self):
        t, _, _ = self.plan(self.BASE, files=["/p/a/STATE.md", "/p/b/STATE.md"])
        values = configure_bridge.telegram_common.parse_env_file
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(t)
            new, report = configure_bridge.plan_changes(t, values(env), [], None, ["/p/a/STATE.md"])
            env.write_text(new)
            self.assertEqual("/p/b/STATE.md", values(env)["STATUS_FILES"])

    def test_add_and_remove_in_one_run_keeps_the_addition(self):
        # Found in the live test: moving a project (remove old + add new in one
        # call) left STATUS_FILES empty because the removal ignored the add.
        values = configure_bridge.telegram_common.parse_env_file
        t, _, _ = self.plan(self.BASE, files=["/p/old/STATE.md", "/p/keep/STATE.md"])
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(t)
            new, _ = configure_bridge.plan_changes(t, values(env), ["/p/new/STATE.md"], None, ["/p/old/STATE.md"])
            env.write_text(new)
            self.assertEqual("/p/keep/STATE.md,/p/new/STATE.md", values(env)["STATUS_FILES"])

    def test_env_rewrite_never_exposes_token_in_a_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text(self.BASE)
            env.chmod(0o600)
            seen = []
            real_replace = Path.replace

            def spy(self_path, target):
                seen.append(oct(self_path.stat().st_mode & 0o777))
                return real_replace(self_path, target)
            with mock.patch.object(configure_bridge, "ENV_FILE", env), \
                    mock.patch.object(Path, "replace", spy), \
                    mock.patch.object(configure_bridge, "register_commands", return_value=0), \
                    mock.patch("sys.stdout"):
                configure_bridge.main(["--status-file", "/p/a/STATE.md"])
            self.assertEqual(["0o600"], seen)
            self.assertEqual(0o600, env.stat().st_mode & 0o777)
            self.assertIn("/p/a/STATE.md", env.read_text())

    def test_unsafe_values_are_refused(self):
        with self.assertRaises(ValueError):
            self.plan(self.BASE, command="echo 'quoted'")


if __name__ == "__main__":
    unittest.main()
