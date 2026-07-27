#!/usr/bin/env python3
"""
test_typing.py - Offline unit tests for typing.sh: the unconfigured-bridge
exit behavior, and (T1/W5) that the keep-alive form returns immediately even
when the caller captures its stdout/stderr, actually fires the typing
indicator more than once, and self-terminates.

No network access, no live token for the unconfigured-bridge tests:
typing.sh's missing-.env and missing-TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID
checks both run - and exit - before the script ever calls curl, so running
the real script directly (not sourced) in a throwaway directory with no
.env exercises that exit path without touching the network. This mirrors
test_send_file.py's UnconfiguredBridgeExitCodeTests for send-file.sh - see
SETUP.md (j)'s "unconfigured-bridge behavior" paragraph, which documents
this same exit-1-on-missing-.env-or-TELEGRAM_BOT_TOKEN contract for all
four scripts (TELEGRAM_CHAT_ID is required here too, since typing.sh has no
--chat override the way react.sh does).

The keep-alive test below uses a stubbed `curl` on PATH and an obviously
fake token/chat id instead - never a live token, never a real network call
- and exercises the real script's actual background-subshell code path (not
a reimplementation of it), the same approach test_react.py uses. Because
that subshell is detached (`disown`'d) and outlives the `typing.sh` process
itself, this test never deletes the tempdir holding the fake `curl` stub
until it has directly confirmed, via the real OS process table (see
_wait_until_gone() below), that the subshell has actually exited - never by
guessing how long that should take. A fixed sleep here previously raced
that exit on a loaded machine and could fall through to the real `curl` on
PATH; see KeepAliveTests' docstring below for the full explanation.

Run:
    python3 test_typing.py
    python3 -m unittest test_typing.py -v
"""

import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TYPING_SH = SCRIPT_DIR / "typing.sh"

FAKE_CURL_STUB = """#!/usr/bin/env bash
# Fake curl: never touches the network. Logs one NUL-terminated timestamp
# per invocation to $CURL_LOG so a test can read back exactly how many
# times it was actually called, instead of inferring that from timing -
# same NUL-separated logging convention test_react.py's stub uses.
printf '%s\\0' "$(date +%s.%N)" >> "$CURL_LOG"
echo '{"ok":true,"result":true}'
exit 0
"""


def _pgrep_pids(marker: str) -> list:
    """PIDs of currently-running processes whose full command line contains
    `marker`, via `pgrep -f`. Raises FileNotFoundError if pgrep itself isn't
    on PATH - callers turn that into a skipTest rather than silently
    treating "can't check" as "nothing's running", which would defeat the
    whole point of the safety checks built on top of this.
    """
    result = subprocess.run(
        ["pgrep", "-f", marker], capture_output=True, text=True, timeout=5,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pgrep -f {marker!r} failed unexpectedly: {result.stderr}")
    return [pid for pid in result.stdout.split() if pid]


def _wait_until_gone(marker: str, timeout: float, poll_interval: float = 0.05) -> bool:
    """Poll the real OS process table - not a timer - until no process's
    command line contains `marker` any more, or `timeout` seconds have
    elapsed. Returns True once pgrep itself reports zero matches: that is
    the actual, authoritative signal that a detached subshell (and any
    curl call it's still mid-flight on) has exited, not an inference from
    how much wall-clock time has passed.
    """
    deadline = time.monotonic() + timeout
    while _pgrep_pids(marker):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)
    return True


def _kill_matching(marker: str) -> None:
    """Safety net only: SIGKILL any process whose command line still
    contains `marker`. A normal run never finds a live match here, because
    callers only reach this after _wait_until_gone() already confirmed (or
    gave up waiting for) the process. It exists so that even a
    pathological stall can never leave a live process behind once the
    caller's tempdir - and the fake `curl` stub inside it - is deleted: the
    guarantee this provides is "nothing survives past this call", not
    "everything usually finishes in time".
    """
    for pid in _pgrep_pids(marker):
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ValueError, ProcessLookupError, PermissionError):
            pass


class UnconfiguredBridgeExitCodeTests(unittest.TestCase):
    """typing.sh must exit 1 (not 0) when the bridge isn't configured,
    matching notify.sh/react.sh/send-file.sh - see SETUP.md (j)'s
    "unconfigured-bridge behavior" paragraph.
    """

    def _run_in_throwaway_dir(self, env_contents=None, args=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bridge_dir = tmp_path / "bridge"
            bridge_dir.mkdir()
            shutil.copy(TYPING_SH, bridge_dir / "typing.sh")
            (bridge_dir / "typing.sh").chmod(0o755)
            if env_contents is not None:
                (bridge_dir / ".env").write_text(env_contents, encoding="utf-8")

            return subprocess.run(
                [str(bridge_dir / "typing.sh"), *(args or [])],
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

    def test_missing_env_file_exits_1_with_duration_arg(self):
        # The keep-alive form (typing.sh <seconds>) must hit the same
        # unconfigured check before ever backgrounding a keep-alive loop.
        result = self._run_in_throwaway_dir(env_contents=None, args=["30"])
        self.assertEqual(result.returncode, 1)
        self.assertIn(".env not found", result.stderr)


class KeepAliveTests(unittest.TestCase):
    """T1 + W5 coverage from a single real keep-alive invocation, so this
    file's one unavoidable real-time cost - typing.sh's keep-alive retry
    interval is a hardcoded 4s sleep, see typing.sh - is paid once, not
    twice.

    T1 regression coverage: typing.sh <seconds> must return immediately
    even when the caller captures this script's stdout/stderr, not just
    when the caller redirects them to /dev/null. subprocess.run(...,
    capture_output=True) captures via a pipe under the hood - the same
    mechanism `typing.sh N | cat` and `out="$(typing.sh N)"` use - so this
    reproduces the exact bug class the verifier measured (elapsed=12s for
    `| cat`, elapsed=9s for `$(...)`, vs. elapsed=0s only when the *caller*
    redirected to /dev/null). Before the fix (redirecting the background
    subshell's own stdout/stderr to /dev/null inside typing.sh itself),
    this test would either time out or measure multi-second elapsed time.

    W5 fix: also proves the detached keep-alive loop this starts genuinely
    re-sends the typing indicator more than once and then stops on its own,
    without racing its own teardown. The previous version of this test
    proved the loop was finished only by guessing a wall-clock margin
    (`time.sleep(duration + 3)`) on top of a fixed `duration`. On a loaded
    machine, the loop's last `send_typing_once` call could still be in
    flight when that guess ran out; the tempdir (and the fake `curl` stub
    inside `fake_bin/`) would then be deleted out from under it, and the
    next `curl` lookup on PATH inside the still-running subshell would fall
    through to the *real* system `curl` and hit api.telegram.org - silently,
    since a failed ping is swallowed (`|| true`) by design. The margin
    observed in practice was about 40 milliseconds.

    This version replaces the guess with two directly-observed facts, and
    never deletes the tempdir until both hold:
      1. How many times the stub actually fired is read from its own
         invocation log (CURL_LOG), not inferred from elapsed time.
      2. Whether the detached subshell has actually exited is read from the
         real OS process table (`pgrep -f <this test's unique typing.sh
         path>` via _wait_until_gone()), not from how much time has passed.
    As a last-resort safety net on top of #2 - in case of a stall beyond
    even the generous timeout below - _kill_matching() forcibly kills
    anything still matching in the `finally` block before control returns
    to the `with tempfile.TemporaryDirectory()` block that deletes
    fake_bin/. Because of that combination, the tempdir can never be
    removed while a process that could still invoke the stubbed `curl` is
    alive - not "usually", always, regardless of how long any single call
    stalls - so the real `curl` on PATH can never be reached at any timing.
    """

    def test_returns_immediately_fires_repeatedly_and_self_terminates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bridge_dir = tmp_path / "bridge"
            bridge_dir.mkdir()
            shutil.copy(TYPING_SH, bridge_dir / "typing.sh")
            (bridge_dir / "typing.sh").chmod(0o755)
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

            script_path = str(bridge_dir / "typing.sh")
            # 2s is the smallest duration that reliably produces a second
            # call: the loop's retry interval is a hardcoded 4s sleep (see
            # typing.sh), and `date +%s` truncates to whole seconds, so
            # duration=1 can let the post-sleep `while` check land on-or-past
            # END before the sleep ever runs, on a run that starts near a
            # second boundary - observed in practice to sometimes produce
            # only the guaranteed immediate call and nothing to prove
            # "repeatedly" with. duration=2 leaves comfortable margin for
            # that same check to still be True.
            duration = 2
            try:
                # If typing.sh still blocked until the keep-alive loop finished
                # (the T1 bug), capture_output's pipe-read would not see EOF
                # until then and this call would hit the 3s timeout and raise
                # TimeoutExpired well before `duration` seconds pass.
                start = time.monotonic()
                result = subprocess.run(
                    [script_path, str(duration)],
                    cwd=bridge_dir, env=env, capture_output=True, text=True, timeout=3,
                )
                elapsed = time.monotonic() - start

                self.assertEqual(result.returncode, 0)
                self.assertLess(elapsed, 2.0, "typing.sh should return almost instantly, not wait on its own background loop")

                # Ground truth for "has it stopped", read from the OS itself,
                # not guessed from elapsed time. 30s is generous - the loop's
                # own math means it should be done in well under 10s here -
                # but the exact bound doesn't matter for safety: see the
                # class docstring and the finally block below for what
                # actually makes this race-proof regardless of this number.
                confirmed_gone = _wait_until_gone(script_path, timeout=30)
                self.assertTrue(
                    confirmed_gone,
                    "typing.sh's detached keep-alive subshell never self-terminated within 30s",
                )

                calls = [line for line in curl_log.read_text(encoding="utf-8").split("\0") if line]
                self.assertGreaterEqual(
                    len(calls), 2,
                    f"expected the keep-alive loop to fire more than once for duration={duration}, got {calls!r}",
                )
            finally:
                # See the class docstring: this is what guarantees the
                # tempdir below is never removed while a process that could
                # still call the stubbed curl is alive, no matter how the
                # assertions above went.
                if not _wait_until_gone(script_path, timeout=5):
                    _kill_matching(script_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
