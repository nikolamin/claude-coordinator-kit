#!/usr/bin/env python3
"""
test_react.py - Offline unit tests for react.sh's word -> emoji reaction
vocabulary (F4: ok/fail plus the newer done/check/thumbup/down/thumbdown/x/
seen/working/thinking words, literal-emoji passthrough for other input, and
a local fast-fail for an unrecognized ASCII word instead of a network round
trip - see the case statement's comment in react.sh).

No network access, no live token: react.sh's word -> EMOJI mapping is
computed by a `case` statement inline in the script's linear body (unlike
send-file.sh, react.sh has no guarded/sourceable function to call in
isolation - see send-file.sh's header comment for why THAT script grew
one), so the only way to observe which emoji a given word actually resolves
to, without changing react.sh itself, is to let the real script run to
completion and inspect what it would have sent. This is done by pointing
PATH at a fake `curl` stub (so no real network call happens) and supplying
a throwaway fake .env (an obviously-fake token/chat id, never a real one),
then parsing the fake curl's logged invocation for the `reaction=` JSON
payload's `emoji` value - this exercises react.sh's actual, real case
statement, not a reimplementation of it.

Run:
    python3 test_react.py
    python3 -m unittest test_react.py -v
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REACT_SH = SCRIPT_DIR / "react.sh"

FAKE_CURL_STUB = """#!/usr/bin/env bash
# Fake curl: never touches the network. Logs its own invocation so the test
# can inspect the reaction= JSON react.sh actually built, then returns a
# canned Telegram-style success response.
printf '%s\\0' "$@" >> "$CURL_LOG"
echo '{"ok":true,"result":true}'
exit 0
"""

REACTION_EMOJI_RE = re.compile(r'"emoji":"([^"]*)"')


def resolve_reaction_emoji(word: str) -> str:
    """Run the real react.sh with `word` as the result argument, against a
    stubbed curl and a throwaway fake .env, and return the emoji value it
    actually placed in the setMessageReaction call.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bridge_dir = tmp_path / "bridge"
        bridge_dir.mkdir()
        shutil.copy(REACT_SH, bridge_dir / "react.sh")
        (bridge_dir / "react.sh").chmod(0o755)
        (bridge_dir / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=FAKE_TEST_TOKEN_NOT_REAL\nTELEGRAM_CHAT_ID=123456789\n",
            encoding="utf-8",
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        curl_stub = fake_bin / "curl"
        curl_stub.write_text(FAKE_CURL_STUB, encoding="utf-8")
        curl_stub.chmod(0o755)

        curl_log = tmp_path / "curl.log"

        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["CURL_LOG"] = str(curl_log)

        result = subprocess.run(
            [str(bridge_dir / "react.sh"), "123", word],
            cwd=bridge_dir, env=env, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"react.sh 123 {word!r} failed (exit {result.returncode}): {result.stderr}")

        if not curl_log.exists():
            raise RuntimeError(f"react.sh 123 {word!r} never invoked curl at all: {result.stderr}")

        # The stub logs each argv token NUL-separated; find the one that
        # looks like the reaction JSON payload.
        raw = curl_log.read_bytes()
        tokens = raw.decode("utf-8").split("\0")
        for token in tokens:
            if token.startswith("reaction="):
                match = REACTION_EMOJI_RE.search(token)
                if match:
                    return match.group(1)
        raise RuntimeError(f"no reaction= payload found in curl invocation for word {word!r}: {tokens}")


def run_react_raw(word: str) -> "tuple[subprocess.CompletedProcess, bool]":
    """Run the real react.sh with `word` as the result argument, against a
    stubbed curl and a throwaway fake .env, and return (CompletedProcess,
    curl_was_invoked) - used by tests that expect react.sh to fail *before*
    ever reaching curl, where resolve_reaction_emoji()'s "must exit 0 and
    must have invoked curl" assumptions don't apply.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bridge_dir = tmp_path / "bridge"
        bridge_dir.mkdir()
        shutil.copy(REACT_SH, bridge_dir / "react.sh")
        (bridge_dir / "react.sh").chmod(0o755)
        (bridge_dir / ".env").write_text(
            "TELEGRAM_BOT_TOKEN=FAKE_TEST_TOKEN_NOT_REAL\nTELEGRAM_CHAT_ID=123456789\n",
            encoding="utf-8",
        )

        fake_bin = tmp_path / "fakebin"
        fake_bin.mkdir()
        curl_stub = fake_bin / "curl"
        curl_stub.write_text(FAKE_CURL_STUB, encoding="utf-8")
        curl_stub.chmod(0o755)

        curl_log = tmp_path / "curl.log"

        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["CURL_LOG"] = str(curl_log)

        result = subprocess.run(
            [str(bridge_dir / "react.sh"), "123", word],
            cwd=bridge_dir, env=env, capture_output=True, text=True, timeout=10,
        )
        return result, curl_log.exists()


class ReactVocabularyTests(unittest.TestCase):
    def test_ok_is_unchanged_thumbs_up(self):
        self.assertEqual(resolve_reaction_emoji("ok"), "👍")

    def test_fail_is_unchanged_thumbs_down(self):
        self.assertEqual(resolve_reaction_emoji("fail"), "👎")

    def test_thumbup_synonyms_all_map_to_thumbs_up(self):
        for word in ("done", "check", "thumbup"):
            self.assertEqual(resolve_reaction_emoji(word), "👍", word)

    def test_thumbdown_synonyms_all_map_to_thumbs_down(self):
        for word in ("down", "thumbdown", "x"):
            self.assertEqual(resolve_reaction_emoji(word), "👎", word)

    def test_seen_and_working_map_to_eyes(self):
        for word in ("seen", "working"):
            self.assertEqual(resolve_reaction_emoji(word), "👀", word)

    def test_thinking_maps_to_thinking_face(self):
        self.assertEqual(resolve_reaction_emoji("thinking"), "🤔")

    def test_unrecognized_word_passes_through_as_a_literal_emoji(self):
        # Not a known keyword - react.sh must never block the caller over
        # an unrecognized argument; it's used as-is.
        self.assertEqual(resolve_reaction_emoji("🔥"), "🔥")


class UnrecognizedAsciiWordFailsLocallyTests(unittest.TestCase):
    """An unrecognized ASCII-letters-only word (almost certainly a typo of
    one of the known words, not an actual emoji) must fail locally, before
    react.sh ever invokes curl - see the case statement's comment. This is
    the T3 fix: previously this class of input passed through to the
    Telegram API and was rejected there instead, which still exited 1 but
    only after a network round trip.
    """

    def test_typo_word_exits_1_without_ever_calling_curl(self):
        result, curl_called = run_react_raw("dun")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(curl_called, "react.sh should reject a typo'd word before invoking curl")

    def test_typo_word_error_names_the_bad_word_and_lists_known_vocabulary(self):
        result, _ = run_react_raw("faill")
        self.assertIn("faill", result.stderr)
        for word in ("ok", "fail", "seen", "working", "thinking"):
            self.assertIn(word, result.stderr, f"expected known word {word!r} listed in error output")

    def test_ok_and_fail_are_unaffected_by_the_new_local_fail_path(self):
        # ok/fail must still resolve normally (reach curl, get 👍/👎) - the
        # local fast-fail only applies to *unrecognized* ASCII words.
        result, curl_called = run_react_raw("ok")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(curl_called)

    def test_non_ascii_emoji_still_passes_through_without_local_rejection(self):
        # A real emoji (non-ASCII) must still reach curl as before - the
        # local fast-fail is scoped to ASCII-letters-only input.
        result, curl_called = run_react_raw("🔥")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(curl_called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
