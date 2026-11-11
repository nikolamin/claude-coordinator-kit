#!/usr/bin/env python3
"""
configure_bridge.py - Turn on (and keep on) every founder-facing Telegram
feature for a coordinator project. Idempotent; safe on a live, shared bridge.
Install and update BOTH run it, so an updated bridge never silently lacks a
feature that only a fresh install's prose steps used to set up.

    python3 configure_bridge.py --status-file /abs/project/docs/coordination/STATE.md
    python3 configure_bridge.py --status-command "python3 /abs/plugin/scripts/coord.py --root /abs/project status"
    python3 configure_bridge.py --remove-status-file /abs/old/project/docs/coordination/STATE.md
    python3 configure_bridge.py --check          # report readiness, change nothing

Use the bridge's own interpreter (venv/bin/python3 if SETUP.md (b) made a
venv) - this script imports requests via telegram_common.

What it does to .env (the existing file is required - create it via SETUP.md
first). Existing lines and values are never rewritten, except STATUS_FILES
and STATUS_COMMANDS (one entry per project: a passed path/command is merged
in; a command replaces an older entry for the same `--root`, e.g. after a
plugin upgrade moved its path):
  - adds RELAY_MODE=1 if the key is absent (👀 reactions, buttons, idle status
    and the command relay all need relay mode); an explicit RELAY_MODE=0 is
    left alone and reported, since another setup on this machine chose it
  - adds the idle-status defaults if absent: IDLE_STATUS_ENABLED=1,
    IDLE_STATUS_AFTER_MINUTES=45, IDLE_STATUS_REFRESH_MINUTES=40,
    IDLE_STATUS_SILENT=1
Then it registers the Telegram "/" command menu (register-commands.sh, or
register-commands.ps1 on Windows) unless --no-commands is given.

Never prints a secret: it reports key NAMES it added and only the values of
the non-secret keys it wrote itself.
"""

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path

import telegram_common

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"

DEFAULTS = [
    ("RELAY_MODE", "1", "Relay to the live coordinator session (needed for 👀/👍 reactions, question buttons, idle status, commands)."),
    ("IDLE_STATUS_ENABLED", "1", "Post a status message after a quiet spell; deleted on the next message."),
    ("IDLE_STATUS_AFTER_MINUTES", "45", "Minutes with no message either way before the status post appears."),
    ("IDLE_STATUS_REFRESH_MINUTES", "40", "While still quiet, re-check this often and edit the post if the status changed."),
    ("IDLE_STATUS_SILENT", "1", "Post without a notification sound."),
]


def active_key(line: str):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def shell_safe(value: str) -> str:
    """Single-quote a value for .env. notify.sh/react.sh `source` this file
    in bash, so an unquoted `STATUS_COMMAND=python3 x.py` line would RUN
    x.py on every send; single quotes make bash read it as a literal and
    telegram_common.parse_env_file() strips them again."""
    if "'" in value or " #" in value or "\n" in value:
        raise ValueError("value must not contain a single quote, ' #', or a newline")
    return f"'{value}'"


def set_line(lines, key, value):
    """Replace the active KEY= line in place, or append one. Returns lines."""
    entry = f"{key}={shell_safe(value)}"
    for i, line in enumerate(lines):
        if active_key(line) == key:
            lines[i] = entry
            return lines
    lines.append(entry)
    return lines


SEPARATOR = " ;; "


def split_commands(value) -> list:
    return [c.strip() for c in (value or "").split(SEPARATOR.strip()) if c.strip()]


def root_of(command: str):
    """The `--root <path>` a plugin status command names, or None."""
    parts = command.split()
    for i, part in enumerate(parts[:-1]):
        if part == "--root":
            return parts[i + 1]
        if part.startswith("--root="):
            return part.split("=", 1)[1]
    return None


def plan_changes(env_text: str, values: dict, status_files, status_command, remove_files=None):
    """Pure: return (new_text, report_lines). `values` is the parsed .env."""
    lines = env_text.splitlines()
    report = []
    added = []
    for key, default, comment in DEFAULTS:
        if key not in values:
            added.append((key, default, comment))
    if added:
        lines.append("")
        lines.append("# --- Founder Telegram features (added by configure_bridge.py) ---")
        for key, default, comment in added:
            lines.append(f"# {comment}")
            lines.append(f"{key}={default}")
            report.append(f"added {key}={default}")

    # Adds and removals apply to ONE running list: computing the removal from
    # the original value would silently drop a path added in the same run.
    current = [p.strip() for p in (values.get("STATUS_FILES") or "").split(",") if p.strip()]
    merged = list(current)
    for path in status_files or []:
        path = str(Path(path).expanduser().resolve())
        if path not in merged:
            merged.append(path)
            report.append(f"STATUS_FILES += {path}")
    for path in remove_files or []:
        path = str(Path(path).expanduser().resolve())
        if path in merged:
            merged.remove(path)
            report.append(f"STATUS_FILES -= {path}")
    if merged != current:
        lines = set_line(lines, "STATUS_FILES", ",".join(merged))

    if status_command is not None:
        if SEPARATOR.strip() in status_command:
            raise ValueError("a status command must not contain ';;'")
        current = split_commands(values.get("STATUS_COMMANDS"))
        root = root_of(status_command)
        kept = [c for c in current if c == status_command or root is None or root_of(c) != root]
        if status_command not in kept:
            kept.append(status_command)
        if kept != current:
            for dropped in [c for c in current if c not in kept]:
                report.append(f"STATUS_COMMANDS replaced older entry for the same project: {dropped}")
            lines = set_line(lines, "STATUS_COMMANDS", SEPARATOR.join(kept))
            report.append(f"STATUS_COMMANDS += {status_command}")

    new_text = "\n".join(lines) + "\n"
    return new_text, report


REQUIRED_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CLAUDE_DEFAULT_CWD")
BRIDGE_DOWN_PREFIX = "BRIDGE DOWN:"


def readiness(values: dict):
    """Pure: list of (ok, message) describing what the founder will get."""
    relay = str(values.get("RELAY_MODE", "")).strip().lower() in ("1", "true", "yes")
    idle = str(values.get("IDLE_STATUS_ENABLED", "1")).strip().lower() in ("1", "true", "yes", "on", "")
    sources = bool((values.get("STATUS_FILES") or "").strip() or (values.get("STATUS_COMMANDS") or "").strip()
                   or (values.get("STATUS_COMMAND") or "").strip())
    out = [
        (relay, "relay mode on (👀 then 👍/👎 reactions, button answers, command relay)" if relay
         else "RELAY_MODE is not 1 - reactions, buttons, idle status and commands are OFF"),
        (relay and idle, "idle status post enabled" if relay and idle else "idle status post disabled"),
        (sources, "idle status has a status source" if sources
         else "no STATUS_FILES / STATUS_COMMANDS - the idle post will only say it is unconfigured"),
    ]
    for path in [p.strip() for p in (values.get("STATUS_FILES") or "").split(",") if p.strip()]:
        exists = Path(path).expanduser().exists()
        out.append((exists, f"status file {'found' if exists else 'MISSING (project moved or gone? --remove-status-file it)'}: {path}"))
    # bot.py's load_config() exits at startup without these (CLAUDE_DEFAULT_CWD
    # included, even in relay mode), so "every feature on" is false while one
    # is blank - a crash-looping service delivers none of them.
    missing = [k for k in REQUIRED_KEYS if not str(values.get(k, "")).strip()]
    out.append((not missing, "bot.py's required keys are set" if not missing
                else f"{BRIDGE_DOWN_PREFIX} bot.py will not start without: {', '.join(missing)} (see SETUP.md (c))"))
    return out


def register_commands() -> int:
    if platform.system() == "Windows":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT_DIR / "register-commands.ps1")]
    else:
        cmd = ["bash", str(SCRIPT_DIR / "register-commands.sh")]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # register-commands never prints the token; still, redact defensively.
    if result.returncode != 0:
        print("command menu: FAILED - " + telegram_common.redact_secrets(result.stderr.strip()[-300:]))
    else:
        print("command menu: registered (/status /fullstatus /agents /stop /resume)")
    return result.returncode


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Enable the coordinator's Telegram features on this bridge.")
    p.add_argument("--status-file", action="append", default=[], help="absolute path to a project's STATE.md (repeatable)")
    p.add_argument("--status-command", help="shell command printing a project's status (plugin installs)")
    p.add_argument("--remove-status-file", action="append", default=[], help="drop a project's STATE.md from STATUS_FILES")
    p.add_argument("--no-commands", action="store_true", help="skip registering the / command menu")
    p.add_argument("--check", action="store_true", help="report readiness only; change nothing")
    args = p.parse_args(argv)

    if not ENV_FILE.exists():
        print(f"Error: {ENV_FILE} not found - create it per SETUP.md (c) first.", file=sys.stderr)
        return 1
    values = telegram_common.parse_env_file(ENV_FILE)

    if not args.check:
        try:
            new_text, report = plan_changes(ENV_FILE.read_text(encoding="utf-8"), values,
                                            args.status_file, args.status_command, args.remove_status_file)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if report:
            # Created 0600 from the first byte: the token must never sit in a
            # world-readable temp file, even if this process dies mid-write.
            tmp = ENV_FILE.with_name(".env.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(new_text)
            os.chmod(tmp, ENV_FILE.stat().st_mode & 0o777 & ~0o077 or 0o600)
            tmp.replace(ENV_FILE)
            for line in report:
                print(line)
        else:
            print(".env already has every feature setting")
        values = telegram_common.parse_env_file(ENV_FILE)

    rc = 0
    for ok, message in readiness(values):
        print(("ok    " if ok else "WARN  ") + message)
        if not ok and message.startswith(("RELAY_MODE", BRIDGE_DOWN_PREFIX)):
            rc = 2

    if not args.check and not args.no_commands:
        if register_commands() != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
