#!/usr/bin/env python3
"""Record every background agent dispatch as an active lane, and release it when the agent stops.

Usage (hook command, JSON on stdin): autolane.py post | stop

  post  PostToolUse on Agent: a background launch (`status: async_launched` and an agent id) gets
        a lane. The brief's marker lines link it: `Task: <task id>` (else `TASK_ID=<id>` or the
        first backticked id of an open task), `Lane: <work lane>`, `Checkout: <path>`.
        * An active lane of that task with no agent_id yet (claimed by the coordinator before
          dispatch) gets the agent id attached; its exclusive checkout claim is kept.
        * Otherwise lane `lane-agent-<id>` is created with `shared_checkout: true`, so its unique
          resource is the agent, not the checkout: agents sharing one checkout never collide.
        * Without a linked task, an auto task `agent-<id>` (in_progress, auto_lane) is created so
          the lane has the task record the store requires.
        Synchronous agents have already finished when PostToolUse fires; they are skipped.
  stop  SubagentStop: every active lane carrying that agent_id is released (manual lanes too, so a
        forgotten release is repaired) and its auto task, if any, is marked done.

Scope: the main session (hook input without agent_id for post) of an established coordinator
workspace (.coordinator/coord.db found from cwd upward). Fails open: a failure never blocks the tool
call. It is recorded in .coordinator/autolane-health.json, which `coord.py idle` turns into an
AUTOLANE-HOOK FAILING line, and shown once as a system message. The prompt is never printed or logged.
Disable per workspace with {"autolane": {"mode": "off"}} in .coordinator/guards.json, or
COORDINATOR_KIT_AUTOLANE=off.
"""
import datetime
import json
import os
from pathlib import Path
import re
import sys

from guard import find_root
from storage import Store, atomic_write, inside

AGENT_ID = re.compile(r'^[A-Za-z0-9_-]{6,64}$')
TASK_LINE = re.compile(r'^[ \t>*-]*Task:[ \t]*`?([A-Za-z0-9][A-Za-z0-9._:-]*)`?[ \t]*$', re.M)
LANE_LINE = re.compile(r'^[ \t>*-]*Lane:[ \t]*`?([A-Za-z0-9][A-Za-z0-9._-]{0,39})`?[ \t]*$', re.M)
CHECKOUT_LINE = re.compile(r'^[ \t>*-]*Checkout:[ \t]*`?([^`\n]+?)`?[ \t]*$', re.M)
TASK_MENTION = re.compile(r'\bTASK_ID=[\'"`]?([A-Za-z0-9][A-Za-z0-9._:-]*)')
BACKTICKED = re.compile(r'`([A-Za-z0-9][A-Za-z0-9._:-]{1,80})`')
CLOSED = ('done', 'dropped')
HEALTH = '.coordinator/autolane-health.json'


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def response_fields(response):
    """(status, agent id) from the Agent tool response: a dict, content blocks, or text."""
    if isinstance(response, list):
        response = ' '.join(b.get('text', '') for b in response if isinstance(b, dict) and isinstance(b.get('text'), str))
    if isinstance(response, dict):
        status = str(response.get('status') or '')
        agent_id = str(response.get('agentId') or response.get('agent_id') or '')
        if not status and response.get('isAsync') is True:
            status = 'async_launched'
        if not agent_id and response.get('content') is not None:
            inner_status, agent_id = response_fields(response['content'])
            status = status or inner_status
        return status, agent_id
    if isinstance(response, str):
        found = re.search(r'agent_?id["\'\s:=]+([A-Za-z0-9_-]{6,64})', response, re.I)
        launched = 'async_launched' if re.search(r'async_launched|running in the background|launched in the background',
                                                 response, re.I) else ''
        return launched, found.group(1) if found else ''
    return '', ''


def linked_task(st, prompt):
    open_tasks = {r[0] for r in st.con.execute("SELECT id FROM records WHERE kind='task' AND status NOT IN (?,?)", CLOSED)}
    for pattern in (TASK_LINE, TASK_MENTION, BACKTICKED):
        for found in pattern.finditer(prompt):
            if found.group(1) in open_tasks:
                return found.group(1)
    return None


def checkout_for(root, prompt):
    found = CHECKOUT_LINE.search(prompt)
    if found:
        try:
            path = inside(root, found.group(1).strip())
            if path.is_dir():
                return str(path.relative_to(root)) or '.'
        except ValueError:
            pass
    return '.'


def active_lanes(st):
    return [st.get(r[0]) for r in st.con.execute("SELECT id FROM records WHERE kind='lane' AND status='active' ORDER BY id")]


def post(st, data):
    tool_input = data.get('tool_input') if isinstance(data.get('tool_input'), dict) else {}
    status, agent_id = response_fields(data.get('tool_response'))
    if status != 'async_launched':
        return None  # Synchronous agents are done by now; failed launches have nothing to record.
    if not AGENT_ID.match(agent_id):
        raise ValueError('background launch without a recognizable agent id (response shape: ' + shape(data) + ')')
    prompt = tool_input.get('prompt') if isinstance(tool_input.get('prompt'), str) else ''
    title = ' '.join(str(tool_input.get('description') or 'agent ' + agent_id).split())[:120] or 'agent ' + agent_id
    transcript = ''
    if isinstance(data.get('transcript_path'), str) and data['transcript_path']:
        transcript = str(Path(data['transcript_path']).with_suffix('') / 'subagents' / ('agent-' + agent_id + '.jsonl'))
    fields = {'agent_id': agent_id, 'transcript': transcript, 'dispatched_at': stamp(),
              'model': str(tool_input.get('model') or 'inherit'),
              'agent_type': str(tool_input.get('subagent_type') or 'general-purpose')}
    lane_name = LANE_LINE.search(prompt)
    if lane_name:
        fields['lane'] = lane_name.group(1)
    with st.transaction():
        lanes = active_lanes(st)
        if any(lane['data'].get('agent_id') == agent_id for lane in lanes):
            return 'already recorded ' + agent_id
        task = linked_task(st, prompt)
        if task:
            claimed = [lane for lane in lanes if lane['data'].get('task') == task and not lane['data'].get('agent_id')]
            if claimed:
                lane = max(claimed, key=lambda row: (row['updated_at'], row['id']))
                st.put('lane', lane['id'], fields)
                return 'attached ' + agent_id + ' to ' + lane['id']
        else:
            task = 'agent-' + agent_id
            st.put('task', task, {'title': title, 'status': 'in_progress', 'auto_lane': True,
                                  'source': 'autolane hook: background agent dispatch ' + agent_id,
                                  'acceptance': ['The dispatched agent finishes; SubagentStop releases its lane.'],
                                  **({'lane': fields['lane']} if 'lane' in fields else {})})
        lane_id = 'lane-agent-' + agent_id
        st.put('lane', lane_id, dict(fields, title=title, status='active', task=task, auto_lane=True,
                                     shared_checkout=True, checkout=checkout_for(st.root, prompt),
                                     agent='claude ' + fields['model'] + ' (' + fields['agent_type'] + ', ' + agent_id + ')'))
        return 'registered ' + lane_id + ' task=' + task


def stop(st, data):
    agent_id = str(data.get('agent_id') or '')
    if not AGENT_ID.match(agent_id):
        found = re.search(r'agent-([A-Za-z0-9_-]{6,64})\.jsonl$', str(data.get('agent_transcript_path') or ''))
        agent_id = found.group(1) if found else ''
    if not agent_id:
        return None
    released = []
    with st.transaction():
        for lane in active_lanes(st):
            if lane['data'].get('agent_id') != agent_id:
                continue
            st.put('lane', lane['id'], {'status': 'released', 'released_at': stamp(), 'released_by': 'autolane SubagentStop'})
            released.append(lane['id'])
            task = lane['data'].get('task')
            if lane['data'].get('auto_lane') and task == 'agent-' + agent_id:
                if st.get(task)['status'] not in CLOSED:
                    st.put('task', task, {'status': 'done'})
    return 'released ' + ','.join(released) if released else None


def shape(data):
    response = data.get('tool_response')
    return ','.join(sorted(map(str, response))) if isinstance(response, dict) else type(response).__name__


def record_health(root, ok, message=''):
    """Last outcome and failing streak; returns True when this failure starts a new streak."""
    path = inside(root, HEALTH)
    try:
        health = json.loads(path.read_text(encoding='utf-8'))
        health = health if isinstance(health, dict) else {}
    except (OSError, ValueError):
        health = {}
    at = stamp()
    first = False
    if ok:
        if not health.get('failures') and health.get('last_ok_at'):
            return False  # Healthy and unchanged: avoid a write on every dispatch.
        health.update(last_ok_at=at, failing_since=None, failures=0)
    else:
        first = not health.get('failures')
        health.update(last_error_at=at, last_error=message[:200], failures=int(health.get('failures') or 0) + 1)
        health['failing_since'] = health.get('failing_since') or at
    atomic_write(path, json.dumps(health, sort_keys=True).encode())
    return first


def enabled(root):
    if os.environ.get('COORDINATOR_KIT_AUTOLANE', '').strip().lower() in ('off', '0', 'false', 'disabled'):
        return False
    path = root / '.coordinator' / 'guards.json'
    try:
        config = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except (OSError, ValueError):
        return True
    section = config.get('autolane') if isinstance(config, dict) else None
    return not (isinstance(section, dict) and section.get('mode') == 'off')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else ''
    root = None
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or mode not in ('post', 'stop'):
            return 0
        if mode == 'post' and (data.get('agent_id') or data.get('tool_name') not in (None, 'Agent', 'Task')):
            return 0  # Nested dispatches inside an agent and other tools are not coordinator lanes.
        cwd = data.get('cwd')
        root = find_root(cwd) if isinstance(cwd, str) and os.path.isdir(cwd) else None
        if root is None or not enabled(root):
            return 0
        st = Store(root)
        try:
            (post if mode == 'post' else stop)(st, data)
        finally:
            st.close()
        record_health(root, True)
    except Exception as exc:  # noqa: BLE001 -- fail open; the message never contains the prompt
        message = mode + ': ' + type(exc).__name__ + ': ' + str(exc)[:200]
        first = False
        if root is not None:
            try:
                first = record_health(root, False, message)
            except Exception:  # noqa: BLE001
                first = True
        if first:
            print(json.dumps({'systemMessage': 'coordinator-kit autolane could not record this agent lane (' + message +
                              '); `coord.py idle` reports it until a later run succeeds.'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
