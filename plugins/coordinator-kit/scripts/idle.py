"""Idle work lanes and free agent slots: what to dispatch next and how many agents may start now.

Read-only except for `block`/`unblock`, which append one event. Nothing here dispatches, sends,
releases or cancels; a pick is a candidate, not an authorization.

  work lane     = a task's `data.lane` (a short name such as `billing` or `mobile`). Tasks without
                  one form the `unassigned` pool.
  running agent = an active lane record with an `agent_id` (the bundled autolane hook records one
                  per background Agent dispatch and releases it on SubagentStop) whose recorded
                  transcript has been written within `quiet_minutes`; or an active lane without an
                  `agent_id` claimed within `claim_minutes` (dispatch is about to happen).
  agent's lane  = the lane record's `data.lane`, else the work lane of its task.
  ready task    = the same rule as sweep's dispatch candidates: pending, authorized, dependencies
                  done, not asked, not owned by an active lane, no queue conflict.
  idle lane     = a work lane with >= 1 ready task, no running agent bound to it and no
                  recorded blocker.
  pick          = per idle lane, the ready task ranked first: ordinary work before last-resort
                  work (`data.last_resort: true`, or an id starting with one of
                  `last_resort_prefixes`, default `weekly-`), then priority P0 < P1 < ... <
                  numeric < none, then queue order.
  FREE-SLOTS    = profile `capacity.max_agents` minus running agents, floored at 0, and 0 while
                  host free memory is under `capacity.min_free_memory_pct`.

Picks fill FREE-SLOTS best-first across idle lanes; the `unassigned` pool fills what is left.
"""
import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from operations import pending_tasks, prepared, queue_order, snapshot, timestamp
from storage import now

POOL = 'unassigned'
ALL = '*'
HEALTH = '.coordinator/autolane-health.json'
PREFIX = 'IDLE-LANES: '
LINE_MAX = 200
DEFAULTS = {'max_agents': 4, 'min_free_memory_pct': 15, 'quiet_minutes': 30, 'claim_minutes': 30,
            'blocker_hours': 4, 'last_resort_prefixes': ['weekly-']}
LIMITS = {'max_agents': (1, 64), 'min_free_memory_pct': (0, 100), 'quiet_minutes': (1, 1440),
          'claim_minutes': (1, 1440), 'blocker_hours': (1, 168)}
LANE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$')


def capacity_config(st, max_agents=None):
    """The workspace profile's `capacity` block with defaults; a flag overrides max_agents."""
    row = st.con.execute("SELECT data FROM records WHERE kind='profile' AND id='workspace'").fetchone()
    raw = json.loads(row['data']).get('capacity') if row else None
    raw = raw if isinstance(raw, dict) else {}
    config = json.loads(json.dumps(DEFAULTS))
    for key, (low, high) in LIMITS.items():
        value = raw.get(key)
        if type(value) is int and low <= value <= high:
            config[key] = value
    prefixes = raw.get('last_resort_prefixes')
    if isinstance(prefixes, list) and all(isinstance(p, str) and p for p in prefixes):
        config['last_resort_prefixes'] = prefixes
    config['max_agents_source'] = 'profile' if config['max_agents'] == raw.get('max_agents') else 'default'
    if max_agents is not None:
        if not LIMITS['max_agents'][0] <= max_agents <= LIMITS['max_agents'][1]:
            raise ValueError('max-agents must be between 1 and 64')
        config['max_agents'], config['max_agents_source'] = max_agents, 'flag'
    return config


def memory_free_pct(platform=None, run=subprocess.run, meminfo='/proc/meminfo'):
    """System-wide free memory in percent, or None when the host does not say."""
    platform = sys.platform if platform is None else platform
    if platform == 'darwin':
        try:
            out = run(['memory_pressure'], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        found = re.search(r'free percentage:\s*([0-9]+)%', out or '')
        return int(found.group(1)) if found else None
    try:
        text = Path(meminfo).read_text(encoding='utf-8')
    except OSError:
        return None
    values = {k: int(v) for k, v in re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)', text, re.M)}
    if values.get('MemTotal') and 'MemAvailable' in values:
        return int(values['MemAvailable'] * 100 // values['MemTotal'])
    return None


def work_lane(data):
    lane = data.get('lane') if isinstance(data, dict) else None
    lane = lane.strip() if isinstance(lane, str) else ''
    return lane if LANE_NAME.match(lane) and lane not in (POOL, ALL) else None


def priority_rank(data):
    value = data.get('priority')
    if isinstance(value, bool) or value is None:
        return (2, 0)
    if isinstance(value, (int, float)):
        return (1, value) if math.isfinite(value) else (2, 0)
    found = re.match(r'\s*[Pp]([0-9]+)\b', str(value))
    if found:
        return (0, int(found.group(1)))
    found = re.match(r'\s*([0-9]+)\s*$', str(value))
    return (1, int(found.group(1))) if found else (2, 0)


def last_resort(row, prefixes):
    return row['data'].get('last_resort') is True or any(row['id'].startswith(p) for p in prefixes)


def rank(row, prefixes):
    return (last_resort(row, prefixes), priority_rank(row['data']), queue_order(row))


def agents(state, tasks, config, current):
    """Split active lanes into running, quiet (transcript silent) and unattached (no agent id)."""
    running, quiet, unattached, seen = [], [], [], set()
    for lane in state['active_lanes']:
        data = lane['data']
        agent_id = data.get('agent_id')
        task = tasks.get(data.get('task'))
        entry = {'lane_record': lane['id'], 'task': data.get('task'), 'agent_id': agent_id,
                 'work_lane': work_lane(data) or (work_lane(task['data']) if task else None)}
        if not agent_id:
            claimed = timestamp(lane['updated_at'])
            if claimed and (current - claimed).total_seconds() < config['claim_minutes'] * 60:
                running.append(dict(entry, state='claimed'))
            else:
                unattached.append(entry)
            continue
        if agent_id in seen:
            continue
        seen.add(agent_id)
        transcript = data.get('transcript')
        if isinstance(transcript, str) and transcript:
            try:
                silent = current.timestamp() - os.path.getmtime(transcript)
            except OSError:
                silent = None  # Not found: the host may keep it elsewhere; count the agent as running.
            if silent is not None and silent >= config['quiet_minutes'] * 60:
                quiet.append(dict(entry, silent_minutes=int(silent // 60)))
                continue
        running.append(dict(entry, state='running'))
    return running, quiet, unattached


def blockers(st, current):
    """Latest `lane_blocker` event per lane that has not expired."""
    latest = {}
    for row in st.con.execute("SELECT * FROM events WHERE kind='lane_blocker' ORDER BY id"):
        latest[row['source']] = row
    active = {}
    for lane, row in latest.items():
        until = timestamp(row['ref'])
        if until is not None and until > current:
            active[lane] = {'lane': lane, 'reason': row['text'], 'until': until.isoformat(), 'since': row['at']}
    return active


def hook_health(root):
    try:
        health = json.loads((Path(root) / HEALTH).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if isinstance(health, dict) and health.get('failures') and health.get('failing_since'):
        return {key: health.get(key) for key in ('failures', 'failing_since', 'last_error', 'last_ok_at')}
    return None


def text(value):
    return ' '.join(str(value or '').replace('`', "'").split())


def clip(line):
    return line if len(line) <= LINE_MAX else line[:LINE_MAX - 1] + '…'


def pick_view(row, lane, ready, config, holds):
    data = row['data']
    action = 'review_hold' if holds else 'dispatch' if prepared(row) else 'prepare'
    return {'lane': lane, 'ready': ready, 'task': row['id'], 'title': row['title'],
            'priority': data.get('priority'), 'prepared': prepared(row),
            'last_resort': last_resort(row, config['last_resort_prefixes']), 'action': action}


def pick_line(pick):
    priority = pick['priority']
    priority = '-' if priority in (None, '') else text(priority).split(' ')[0][:8]
    suffix = {'dispatch': '', 'prepare': ' [prepare first]', 'review_hold': ' [check hold scope]'}[pick['action']]
    head = pick['lane'] + (' (' + str(pick['ready']) + ')' if pick['lane'] != POOL else '')
    return clip(PREFIX + head + ' pick ' + pick['task'] + ' ' + priority + ' ' + text(pick['title']) + suffix)


def idle_view(st, at=None, max_agents=None, mem_pct=False, reader=memory_free_pct):
    """mem_pct=False reads the host; an int or None fixes the reading (replay and tests)."""
    current = timestamp(at if at is not None else now())
    if current is None:
        raise ValueError('idle --now requires a timezone-aware ISO timestamp')
    config = capacity_config(st, max_agents)
    tasks, questions, state = snapshot(st)
    running, quiet, unattached = agents(state, tasks, config, current)
    busy = {}
    for entry in running:
        if entry['work_lane']:
            busy.setdefault(entry['work_lane'], []).append(entry['agent_id'] or entry['lane_record'])
    groups = {}
    for row in pending_tasks(tasks, questions, state):
        groups.setdefault(work_lane(row['data']) or POOL, []).append(row)
    order = lambda row: rank(row, config['last_resort_prefixes'])  # noqa: E731
    holds = bool(state['active_holds'])
    blocked = blockers(st, current)
    idle, blocked_lanes, pool = [], [], []
    for lane, rows in groups.items():
        rows.sort(key=order)
        block = blocked.get(lane) or blocked.get(ALL)
        if lane == POOL:
            if block:
                blocked_lanes.append({'lane': lane, 'ready': len(rows), 'blocker': block})
            else:
                pool = rows
            continue
        if lane in busy:
            continue
        if block:
            blocked_lanes.append({'lane': lane, 'ready': len(rows), 'blocker': block})
        else:
            idle.append((order(rows[0]), pick_view(rows[0], lane, len(rows), config, holds)))
    idle = [pick for _, pick in sorted(idle, key=lambda item: item[0])]
    memory, gated = None, False
    if idle or pool:
        memory = reader() if mem_pct is False else mem_pct
    if memory is not None and memory < config['min_free_memory_pct']:
        free, gated = 0, True
    else:
        free = max(0, config['max_agents'] - len(running))
    dispatch = idle[:free]
    dispatch += [pick_view(row, POOL, len(pool), config, holds) for row in pool[:max(0, free - len(dispatch))]]
    health = hook_health(st.root)
    lines = []
    if health:
        lines.append(clip(PREFIX + 'AUTOLANE-HOOK FAILING x' + str(health['failures']) + ' since ' +
                          str(health['failing_since']) + ' (dispatched agents are not recorded): ' +
                          text(health.get('last_error'))))
    if unattached:
        lines.append(clip(PREFIX + 'UNATTACHED-LANES ' + str(len(unattached)) + ': ' +
                          ','.join(e['lane_record'] for e in unattached) +
                          ' (active lane without agent_id; attach the agent id or release it)'))
    if dispatch:
        mem = '?' if memory is None else str(memory) + '%'
        lines.append(PREFIX + 'FREE-SLOTS: ' + str(free) + ' (agents ' + str(len(running)) + '/' +
                     str(config['max_agents']) + ', mem ' + mem + ' free)')
        lines.extend(pick_line(pick) for pick in dispatch)
    if quiet and lines:
        lines.append(clip(PREFIX + 'QUIET-AGENTS ' + str(len(quiet)) + ': ' + ','.join(
            str(e['agent_id']) + '(' + str(e['silent_minutes']) + 'm)' for e in quiet) + ' (check liveness)'))
    return {'at': current.isoformat(), 'read_only': True,
            'max_agents': config['max_agents'], 'max_agents_source': config['max_agents_source'],
            'running_agents': len(running), 'running': running, 'quiet_agents': quiet,
            'unattached_lanes': unattached, 'busy_lanes': {lane: busy[lane] for lane in sorted(busy)},
            'memory_free_pct': memory, 'min_free_memory_pct': config['min_free_memory_pct'],
            'memory_gated': gated, 'free_slots': free, 'idle_lanes': idle, 'blocked_lanes': blocked_lanes,
            'pool_ready': len(pool), 'dispatch': dispatch, 'hook_health': health, 'lines': lines,
            'action_required': bool(dispatch or health or unattached),
            'rule': 'Dispatch each pick in `dispatch` now (claim a lane, brief with Task:/Lane: lines), or record '
                    'the lane blocker with `idle block LANE --reason`; do not wait or re-arm with neither.'}


def block(st, lane, reason, hours=None, actor='coordinator', clear=False):
    if lane != ALL and lane != POOL and not LANE_NAME.match(lane or ''):
        raise ValueError('Lane must be a work lane name, unassigned, or * for all lanes')
    current = datetime.datetime.now(datetime.timezone.utc)
    if clear:
        until, reason = current, 'cleared' + (': ' + reason.strip() if reason and reason.strip() else '')
    else:
        if not reason or not reason.strip():
            raise ValueError('A lane blocker needs the concrete reason (dependency, user decision, access, hold, capacity)')
        hours = capacity_config(st)['blocker_hours'] if hours is None else hours
        if not (isinstance(hours, (int, float)) and math.isfinite(hours) and 0 < hours <= 168):
            raise ValueError('hours must be greater than 0 and at most 168')
        until = current + datetime.timedelta(hours=hours)
    until = until.isoformat(timespec='seconds')
    st.event('lane_blocker', reason.strip(), None, actor, until, lane)
    return {'lane': lane, 'until': until, 'reason': reason.strip(), 'cleared': clear}
