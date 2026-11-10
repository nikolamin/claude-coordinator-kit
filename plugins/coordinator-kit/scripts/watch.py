#!/usr/bin/env python3
"""One combined coordinator watch: silent while everything is benign, one line and exit when not.

Run it once in the background instead of one monitor per topic re-armed on a timer:

    python3 watch.py --root WORKSPACE            # blocks; prints the first actionable event, exits 0
    python3 watch.py --root WORKSPACE --once     # single pass (for a scheduler or a test)

Built in: active lanes whose recorded `deadline` (timezone-aware ISO time) has passed.
Project checks come from WORKSPACE/.coordinator/watch.json:

    {"interval_seconds": 60, "repeat_after_seconds": 1800,
     "checks": [{"name": "inbox", "command": "python3 tools/inbox.py pending", "timeout": 20}]}

A check command prints a line ONLY when the coordinator must act and prints nothing otherwise
(for example nothing for "0 pending" or an in-range reading). A check that fails without output
three times in a row is reported as CHECK_BROKEN, so a dead check is never mistaken for quiet.
An event already reported is not repeated until it changes or repeat_after_seconds passes.
The watch reads state and runs the configured commands; it never dispatches, sends or cancels.
"""
import argparse
import datetime
import hashlib
import json
import sqlite3
import subprocess
import sys
import time

from storage import Store, atomic_write, inside


def load(root):
    path = inside(root, '.coordinator/watch.json')
    config = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if not isinstance(config, dict) or not isinstance(config.get('checks', []), list):
        raise ValueError('watch.json needs an object with a "checks" list')
    return config


def overdue(root, at):
    st = Store(root, read_only=True)
    try:
        rows = [st.get(r[0]) for r in st.con.execute("SELECT id FROM records WHERE kind='lane' AND status='active' ORDER BY id")]
    finally:
        st.close()
    for row in rows:
        try:
            deadline = datetime.datetime.fromisoformat(str(row['data'].get('deadline')).replace('Z', '+00:00'))
        except ValueError:
            continue
        if deadline.tzinfo is not None and deadline < at:
            yield ('AGENT_OVERDUE lane=' + row['id'] + ' task=' + str(row['data'].get('task')) + ' agent=' +
                   str(row['data'].get('agent')) + ' deadline=' + deadline.isoformat() +
                   ' (check native status first; overdue is not dead)')


def run_checks(root, config, failures):
    for check in config.get('checks', []):
        name, command = check.get('name'), check.get('command')
        if not isinstance(name, str) or not isinstance(command, str):
            yield 'CHECK_BROKEN watch.json entry needs string "name" and "command"'
            continue
        try:
            result = subprocess.run(command, shell=True, cwd=str(root), capture_output=True, text=True,
                                    timeout=check.get('timeout', 30))
            output, code, error = result.stdout.strip(), result.returncode, result.stderr.strip()
        except subprocess.TimeoutExpired:
            output, code, error = '', 124, 'timed out'
        if output:
            failures[name] = 0
            yield name.upper() + ' ' + output.splitlines()[0][:300]
        elif code != 0:
            failures[name] = failures.get(name, 0) + 1
            if failures[name] >= 3:
                yield 'CHECK_BROKEN ' + name + ' exit=' + str(code) + ' ' + (error.splitlines()[0][:200] if error else '')
        else:
            failures[name] = 0


def fresh(root, events, at, repeat_after):
    """Drop events already reported recently; remember the ones reported now."""
    path = inside(root, '.coordinator/watch-state.json')
    try:
        seen = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    stamp = at.timestamp()
    result = []
    for event in events:
        key = hashlib.sha256(event.encode()).hexdigest()[:16]
        last = seen.get(key)
        if not isinstance(last, (int, float)) or stamp - last >= repeat_after:
            result.append(event)
            seen[key] = stamp
    if result:
        seen = {key: value for key, value in seen.items() if isinstance(value, (int, float)) and stamp - value < 7 * 86400}
        atomic_write(path, json.dumps(seen).encode())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', default='.')
    parser.add_argument('--once', action='store_true', help='Single pass, then exit')
    parser.add_argument('--interval', type=float, help='Seconds between passes (default: watch.json or 60)')
    parser.add_argument('--max-seconds', type=float, help='Stop silently after this long (only if the host limits background runs)')
    a = parser.parse_args(argv)
    failures, started = {}, time.monotonic()
    try:
        while True:
            config = load(a.root)
            at = datetime.datetime.now(datetime.timezone.utc)
            events = list(overdue(a.root, at)) + list(run_checks(a.root, config, failures))
            events = fresh(a.root, events, at, config.get('repeat_after_seconds', 1800))
            if events:
                print('\n'.join(events), flush=True)
                return 0
            if a.once:
                return 0
            interval = a.interval if a.interval is not None else config.get('interval_seconds', 60)
            if a.max_seconds is not None and time.monotonic() - started + interval > a.max_seconds:
                return 0
            time.sleep(max(1, interval))
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        # A watch that cannot run must say so once rather than look like silence.
        print('WATCH_BROKEN ' + str(exc), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
