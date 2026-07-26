#!/usr/bin/env python3
"""
daily_report.py - Daily activity-digest report for CLAUDE_DEFAULT_CWD.

One-shot script (meant to be run once a day by launchd/systemd, see the
plist/timer templates in this directory): looks at what git history has
landed in CLAUDE_DEFAULT_CWD since the last time this script successfully
reported, asks `claude -p` (a one-shot call, not --continue) to turn that
into a short human-readable digest, and sends it to the configured Telegram
chat.

A "last reported" marker (commit hash + timestamp) is persisted to
LAST_REPORT_FILE (.last_report, next to this script) and is only advanced
after the Telegram send succeeds, so a failed send never silently drops a
day's activity - it will just be included in the next successful report.

SIGNIFICANCE GATE: by default this script does NOT send a digest every
day - it only sends when today's activity looks significant, meaning
either of:
  1. COMMIT-VOLUME SPIKE: the number of commits in this report is a large
     jump over the recent normal rate - compared against a trailing
     BASELINE_WINDOW_DAYS-day average commit rate computed directly from
     git history (no persisted state needed - `git log --since/--until`
     against real timestamps), floored at MIN_SIGNIFICANT_COMMITS so a
     quiet/low-baseline repo doesn't flag on a single routine commit - see
     compute_recent_daily_commit_average() / evaluate_significance().
  2. FLAGGED KEYWORDS: any commit's `--oneline` summary contains a word
     from SIGNIFICANT_COMMIT_KEYWORDS (revert, hotfix, incident, security,
     ...) - catches a single noteworthy commit even on an otherwise quiet,
     low-volume day, independent of the volume check above.
If NEITHER condition fires, this script sends NOTHING - not even a
"nothing new" message. Silence is the correct, expected default. Zero
commits since the marker is always treated as routine (silent) too.

WHEN A ROUTINE DAY IS SKIPPED, THE MARKER IS DELIBERATELY *NOT* ADVANCED:
"successful send" and "day evaluated" are not the same event. Leaving the
marker alone means those routine commits are simply folded into whichever
future report DOES end up sending (the next significant day, if any) - so
nothing is ever silently lost, it's just batched until something worth
mentioning happens. This mirrors this script's pre-existing "never
silently drop activity" invariant, extended to cover "silently skipped
because it wasn't significant" the same way it already covered "silently
skipped because the send failed".

Set DIGEST_ALWAYS_SEND=1 in .env to bypass the significance gate entirely
and go back to sending a digest unconditionally every run (the pre-gate
behavior) - escape hatch for repos/situations where the gate isn't wanted.

DRY RUN: pass --dry-run to run the full pipeline (including the
significance evaluation and, if significant, the real `claude -p`
summarization call) but skip the actual Telegram send AND skip advancing
the marker - the message that would have been sent (or a clear note that
the day was routine) is logged/printed instead. Used for manual
verification without spamming the chat or disturbing real state.

Only stdlib + `requests` (via telegram_common) are used, matching the rest
of this module.

Run manually for testing:
    python3 daily_report.py
    python3 daily_report.py --dry-run

Optional extra - skip this file entirely if you don't want a daily digest;
nothing else in this directory depends on it.
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import telegram_common

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
LOG_FILE = SCRIPT_DIR / "daily_report.log"
LAST_REPORT_FILE = SCRIPT_DIR / ".last_report"

CLAUDE_TIMEOUT = 600  # 10 minutes
TRUNCATE_LOG_CHARS = 200
FALLBACK_LOOKBACK_HOURS = 24  # used only when there's no marker yet (first run)

# --- Significance gate (see module docstring "SIGNIFICANCE GATE") ---------
BASELINE_WINDOW_DAYS = 7
MIN_SIGNIFICANT_COMMITS = 3     # floor: below this, never flag on volume alone
COMMIT_SPIKE_MULTIPLIER = 1.5   # commits-in-report >= baseline_avg * this -> spike
SIGNIFICANT_COMMIT_KEYWORDS = (
    "revert", "rollback", "urgent", "critical", "hotfix", "incident",
    "outage", "broken", "security", "vulnerab", "breaking change",
    "regression", "rolled back",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("claude-telegram-bridge")


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


def truncate(text: str, limit: int = TRUNCATE_LOG_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def load_last_report():
    """Read the persisted marker. Returns None if unset/missing/corrupt."""
    if not LAST_REPORT_FILE.exists():
        return None
    try:
        data = json.loads(LAST_REPORT_FILE.read_text(encoding="utf-8"))
        if not data.get("commit"):
            return None
        return data
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        log.warning(
            "Last-report marker file %s is missing/corrupt (%s); treating as first run.",
            LAST_REPORT_FILE,
            exc,
        )
        return None


def save_last_report(commit: str, timestamp: str) -> None:
    """Persist the marker. Writes atomically (temp file + rename)."""
    tmp_path = LAST_REPORT_FILE.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps({"commit": commit, "timestamp": timestamp}, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(LAST_REPORT_FILE)
    except OSError as exc:
        log.error("Failed to persist last-report marker: %s", exc)


def run_git(args, cwd):
    """Run a git command, returning (returncode, stdout, stderr) (all str)."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_commits_since_marker(cwd: str, marker) -> str:
    """Return `git log --oneline` output since the last marker.

    Falls back to the last FALLBACK_LOOKBACK_HOURS hours of history if
    there's no marker yet (first run), or if the marker's commit is no
    longer resolvable in this repo (e.g. history was rewritten).
    """
    if marker and marker.get("commit"):
        commit = marker["commit"]
        code, out, err = run_git(["log", "--oneline", f"{commit}..HEAD"], cwd)
        if code == 0:
            return out
        log.warning(
            "git log %s..HEAD failed (rc=%s, %s); falling back to last %sh of history.",
            commit,
            code,
            err,
            FALLBACK_LOOKBACK_HOURS,
        )

    since = (datetime.now() - timedelta(hours=FALLBACK_LOOKBACK_HOURS)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    code, out, err = run_git(["log", "--oneline", f"--since={since}"], cwd)
    if code != 0:
        raise RuntimeError(f"git log --since={since} failed: {err}")
    return out


def get_head_commit(cwd: str) -> str:
    code, out, err = run_git(["rev-parse", "HEAD"], cwd)
    if code != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {err}")
    return out


# ---------------------------------------------------------------------------
# Significance gate - see module docstring "SIGNIFICANCE GATE".
# ---------------------------------------------------------------------------

def compute_recent_daily_commit_average(cwd: str, days: int = BASELINE_WINDOW_DAYS, now: datetime = None) -> float:
    """Average commits/day over the trailing `days` days (real calendar
    time, via `git log --since/--until` against actual commit timestamps -
    no persisted state needed, unlike the report marker). Used purely as a
    baseline for evaluate_significance() below; returns 0.0 (never raises)
    on a git failure, so a baseline-computation hiccup degrades to "no
    established baseline" rather than crashing the whole run.
    """
    if now is None:
        now = datetime.now()
    until = now.strftime("%Y-%m-%d %H:%M:%S")
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    code, out, err = run_git(["log", "--oneline", f"--since={since}", f"--until={until}"], cwd)
    if code != 0:
        log.warning("Failed to compute recent commit baseline (rc=%s, %s); treating baseline as 0.", code, err)
        return 0.0
    count = len([line for line in out.splitlines() if line.strip()])
    return count / days if days else 0.0


def evaluate_significance(git_log_text: str, baseline_avg: float):
    """Decide whether `git_log_text` (this report's `--oneline` commits)
    counts as significant enough to send. Returns (is_significant: bool,
    reason: str | None). Pure function, no I/O - see the two rules in the
    module docstring's "SIGNIFICANCE GATE" section.
    """
    lines = [line for line in git_log_text.splitlines() if line.strip()]
    count = len(lines)

    threshold = max(MIN_SIGNIFICANT_COMMITS, baseline_avg * COMMIT_SPIKE_MULTIPLIER)
    if count >= threshold:
        return True, f"commit volume spike: {count} commits vs a ~{baseline_avg:.1f}/day recent baseline"

    lowered = "\n".join(lines).lower()
    hit_keywords = [kw for kw in SIGNIFICANT_COMMIT_KEYWORDS if kw in lowered]
    if hit_keywords:
        return True, f"flagged keyword(s) in commit messages: {', '.join(hit_keywords)}"

    return False, None


def build_digest_prompt(git_log_text: str) -> str:
    return (
        "You are generating a short daily activity digest to send as a Telegram "
        "message. Below is the raw `git log --oneline` output for commits that "
        "landed in this repository since the last digest.\n\n"
        "Produce a concise, readable summary: what tasks/commits landed, and call "
        "out anything that looks like it failed, is incomplete, or needs "
        "attention. Feel free to look around the repo (e.g. docs/coordination/"
        "STATE.md or similar tracking files, if present) for extra context on "
        "what these commits mean. Keep it short and readable as a chat message - "
        "no need to restate the raw log verbatim.\n\n"
        f"```\n{git_log_text}\n```"
    )


def run_claude_digest(cwd: str, git_log_text: str):
    """Run a one-shot `claude -p` call to summarize git_log_text.

    Returns (ok, output_text). Does NOT use --continue - this is always a
    fresh, standalone Claude invocation.
    """
    prompt = build_digest_prompt(git_log_text)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log.error("claude -p timed out after %s seconds while generating digest.", CLAUDE_TIMEOUT)
        return False, "Claude command timed out after 10 minutes."
    except Exception as exc:
        log.error("Failed to run claude -p for digest: %s", exc)
        return False, f"Failed to run Claude: {exc}"

    if result.returncode != 0:
        stderr_excerpt = truncate(result.stderr, 500)
        log.error(
            "claude -p exited with code %s. stderr: %s", result.returncode, stderr_excerpt
        )
        return False, f"Claude exited with an error: {stderr_excerpt}"

    return True, result.stdout


def _env_flag(value: str) -> bool:
    """Parse a loose boolean-ish .env value ('1', 'true', 'yes', 'on')."""
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Send a short daily git-activity digest to Telegram.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline (real git/claude -p calls) but skip the actual Telegram send "
             "and skip advancing the last-report marker; logs/prints the message that would have "
             "been sent instead.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    env = parse_env_file(ENV_FILE)
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
    default_cwd = env.get("CLAUDE_DEFAULT_CWD", "").strip()
    always_send = _env_flag(env.get("DIGEST_ALWAYS_SEND", ""))

    missing = [
        name
        for name, val in (
            ("TELEGRAM_BOT_TOKEN", token),
            ("TELEGRAM_CHAT_ID", chat_id),
            ("CLAUDE_DEFAULT_CWD", default_cwd),
        )
        if not val
    ]
    if missing:
        log.error(
            "Missing required .env variable(s): %s. "
            "Copy .env.example to .env and fill them in.",
            ", ".join(missing),
        )
        return 1

    marker = load_last_report()

    try:
        git_log_text = get_commits_since_marker(default_cwd, marker)
    except RuntimeError as exc:
        log.error("Failed to gather git history from %s: %s", default_cwd, exc)
        return 1

    reason = None

    if not git_log_text.strip():
        if not always_send:
            log.info("No new commits since last report; sending nothing (silence is the default).")
            return 0
        log.info("No new commits since last report; DIGEST_ALWAYS_SEND=1, sending short notice, skipping Claude.")
        message = "Daily digest: nothing new since last report."
    else:
        if not always_send:
            baseline_avg = compute_recent_daily_commit_average(default_cwd)
            is_significant, reason = evaluate_significance(git_log_text, baseline_avg)
            if not is_significant:
                log.info(
                    "Routine day (%d commit(s), ~%.1f/day recent baseline, no flagged keywords) - "
                    "sending nothing. Marker NOT advanced; these commits will be folded into "
                    "whichever future report does send.",
                    len(git_log_text.splitlines()), baseline_avg,
                )
                return 0
            log.info("Significant day: %s", reason)
        else:
            log.info("DIGEST_ALWAYS_SEND=1: bypassing significance gate, sending unconditionally.")

        ok, output = run_claude_digest(default_cwd, git_log_text)
        log.info("Digest generation ok=%s", ok)
        if ok:
            message = output.strip() or "(no output from Claude)"
        else:
            message = (
                "Daily digest: automatic summarization failed "
                f"({truncate(output, 300)}).\n\nRaw commits since last report:\n\n"
                f"{git_log_text}"
            )

    if args.dry_run:
        log.info(
            "[DRY RUN] Would send daily digest to chat_id=%s (reason: %s):\n%s",
            chat_id, reason or ("always-send" if always_send else "n/a"), message,
        )
        return 0

    try:
        sent_ok = telegram_common.send_message_chunked(token, chat_id, message)
    except Exception as exc:  # defensive: never let an unexpected send error crash us silently
        log.error("Unexpected error sending daily digest to Telegram: %s", exc)
        sent_ok = False

    if not sent_ok:
        log.error("Failed to send daily digest; NOT advancing last-report marker.")
        return 1

    try:
        head_commit = get_head_commit(default_cwd)
    except RuntimeError as exc:
        # Digest was sent, but we can't resolve HEAD to advance the marker.
        # Leaving the marker alone means next run may re-report some of the
        # same commits, which is safer than silently losing track of them.
        log.error("Sent digest but failed to resolve HEAD for marker update: %s", exc)
        return 1

    timestamp = datetime.now().astimezone().isoformat()
    save_last_report(head_commit, timestamp)
    log.info("Updated last-report marker: commit=%s timestamp=%s", head_commit, timestamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
