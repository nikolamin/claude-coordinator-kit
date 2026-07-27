#!/usr/bin/env python3
"""
test_send_file.py - Offline unit tests for send-file.sh's extension -> Bot
API method routing (its resolve_send_method() bash function) and its
unconfigured-bridge exit behavior.

No network access, no live token, no .env required: send-file.sh guards its
own top-level body with `[[ "${BASH_SOURCE[0]}" == "${0}" ]]`, so `source`ing
it (rather than executing it) only defines resolve_send_method() and its
size-threshold constants, without parsing argv, touching .env, or making any
network call. Each routing test below sources the script in a fresh
`bash -c` subprocess and calls resolve_send_method() directly with synthetic
(extension, byte-size) inputs, capturing its stdout. The unconfigured-exit
tests below instead execute the real script directly (in a throwaway
directory with no .env, so no network call is ever reached - the missing-.env
check runs and exits before curl would) to confirm it exits 1, matching
notify.sh/react.sh/typing.sh - see SETUP.md (j)'s "unconfigured-bridge
behavior" note.

Run:
    python3 test_send_file.py
    python3 -m unittest test_send_file.py -v
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SEND_FILE_SH = SCRIPT_DIR / "send-file.sh"


def resolve_send_method(ext: str, size_bytes: int) -> str:
    """Call send-file.sh's resolve_send_method() in an isolated bash
    subprocess (source-only, no execution of the script's main body) and
    return its "<METHOD> <FIELD>" stdout, stripped.
    """
    result = subprocess.run(
        ["bash", "-c", f'source "{SEND_FILE_SH}"; resolve_send_method "$1" "$2"',
         "--", ext, str(size_bytes)],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"resolve_send_method({ext!r}, {size_bytes!r}) failed "
            f"(exit {result.returncode}): {result.stderr}"
        )
    return result.stdout.strip()


class SourcingSendFileDoesNotRunItsBodyTests(unittest.TestCase):
    """Confirms the guard itself: sourcing send-file.sh with no arguments
    and no .env must not crash, print an error, or attempt a network call -
    the entire point of the `[[ "${BASH_SOURCE[0]}" == "${0}" ]]` guard.
    """

    def test_sourcing_with_no_args_and_no_env_is_a_silent_no_op(self):
        result = subprocess.run(
            ["bash", "-c", f'source "{SEND_FILE_SH}"; echo SOURCED_OK'],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SOURCED_OK", result.stdout)
        self.assertEqual(result.stderr.strip(), "")


class ResolveSendMethodTests(unittest.TestCase):
    def test_small_jpg_is_sent_as_photo(self):
        self.assertEqual(resolve_send_method("jpg", 1000), "sendPhoto photo")

    def test_jpeg_png_webp_are_also_photo(self):
        for ext in ("jpeg", "png", "webp"):
            self.assertEqual(resolve_send_method(ext, 1000), "sendPhoto photo", ext)

    def test_photo_over_10mb_falls_back_to_document(self):
        over_10mb = 10 * 1024 * 1024 + 1
        self.assertEqual(resolve_send_method("jpg", over_10mb), "sendDocument document")

    def test_photo_at_exactly_10mb_is_still_a_photo(self):
        exactly_10mb = 10 * 1024 * 1024
        self.assertEqual(resolve_send_method("png", exactly_10mb), "sendPhoto photo")

    def test_gif_is_sent_as_animation_regardless_of_size(self):
        self.assertEqual(resolve_send_method("gif", 1000), "sendAnimation animation")
        self.assertEqual(resolve_send_method("gif", 40 * 1024 * 1024), "sendAnimation animation")

    def test_video_extensions_are_sent_as_video(self):
        for ext in ("mp4", "mov", "mkv", "webm", "m4v", "avi", "3gp"):
            self.assertEqual(resolve_send_method(ext, 1000), "sendVideo video", ext)

    def test_unknown_or_missing_extension_falls_back_to_document(self):
        for ext in ("pdf", "docx", "xlsx", "txt", "zip", "log", ""):
            self.assertEqual(resolve_send_method(ext, 1000), "sendDocument document", ext)

    def test_caller_must_lowercase_first(self):
        # resolve_send_method() itself expects an already-lowercased
        # extension - send-file.sh's main body lowercases before calling
        # it. An uppercase extension must NOT match the photo/video cases,
        # so a future caller can't silently skip the lowercasing step
        # without this test noticing.
        self.assertEqual(resolve_send_method("JPG", 1000), "sendDocument document")


class UnconfiguredBridgeExitCodeTests(unittest.TestCase):
    """send-file.sh must exit 1 (not 0) when the bridge isn't configured,
    matching notify.sh/react.sh/typing.sh - see SETUP.md (j)'s
    "unconfigured-bridge behavior" paragraph. Runs the real script directly
    (not sourced) in a throwaway directory so the missing-.env /
    missing-vars checks are exercised exactly as a real caller would hit
    them; both checks run before any network call, so this stays offline.
    """

    def _run_in_throwaway_dir(self, env_contents=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bridge_dir = tmp_path / "bridge"
            bridge_dir.mkdir()
            shutil.copy(SEND_FILE_SH, bridge_dir / "send-file.sh")
            (bridge_dir / "send-file.sh").chmod(0o755)
            if env_contents is not None:
                (bridge_dir / ".env").write_text(env_contents, encoding="utf-8")

            target_file = tmp_path / "deliverable.txt"
            target_file.write_text("hello", encoding="utf-8")

            return subprocess.run(
                [str(bridge_dir / "send-file.sh"), str(target_file)],
                cwd=bridge_dir, capture_output=True, text=True, timeout=10,
            )

    def test_missing_env_file_exits_1(self):
        result = self._run_in_throwaway_dir(env_contents=None)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".env not found", result.stderr)

    def test_env_file_with_empty_vars_exits_1(self):
        result = self._run_in_throwaway_dir(env_contents="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID not set", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
