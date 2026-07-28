#!/usr/bin/env python3
"""
test_register_commands.py - Offline unit tests for register-commands.sh's
menu merge (SETUP.md (m)).

WHAT IS ACTUALLY BEING TESTED. The three properties the script promises and
that a re-run has to keep true forever:

  1. ADDITIVE - a command registered by somebody else (an older run, a
     second project, the founder by hand) is never dropped by our merge,
     and keeps its position;
  2. IDEMPOTENT - running twice changes nothing the second time, and the
     script says so instead of issuing a pointless setMyCommands write;
  3. EMPTY BY DEFAULT IS A NO-OP, NOT A CRASH - the kit ships COMMANDS
     empty, and `"${COMMANDS[@]}"` on an empty array is an unbound-variable
     error under `set -u` in bash 3.2 (still /bin/bash on macOS). The guard
     for that is a behaviour, so it gets a test.

Plus the secrets-hygiene property the whole bridge shares: the bot token is
never echoed to stdout or stderr, on any path.

No network access, no live token. Like test_react.py/test_typing.py, these
run the REAL script - the merge is a python heredoc inline in the script's
body, so the only honest way to observe what it computes is to let the
script run and inspect what it tried to send. That is done by putting a
fake `curl` first on PATH (it logs its own invocation and answers with a
canned getMyCommands body) and supplying a throwaway fake .env with an
obviously-fake token. Nothing here reimplements the merge.

Run:
    python3 test_register_commands.py
    python3 -m unittest test_register_commands.py -v
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REGISTER_SH = SCRIPT_DIR / "register-commands.sh"

# Obviously fake - the digits are a placeholder shape, not anybody's token.
FAKE_TOKEN = "123456:FAKE-TEST-TOKEN-NOT-A-REAL-ONE"
FAKE_CHAT_ID = "999999999"

FAKE_CURL_STUB = r"""#!/usr/bin/env bash
# Fake curl: never touches the network.
#   - logs every invocation's full argument list to $CURL_LOG, one line each;
#   - answers getMyCommands with whatever JSON is in $FAKE_EXISTING;
#   - records a setMyCommands payload to $SET_LOG and answers ok.
printf '%s\n' "$*" >> "$CURL_LOG"

payload=""
url=""
prev=""
for arg in "$@"; do
  case "$prev" in
    --data-urlencode) payload="$arg" ;;
  esac
  case "$arg" in
    https://*) url="$arg" ;;
  esac
  prev="$arg"
done

case "$url" in
  *"/setMyCommands")
    printf '%s\n' "${payload#commands=}" >> "$SET_LOG"
    echo '{"ok":true,"result":true}'
    ;;
  *"/getMyCommands")
    cat "$FAKE_EXISTING"
    ;;
  *)
    echo "fake curl: unexpected url" >&2
    exit 1
    ;;
esac
exit 0
"""


class RegisterCommandsTestCase(unittest.TestCase):
    """Shared harness: a throwaway bridge dir holding a copy of the real
    script, a fake .env, and a fake curl on PATH.
    """

    def run_script(self, commands=None, existing=None, args=None, env_contents=None):
        """Run the real register-commands.sh with `commands` substituted into
        its COMMANDS array and `existing` as what getMyCommands returns.

        `commands=None` means "leave the shipped array exactly as it is" -
        which is how the empty-default test exercises the real file rather
        than a rewritten one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bridge = tmp_path / "bridge"
            bridge.mkdir()

            script = bridge / "register-commands.sh"
            source = REGISTER_SH.read_text()
            if commands is not None:
                lines = "\n".join(f'  "{c}"' for c in commands)
                source, n = re.subn(
                    r"COMMANDS=\(\n.*?\n\)",
                    "COMMANDS=(\n" + lines + "\n)",
                    source,
                    count=1,
                    flags=re.S,
                )
                self.assertEqual(1, n, "the COMMANDS array must still be substitutable")
            script.write_text(source)
            script.chmod(0o755)

            if env_contents is None:
                env_contents = (
                    f"TELEGRAM_BOT_TOKEN={FAKE_TOKEN}\nTELEGRAM_CHAT_ID={FAKE_CHAT_ID}\n"
                )
            if env_contents is not False:
                (bridge / ".env").write_text(env_contents)

            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            curl = bin_dir / "curl"
            curl.write_text(FAKE_CURL_STUB)
            curl.chmod(0o755)

            existing_file = tmp_path / "existing.json"
            # Compact separators on purpose: the real Telegram API answers
            # `{"ok":true,...}` with no space, and the script's fast check is a
            # literal `grep -q '"ok":true'`. A prettified fixture would fail
            # that grep and test nothing but our own formatting.
            existing_file.write_text(
                json.dumps(
                    {"ok": True, "result": existing if existing is not None else []},
                    separators=(",", ":"),
                )
            )
            curl_log = tmp_path / "curl.log"
            set_log = tmp_path / "set.log"
            curl_log.touch()
            set_log.touch()

            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            env["CURL_LOG"] = str(curl_log)
            env["SET_LOG"] = str(set_log)
            env["FAKE_EXISTING"] = str(existing_file)

            result = subprocess.run(
                [str(script), *(args or [])],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmp_path,  # NOT the bridge dir: proves .env is read from next to the script
                env=env,
            )
            sets = [json.loads(line) for line in set_log.read_text().splitlines() if line.strip()]
            return result, curl_log.read_text(), sets


class EmptyCommandListTests(RegisterCommandsTestCase):
    """The kit's shipped state: COMMANDS is all comments."""

    def test_shipped_script_with_no_commands_is_a_clean_no_op(self):
        result, _, sets = self.run_script(existing=[{"command": "existing", "description": "kept"}])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("nothing to register", result.stdout)
        self.assertEqual([], sets, "an empty list must never issue a setMyCommands write")

    def test_empty_array_does_not_trip_set_u(self):
        """bash 3.2 + `set -u` + "${EMPTY[@]}" is an unbound variable error.
        The guard exists precisely so the shipped script does not die there.
        """
        result, _, _ = self.run_script(existing=[])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("unbound variable", result.stderr)

    def test_empty_list_still_reports_the_current_menu(self):
        result, _, _ = self.run_script(existing=[{"command": "existing", "description": "kept"}])
        self.assertIn("existing", result.stdout, "the caller must still see what is registered")


class AdditiveMergeTests(RegisterCommandsTestCase):
    def test_a_command_registered_elsewhere_survives_our_merge(self):
        result, _, sets = self.run_script(
            commands=["ours|Our command"],
            existing=[{"command": "theirs", "description": "Registered by somebody else"}],
        )
        self.assertEqual(0, result.returncode, result.stderr)
        sent = sets[-1]
        self.assertEqual(
            ["theirs", "ours"],
            [c["command"] for c in sent],
            "existing commands keep their order and come first",
        )
        self.assertEqual("Registered by somebody else", sent[0]["description"])

    def test_a_changed_description_is_updated_in_place_not_duplicated(self):
        _, _, sets = self.run_script(
            commands=["ours|New wording"],
            existing=[
                {"command": "theirs", "description": "untouched"},
                {"command": "ours", "description": "Old wording"},
            ],
        )
        sent = sets[-1]
        self.assertEqual(["theirs", "ours"], [c["command"] for c in sent])
        self.assertEqual("New wording", sent[1]["description"])

    def test_several_commands_are_all_registered(self):
        _, _, sets = self.run_script(commands=["one|First", "two|Second"], existing=[])
        self.assertEqual(["one", "two"], [c["command"] for c in sets[-1]])


class IdempotencyTests(RegisterCommandsTestCase):
    def test_re_running_with_nothing_to_change_writes_nothing(self):
        result, _, sets = self.run_script(
            commands=["ours|Our command"],
            existing=[{"command": "ours", "description": "Our command"}],
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("already up to date", result.stdout)
        self.assertEqual([], sets, "a no-op run must not issue a setMyCommands write")

    def test_a_no_op_run_is_detected_even_when_others_are_registered_too(self):
        _, _, sets = self.run_script(
            commands=["ours|Our command"],
            existing=[
                {"command": "theirs", "description": "untouched"},
                {"command": "ours", "description": "Our command"},
            ],
        )
        self.assertEqual([], sets)


class ListOnlyTests(RegisterCommandsTestCase):
    def test_list_prints_the_menu_and_changes_nothing(self):
        result, curl_log, sets = self.run_script(
            commands=["ours|Our command"],
            existing=[{"command": "theirs", "description": "untouched"}],
            args=["--list"],
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("theirs", result.stdout)
        self.assertEqual([], sets, "--list must never write")
        self.assertNotIn("setMyCommands", curl_log)


class UnconfiguredBridgeExitCodeTests(RegisterCommandsTestCase):
    """Same contract as notify.sh/react.sh/send-file.sh/typing.sh - exit 1,
    not a silent 0, when the bridge isn't configured.
    """

    def test_missing_env_file_exits_1(self):
        result, _, _ = self.run_script(env_contents=False)
        self.assertEqual(1, result.returncode)
        self.assertIn(".env not found", result.stderr)

    def test_blank_token_exits_1(self):
        result, _, _ = self.run_script(env_contents="TELEGRAM_BOT_TOKEN=\n")
        self.assertEqual(1, result.returncode)
        self.assertIn("TELEGRAM_BOT_TOKEN not set", result.stderr)


class TokenHygieneTests(RegisterCommandsTestCase):
    """The token is interpolated into a curl URL and must never be echoed -
    transcripts and CI logs persist, so a printed secret is a leaked one.
    """

    def _assert_token_absent(self, result):
        self.assertNotIn(FAKE_TOKEN, result.stdout, "the token must never reach stdout")
        self.assertNotIn(FAKE_TOKEN, result.stderr, "the token must never reach stderr")

    def test_token_is_not_printed_on_a_successful_register(self):
        result, _, _ = self.run_script(commands=["ours|Our command"], existing=[])
        self._assert_token_absent(result)

    def test_token_is_not_printed_on_the_empty_list_path(self):
        result, _, _ = self.run_script(existing=[])
        self._assert_token_absent(result)

    def test_token_is_not_printed_on_list(self):
        result, _, _ = self.run_script(existing=[], args=["--list"])
        self._assert_token_absent(result)

    def test_token_is_not_printed_on_the_idempotent_path(self):
        result, _, _ = self.run_script(
            commands=["ours|Our command"],
            existing=[{"command": "ours", "description": "Our command"}],
        )
        self._assert_token_absent(result)


class ShippedFileTests(unittest.TestCase):
    """Properties of the file as committed, independent of any run."""

    def test_script_is_executable(self):
        self.assertTrue(os.access(REGISTER_SH, os.X_OK), "register-commands.sh must ship executable")

    def test_shipped_commands_array_is_empty(self):
        """The kit is project-agnostic: no project's commands ship in it."""
        body = re.search(r"COMMANDS=\(\n(.*?)\n\)", REGISTER_SH.read_text(), re.S).group(1)
        live = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        self.assertEqual([], live, f"the shipped COMMANDS array must be all comments, found: {live}")

    def test_no_credentials_are_committed_in_the_script(self):
        text = REGISTER_SH.read_text()
        self.assertNotIn("api.telegram.org/bot1", text, "no literal token may be committed")


if __name__ == "__main__":
    unittest.main()
