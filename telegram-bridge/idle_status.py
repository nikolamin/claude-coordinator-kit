#!/usr/bin/env python3
"""
idle_status.py - Silence-triggered status post for the Telegram bridge.

Behaviour (all intervals configurable in .env, see .env.example):

- After IDLE_STATUS_AFTER_MINUTES (default 45) with no message exchanged in
  either direction - no founder message or button press, and nothing sent by
  notify/ask/send-file - post ONE silent status message to the founder chat.
- While the silence continues, rebuild the status every
  IDLE_STATUS_REFRESH_MINUTES (default 40) and edit the same post in place,
  but only if the status text actually changed.
- As soon as any message is exchanged again, delete the post.

"Exchanged" is read from the `.last-exchange` marker's mtime, which bot.py
touches for every relayed inbound message and every outbound sender script
touches after Telegram accepted its send (telegram_common.mark_exchange()).
Typing indicators, reactions and this module's own post/edit do NOT count,
so the status post never resets the silence it reports on.

Status text sources (both may be set - a machine-level bridge can serve a
plugin-install project and a file-copy project at once; configure_bridge.py
writes them):
  - STATUS_COMMANDS - shell commands joined by " ;; ", one per project, each
    printing a status block (e.g. the coordinator plugin's
    `coord.py --root <project> status`). 60s timeout each. A single legacy
    STATUS_COMMAND is read too.
  - STATUS_FILES - comma-separated paths. A coordinator STATE.md contributes
    only its `## Current` section; any other file contributes its whole text.
  - Neither configured - a minimal post that names the missing setting, so a
    misconfiguration is visible instead of silently absent.

bot.py calls tick() once at the end of every poll cycle (RELAY_MODE only).
This module is the only writer of IDLE_STATE_FILE; the sender scripts only
touch the exchange marker, so there is no cross-process write race.

Only stdlib + `requests` (via telegram_common) are used.
"""

import hashlib
import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

import telegram_common

log = logging.getLogger("claude-telegram-bridge")

SCRIPT_DIR = Path(__file__).resolve().parent
IDLE_STATE_FILE = SCRIPT_DIR / "idle-status.json"
EXCHANGE_FILE = SCRIPT_DIR / ".last-exchange"

DEFAULT_AFTER_MINUTES = 45
DEFAULT_REFRESH_MINUTES = 40
STATUS_COMMAND_TIMEOUT = 60
MAX_BODY_CHARS = 3500
# Bots may only delete messages younger than 48h; rotate the post before that
# so a very long silence never leaves an undeletable stale status behind.
ROTATE_AFTER_SECONDS = 46 * 3600
SEND_BACKOFF_SECONDS = 300

# Telegram descriptions that mean "the post is gone or can never be touched
# again" - drop it from state instead of retrying forever.
_GONE_MARKERS = (
    "message to delete not found",
    "message to edit not found",
    "message can't be deleted",
    "message can't be edited",
    "chat not found",
    "bot was blocked",
)


def _truthy(value, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _minutes(value, default: int) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


COMMAND_SEPARATOR = " ;; "


def split_commands(value) -> list:
    """STATUS_COMMANDS holds one command per project, joined by " ;; "."""
    return [c.strip() for c in (value or "").split(COMMAND_SEPARATOR.strip()) if c.strip()]


def load_settings(env: dict) -> dict:
    files = [p.strip() for p in (env.get("STATUS_FILES") or "").split(",") if p.strip()]
    return {
        "enabled": _truthy(env.get("IDLE_STATUS_ENABLED"), True),
        "after_seconds": _minutes(env.get("IDLE_STATUS_AFTER_MINUTES"), DEFAULT_AFTER_MINUTES) * 60,
        "refresh_seconds": _minutes(env.get("IDLE_STATUS_REFRESH_MINUTES"), DEFAULT_REFRESH_MINUTES) * 60,
        "silent": _truthy(env.get("IDLE_STATUS_SILENT"), True),
        "status_commands": split_commands(env.get("STATUS_COMMANDS")) + split_commands(env.get("STATUS_COMMAND")),
        "status_files": files,
    }


# --------------------------------------------------------------------------
# Status text
# --------------------------------------------------------------------------

def extract_current_section(text: str) -> str:
    """Return the body of a markdown `## Current` section, or "" if absent."""
    lines = text.splitlines()
    out = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().lower().startswith("current")
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def _project_label(path: Path) -> str:
    # <project>/docs/coordination/STATE.md -> "<project>"
    parts = path.resolve().parts
    if len(parts) >= 4 and parts[-3:-1] == ("docs", "coordination"):
        return parts[-4]
    return path.name


def read_status_file(path_str: str) -> str:
    path = Path(path_str).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"[{path_str}: unreadable ({exc.__class__.__name__})]"
    body = extract_current_section(text) if "## Current" in text else text.strip()
    if not body:
        body = "(no Current section)"
    return f"{_project_label(path)}:\n{body}"


def run_status_command(command: str) -> str:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=STATUS_COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return "[status command timed out]"
    except OSError as exc:
        return f"[status command failed to start: {exc.__class__.__name__}]"
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        # stderr can be long or noisy; keep only its last line, never the
        # environment or the command line itself.
        err_tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
        return (out + "\n" if out else "") + f"[status command exit {proc.returncode}: {err_tail[0][:200]}]"
    return out or "(status command printed nothing)"


def build_status_body(settings: dict) -> str:
    parts = []
    parts.extend(run_status_command(c) for c in settings["status_commands"])
    parts.extend(read_status_file(p) for p in settings["status_files"])
    body = "\n\n".join(parts) if parts else (
        "No status source configured - set STATUS_FILES or STATUS_COMMANDS in the bridge .env "
        "(configure_bridge.py does this)."
    )
    if len(body) > MAX_BODY_CHARS:
        body = body[: MAX_BODY_CHARS - 20].rstrip() + "\n... (truncated)"
    return body


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def render_post(body: str, quiet_since: float, now: float) -> str:
    return f"⏳ Status - quiet since {_hhmm(quiet_since)}\n\n{body}\n\n(updated {_hhmm(now)}; deleted on the next message)"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_state(path: Path = IDLE_STATE_FILE) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: Path = IDLE_STATE_FILE) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(path)


def last_exchange(path: Path = EXCHANGE_FILE):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _is_gone(resp: dict) -> bool:
    desc = str(resp.get("description", "")).lower()
    return any(marker in desc for marker in _GONE_MARKERS)


# --------------------------------------------------------------------------
# Tick
# --------------------------------------------------------------------------

def _delete_post(api, post: dict) -> str:
    """Return "deleted", "gone" (already unreachable - drop it) or "retry"."""
    try:
        resp = api("deleteMessage", {"chat_id": post["chat_id"], "message_id": post["message_id"]})
    except Exception as exc:  # network: keep state, retry next tick
        log.warning("idle-status: delete failed, will retry: %s", telegram_common.redact_secrets(exc))
        return "retry"
    if resp.get("ok"):
        return "deleted"
    if _is_gone(resp) or resp.get("error_code") in (400, 403):
        log.info("idle-status: post %s no longer deletable (%s); dropping it.", post.get("message_id"), resp.get("description"))
        return "gone"
    log.warning("idle-status: delete rejected, will retry: %s", resp.get("description"))
    return "retry"


def _send_post(api, chat_id, settings: dict, quiet_since: float, now: float):
    body = build_status_body(settings)
    payload = {
        "chat_id": chat_id,
        "text": render_post(body, quiet_since, now),
        "disable_notification": bool(settings["silent"]),
    }
    try:
        resp = api("sendMessage", payload)
    except Exception as exc:
        log.warning("idle-status: send failed: %s", telegram_common.redact_secrets(exc))
        return None
    if not resp.get("ok"):
        log.warning("idle-status: send rejected: %s", resp.get("description"))
        return None
    message_id = (resp.get("result") or {}).get("message_id")
    if message_id is None:
        return None
    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "posted_at": float(int(now)),
        "checked_at": now,
        "hash": body_hash(body),
    }


def tick(api, chat_id, settings: dict, now: float = None,
         state_path: Path = IDLE_STATE_FILE, exchange_path: Path = EXCHANGE_FILE) -> str:
    """Advance the idle-status state machine once. Returns the action taken.

    `api(method, payload) -> dict` performs one Bot API call (see
    telegram_common.api_call); injected so tests never touch the network.
    """
    now = time.time() if now is None else now
    state = load_state(state_path)
    post = state.get("post")

    if not settings["enabled"]:
        if post:
            if _delete_post(api, post) == "retry":
                return "retry_delete"
            save_state({}, state_path)
            return "deleted"
        return "disabled"

    ex = last_exchange(exchange_path)
    if ex is None:
        # First run on this machine: start the silence clock now rather than
        # treating "no marker" as "silent since the epoch".
        telegram_common.mark_exchange(exchange_path)
        return "init"

    if post:
        # posted_at is stored floored to whole seconds and compared with >=,
        # so an exchange in the same second as the post still deletes it on
        # filesystems whose mtimes have 1-2s resolution (HFS+, FAT, some
        # network/WSL mounts). Posting needs >= 45 min of quiet, so an
        # exchange *before* the post can never fall in that same second.
        if ex >= post.get("posted_at", 0):
            if _delete_post(api, post) == "retry":
                return "retry_delete"
            save_state({}, state_path)
            return "deleted"

        if now - post.get("posted_at", now) >= ROTATE_AFTER_SECONDS:
            if _delete_post(api, post) == "retry":
                return "retry_delete"
            new_post = _send_post(api, chat_id, settings, ex, now)
            save_state({"post": new_post} if new_post else {}, state_path)
            return "rotated" if new_post else "send_failed"

        if now - post.get("checked_at", 0) < settings["refresh_seconds"]:
            return "waiting"

        body = build_status_body(settings)
        new_hash = body_hash(body)
        post["checked_at"] = now
        if new_hash == post.get("hash"):
            save_state({"post": post}, state_path)
            return "unchanged"
        try:
            resp = api("editMessageText", {
                "chat_id": post["chat_id"],
                "message_id": post["message_id"],
                "text": render_post(body, ex, now),
            })
        except Exception as exc:
            log.warning("idle-status: edit failed, will retry: %s", telegram_common.redact_secrets(exc))
            return "retry_edit"
        if resp.get("ok") or "not modified" in str(resp.get("description", "")).lower():
            post["hash"] = new_hash
            save_state({"post": post}, state_path)
            return "edited"
        if _is_gone(resp):
            # The founder deleted it by hand (or it aged out): forget it; the
            # next tick posts a fresh one while the silence continues.
            save_state({}, state_path)
            return "gone"
        log.warning("idle-status: edit rejected: %s", resp.get("description"))
        save_state({"post": post}, state_path)
        return "edit_rejected"

    if now - ex < settings["after_seconds"]:
        return "quiet_not_long_enough"

    if now < state.get("send_backoff_until", 0):
        return "backoff"

    new_post = _send_post(api, chat_id, settings, ex, now)
    if not new_post:
        # Don't hammer Telegram every poll cycle while it is down/refusing.
        save_state({"send_backoff_until": now + SEND_BACKOFF_SECONDS}, state_path)
        return "send_failed"
    save_state({"post": new_post}, state_path)
    return "posted"
