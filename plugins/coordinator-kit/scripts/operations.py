"""Read-only operational views. Suggestions never authorize dispatch or send messages."""
import datetime
import math

from storage import now


def timestamp(value):
    try:
        result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, TypeError, AttributeError):
        return None
    return result if result.tzinfo is not None else None


def snapshot(st):
    records = [st.get(r[0]) for r in st.con.execute('SELECT id FROM records ORDER BY created_at,id')]
    tasks = {r['id']: r for r in records if r['kind'] == 'task'}
    questions = [r for r in records if r['kind'] == 'question']
    return tasks, questions, st.summary()


def task_view(row):
    data = row['data']
    result = {key: row[key] for key in ('id', 'title', 'status')}
    result.update({key: data[key] for key in ('goal', 'priority', 'queue_pos', 'release_target', 'next_step') if data.get(key) is not None})
    return result


def queue_order(row):
    position = row['data'].get('queue_pos')
    return (position if type(position) is int and position > 0 else float('inf'), row['created_at'], row['id'])


def question_links(row):
    refs = row['data'].get('tasks', [])
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        return None
    return refs


def next_tasks(tasks, questions, state):
    # Holds may be scoped; leave interpretation to the coordinator rather than guessing scope.
    if not state['ready_for_dispatch'] or state['active_holds']:
        return []
    open_questions = [q for q in questions if q['status'] in ('queued', 'presented')]
    if any(question_links(q) is None for q in open_questions):
        return []
    asked = {ref for q in open_questions for ref in question_links(q)}
    owned = {lane['data'].get('task') for lane in state['active_lanes']}
    result = []
    for row in sorted(tasks.values(), key=queue_order):
        data = row['data']
        if row['status'] != 'pending' or data.get('user_initiated') or data.get('needs_user') or data.get('blocked_on'):
            continue
        if row['id'] in asked or row['id'] in owned or type(data.get('queue_pos')) is not int or data['queue_pos'] < 1:
            continue
        dependencies = data.get('dependencies', [])
        if not isinstance(dependencies, list) or any(not isinstance(ref, str) or ref not in tasks or tasks[ref]['status'] != 'done' for ref in dependencies):
            continue
        result.append(row)
    return result


def status_view(st, limit=3):
    if not 1 <= limit <= 20:
        raise ValueError('status limit must be between 1 and 20')
    tasks, questions, state = snapshot(st)
    open_rows = [r for r in tasks.values() if r['status'] not in ('done', 'dropped')]
    running = [r for r in open_rows if r['status'] in ('in_progress', 'verifying')]
    releases = [r for r in open_rows if r['status'] == 'awaiting_release' and not r['data'].get('user_initiated')]
    waiting = [r for r in open_rows if not r['data'].get('user_initiated') and
               (r['data'].get('needs_user') or r['status'] == 'awaiting_release')]
    presented = next((q for q in questions if q['status'] == 'presented'), None)
    return {'open_tasks': len(open_rows), 'running_count': len(running),
            'running': [task_view(r) for r in sorted(running, key=queue_order)[:limit]],
            'awaiting_release_count': len(releases),
            'awaiting_release': [task_view(r) for r in sorted(releases, key=queue_order)[:limit]],
            'waiting_on_user_count': len(waiting),
            'user_initiated_count': sum(bool(r['data'].get('user_initiated')) for r in open_rows),
            'queued_question_count': sum(q['status'] == 'queued' for q in questions),
            'question_link_review': [q['id'] for q in questions if q['status'] in ('queued', 'presented') and question_links(q) is None],
            'presented_question': None if presented is None else {
                'id': presented['id'], 'title': presented['title'],
                'options': presented['data'].get('options'), 'outbound_id': presented['data'].get('outbound_id')},
            'next_tasks': [task_view(r) for r in next_tasks(tasks, questions, state)[:limit]],
            'migration_ready': state['ready_for_dispatch'],
            'active_hold_count': len(state['active_holds']),
            'note': 'Next tasks are candidates; confirm authorization, scoped holds, live ownership and capacity.'}


def sweep(st, at=None, stale_hours=6, available_slots=None):
    current = timestamp(at if at is not None else now())
    if current is None:
        raise ValueError('sweep --now requires a timezone-aware ISO timestamp')
    if not math.isfinite(stale_hours) or stale_hours <= 0:
        raise ValueError('stale-hours must be finite and greater than zero')
    if available_slots is not None and not 0 <= available_slots <= 64:
        raise ValueError('available-slots must be between 0 and 64; omit when unknown')
    tasks, questions, state = snapshot(st)
    items = []
    if not state['ready_for_dispatch']:
        items.append({'kind': 'migration_review', 'text': 'Finish migration reconciliation before dispatch.'})
    if state['active_holds']:
        items.append({'kind': 'review_holds', 'records': [r['id'] for r in state['active_holds']],
                      'text': 'Check hold scope before dispatch; no hold is lifted by this sweep.'})
    open_questions = [q for q in questions if q['status'] in ('queued', 'presented')]
    refs = {ref for q in open_questions for ref in (question_links(q) or [])}
    settled = {}
    for question in questions:
        if question['status'] in ('answered', 'parked'):
            for ref in question_links(question) or []:
                settled.setdefault(ref, []).append(question['id'])
    queued = [q for q in questions if q['status'] == 'queued']
    for row in sorted(tasks.values(), key=queue_order):
        data = row['data']
        if row['status'] in ('done', 'dropped', 'needs_review'):
            continue
        if not data.get('user_initiated'):
            if row['id'] not in refs and row['id'] in settled and (row['status'] == 'awaiting_release' or data.get('needs_user')):
                items.append({'kind': 'reconcile_answer', 'task': row['id'], 'questions': settled[row['id']],
                              'text': 'A linked question is answered or parked; reconcile its scope and task state before asking again.'})
            elif row['status'] == 'awaiting_release' and row['id'] not in refs:
                items.append({'kind': 'queue_release_question', 'task': row['id'],
                              'release_target': data.get('release_target'),
                              'text': 'Record one scoped release question; present only when the decision slot is free.'})
            elif data.get('needs_user') and row['id'] not in refs:
                items.append({'kind': 'queue_user_question', 'task': row['id'],
                              'text': 'Record the concrete remaining user decision or action.'})
        if row['status'] in ('in_progress', 'verifying'):
            activity = [timestamp(row['updated_at'])]
            activity.extend(timestamp(r[0]) for r in st.con.execute('SELECT at FROM events WHERE record_id=?', (row['id'],)))
            latest = max((value for value in activity if value is not None), default=None)
            if latest is None or (current - latest).total_seconds() >= stale_hours * 3600:
                items.append({'kind': 'check_liveness', 'task': row['id'],
                              'last_activity': latest.isoformat() if latest else None,
                              'text': 'Inspect native status/output; elapsed silence does not authorize cancellation or restart.'})
    # A question left over after a user-controlled action was parked needs reconciliation,
    # not another automatic reminder. Neither a stale item nor this command changes the slot.
    invalid = set()
    for question in open_questions:
        linked = question_links(question)
        if linked is None or any(ref not in tasks or tasks[ref]['status'] in ('done', 'dropped') or
               tasks[ref]['data'].get('user_initiated') for ref in linked):
            invalid.add(question['id'])
            items.append({'kind': 'review_question', 'question': question['id'],
                          'text': 'Reconcile malformed links, completed/missing tasks or user-initiated scope before presenting.'})
    if not state['presented_question'] and queued:
        first = next((q for q in queued if q['id'] not in invalid), None)
        if first:
            items.append({'kind': 'present_question', 'question': first['id'],
                          'text': 'Present this queued question through the authorized channel, then save its outbound id.'})
    if available_slots:
        for row in next_tasks(tasks, questions, state)[:available_slots]:
            items.append({'kind': 'dispatch_candidate', 'task': row['id'],
                          'text': 'Check authorization and live resource ownership before claiming a lane.'})
    return {'at': current.isoformat(), 'items': items, 'read_only': True}
