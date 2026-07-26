#!/usr/bin/env python3
"""
test_daily_report.py - Offline unit tests for daily_report.py's
significance gate and --dry-run flag (see daily_report.py's module
docstring "SIGNIFICANCE GATE" / "DRY RUN" sections).

Most days now send NOTHING: the digest only fires on a commit-volume spike
over a trailing baseline, or a flagged keyword in a commit message.
ComputeRecentDailyCommitAverageTests / EvaluateSignificanceTests cover the
pure logic; SignificanceGateEndToEndTests covers main() actually acting on
it (routine day -> silent, marker not advanced; significant day -> sent,
marker advanced; --dry-run -> never sends, never advances the marker;
DIGEST_ALWAYS_SEND=1 -> bypasses the gate entirely).

No real network/subprocess I/O: git/`claude -p` calls are patched out via
mock.patch.object on daily_report's own functions (get_commits_since_marker/
run_claude_digest/get_head_commit/save_last_report/
compute_recent_daily_commit_average), and Telegram sends are patched at the
telegram_common module level - never touches this repo's real
.last_report or Telegram chat.

Run:
    python3 test_daily_report.py
    python3 -m unittest test_daily_report.py -v
"""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import daily_report as dr
import telegram_common as tc

# Same rationale as elsewhere: silence the root logger for this test
# module's duration so it never writes into the real daily_report.log
# next to daily_report.py.
logging.getLogger().handlers = [logging.NullHandler()]


class ComputeRecentDailyCommitAverageTests(unittest.TestCase):
    def test_averages_commit_count_over_the_window(self):
        with mock.patch.object(dr, "run_git", return_value=(0, "a\nb\nc\nd\ne\nf\ng", "")):
            avg = dr.compute_recent_daily_commit_average("/fake/cwd", days=7)
        self.assertAlmostEqual(avg, 1.0)  # 7 commits / 7 days

    def test_git_failure_returns_zero_not_a_crash(self):
        with mock.patch.object(dr, "run_git", return_value=(128, "", "not a git repository")):
            avg = dr.compute_recent_daily_commit_average("/fake/cwd", days=7)
        self.assertEqual(avg, 0.0)

    def test_empty_history_is_zero(self):
        with mock.patch.object(dr, "run_git", return_value=(0, "", "")):
            avg = dr.compute_recent_daily_commit_average("/fake/cwd", days=7)
        self.assertEqual(avg, 0.0)


class EvaluateSignificanceTests(unittest.TestCase):
    def test_low_volume_no_keywords_is_routine(self):
        git_log = "abc1234 Fix a typo\ndef5678 Update copy"
        is_significant, reason = dr.evaluate_significance(git_log, baseline_avg=5.0)
        self.assertFalse(is_significant)
        self.assertIsNone(reason)

    def test_commit_count_at_or_above_floor_and_multiplier_is_significant(self):
        # baseline 1.0/day * 1.5 = 1.5 -> threshold is MIN_SIGNIFICANT_COMMITS (3)
        # since that floor is higher; 3 commits clears it.
        git_log = "\n".join(f"{i:07x} Routine commit {i}" for i in range(3))
        is_significant, reason = dr.evaluate_significance(git_log, baseline_avg=1.0)
        self.assertTrue(is_significant)
        self.assertIn("spike", reason)

    def test_below_floor_commit_count_is_routine_even_with_high_ratio(self):
        # 2 commits vs baseline 0.1/day is technically a huge ratio, but
        # MIN_SIGNIFICANT_COMMITS (3) floors it - must not fire.
        git_log = "abc1234 One thing\ndef5678 Another thing"
        is_significant, _reason = dr.evaluate_significance(git_log, baseline_avg=0.1)
        self.assertFalse(is_significant)

    def test_keyword_match_is_significant_regardless_of_volume(self):
        git_log = "abc1234 Revert: bad deploy"
        is_significant, reason = dr.evaluate_significance(git_log, baseline_avg=10.0)
        self.assertTrue(is_significant)
        self.assertIn("keyword", reason)

    def test_keyword_match_is_case_insensitive(self):
        git_log = "abc1234 URGENT hotfix for prod outage"
        is_significant, reason = dr.evaluate_significance(git_log, baseline_avg=10.0)
        self.assertTrue(is_significant)

    def test_high_baseline_requires_proportionally_more_commits(self):
        # baseline 20/day * 1.5 = 30 -> 10 routine commits must NOT fire.
        git_log = "\n".join(f"{i:07x} Routine commit {i}" for i in range(10))
        is_significant, _reason = dr.evaluate_significance(git_log, baseline_avg=20.0)
        self.assertFalse(is_significant)


class SignificanceGateEndToEndTests(unittest.TestCase):
    def _write_env(self, tmp_path, extra=""):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "TELEGRAM_BOT_TOKEN=faketoken\n"
            "TELEGRAM_CHAT_ID=12345\n"
            "CLAUDE_DEFAULT_CWD=/tmp\n" + extra,
            encoding="utf-8",
        )
        return env_path

    def test_zero_commits_sends_nothing_and_does_not_touch_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path)

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value=""), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked") as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 0)
        mock_send.assert_not_called()
        mock_save.assert_not_called()

    def test_routine_day_sends_nothing_and_does_not_advance_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path)

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value="abc1234 Small routine fix"), \
                    mock.patch.object(dr, "compute_recent_daily_commit_average", return_value=10.0), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked") as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 0)
        mock_send.assert_not_called()
        mock_save.assert_not_called()  # routine day must NOT advance the marker

    def test_significant_day_sends_and_advances_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path)

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value="abc1234 security: patch CVE"), \
                    mock.patch.object(dr, "compute_recent_daily_commit_average", return_value=1.0), \
                    mock.patch.object(dr, "run_claude_digest", return_value=(True, "Patched a CVE.")), \
                    mock.patch.object(dr, "get_head_commit", return_value="deadbeef"), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked", return_value=True) as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 0)
        mock_send.assert_called_once()
        mock_save.assert_called_once_with("deadbeef", mock.ANY)

    def test_dry_run_never_sends_and_never_advances_marker_even_when_significant(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path)

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value="abc1234 Revert: rollback release"), \
                    mock.patch.object(dr, "compute_recent_daily_commit_average", return_value=1.0), \
                    mock.patch.object(dr, "run_claude_digest", return_value=(True, "Rolled back a release.")), \
                    mock.patch.object(dr, "get_head_commit", return_value="deadbeef"), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked") as mock_send:
                exit_code = dr.main(["--dry-run"])

        self.assertEqual(exit_code, 0)
        mock_send.assert_not_called()
        mock_save.assert_not_called()

    def test_digest_always_send_bypasses_gate_on_routine_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path, extra="DIGEST_ALWAYS_SEND=1\n")

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value="abc1234 Small routine fix"), \
                    mock.patch.object(dr, "compute_recent_daily_commit_average") as mock_baseline, \
                    mock.patch.object(dr, "run_claude_digest", return_value=(True, "Routine summary.")), \
                    mock.patch.object(dr, "get_head_commit", return_value="deadbeef"), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked", return_value=True) as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 0)
        mock_baseline.assert_not_called()  # gate bypassed entirely, baseline never computed
        mock_send.assert_called_once()
        mock_save.assert_called_once_with("deadbeef", mock.ANY)

    def test_digest_always_send_sends_nothing_new_notice_on_zero_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = self._write_env(tmp_path, extra="DIGEST_ALWAYS_SEND=1\n")

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(dr, "get_commits_since_marker", return_value=""), \
                    mock.patch.object(dr, "get_head_commit", return_value="deadbeef"), \
                    mock.patch.object(dr, "save_last_report") as mock_save, \
                    mock.patch.object(tc, "send_message_chunked", return_value=True) as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 0)
        mock_send.assert_called_once()
        sent_message = mock_send.call_args[0][2]
        self.assertIn("nothing new", sent_message)
        mock_save.assert_called_once_with("deadbeef", mock.ANY)

    def test_missing_env_vars_exits_without_sending(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env_path = tmp_path / ".env"
            env_path.write_text("TELEGRAM_BOT_TOKEN=faketoken\n", encoding="utf-8")  # missing chat id / cwd

            with mock.patch.object(dr, "ENV_FILE", env_path), \
                    mock.patch.object(tc, "send_message_chunked") as mock_send:
                exit_code = dr.main([])

        self.assertEqual(exit_code, 1)
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
