"""Mechanical coordinator discipline: verify-cycle cap, stated commitments, sequential slots, brief contract.

These exist as commands because the matching instructions were ignored under load. They record and
refuse; they never dispatch, send, release or approve anything.
"""
from storage import now, verify_blocked, verify_cap

ESCALATION_OPTIONS = [
    'Ship to the staging/test target as it is and file the open findings as tasks',
    'Cut scope to a named part that already passes',
    'One advice agent, then one last fix/verify cycle',
    'Park the task',
]

CONTRACT = '''Execution contract (coordinator-kit; applies to this whole task):
- Do not delegate; execute the assigned work directly. No side backlog: no task chips or spawned
  sessions; discoveries go in your final report.
- Step cap ~{steps} tool steps or ~{context}k tokens of context, whichever comes first. If you will pass it,
  stop at a safe boundary, write a checkpoint (intent, revision, dirty files, evidence, remaining
  steps) to {scratch}/checkpoint.md and report what you have; a fresh agent continues from disk.
- Logs, temp scripts, downloads and reports go under {scratch} inside the workspace; never a system
  temp or home path. Bulk output goes to a file there; return decisive lines, counts and exit codes
  only. Reads carry line ranges.
- Anything that can run longer than ~2 minutes (build, suite, CI wait, device): do not rely on one
  long foreground call, the host may move it to the background. Start it with the host's background
  launch (run_in_background in Claude Code) and let it write its own exit marker:
      <command> > {scratch}/run.log 2>&1; echo "rc=$?" >> {scratch}/run.log
  then poll with ordinary bounded calls, each under 170 s:
      for i in $(seq 1 16); do grep -q '^rc=' {scratch}/run.log && break; sleep 10; done; tail -5 {scratch}/run.log
  Repeat the poll until rc= appears. Never end your turn while a run is live and never finish with
  "waiting" or "standing by": nothing re-invokes you.
'''


def brief_contract(scratch, steps, context, task=None, lane=None, checkout=None):
    if not 10 <= steps <= 400 or not 50 <= context <= 1000:
        raise ValueError('steps must be 10-400 and context 50-1000 (thousand tokens)')
    scratch = scratch.rstrip('/')
    if '.coordinator-scratch' not in scratch.replace('\\', '/').split('/'):
        raise ValueError('scratch must be a task-owned directory under .coordinator-scratch/')
    # Marker lines the autolane hook reads to link the dispatched agent to its task and work lane.
    markers = ''.join(name + ': ' + value + '\n' for name, value in (('Task', task), ('Lane', lane), ('Checkout', checkout))
                      if value)
    if any(c.isspace() for value in (task, lane) if value for c in value):
        raise ValueError('task and lane are single tokens')
    return markers + CONTRACT.format(scratch=scratch, steps=steps, context=context)


def task(st, key):
    row = st.get(key)
    if row['kind'] != 'task':
        raise ValueError('Verify cycles are recorded on task records')
    return row


def verify_state(st, key):
    row = task(st, key)
    data, cap = row['data'], verify_cap(st)
    failed = data.get('failed_verify_cycles', 0)
    result = {'task': key, 'status': row['status'], 'failed_verify_cycles': failed, 'cap': cap,
              'cycle': str(failed) + '/' + str(cap), 'escalation_required': verify_blocked(data, cap),
              'last_verdict': data.get('last_verdict')}
    if result['escalation_required']:
        result['escalation_question'] = {
            'record': {'type': 'verify_escalation', 'cycle': failed, 'tasks': [key]},
            'title': row['title'] + ': failed verification ' + str(failed) + ' times; how to proceed?',
            'options': ESCALATION_OPTIONS,
            'default': 'No further fix agent; the task stays blocked',
            'next': 'Record this as ONE question with the record fields above and present it through question-protocol. '
                    'After the answer: `verify clear TASK --question ID` permits exactly one more cycle; '
                    'shipping, cutting scope or parking is a normal status change. No further fix or verify agent before that.'}
    return result


def verify(st, a):
    op = a.operation
    if op == 'status':
        return verify_state(st, a.task)
    row = task(st, a.task)
    data, cap = row['data'], verify_cap(st)
    failed = data.get('failed_verify_cycles', 0)
    if op == 'start':
        if verify_blocked(data, cap):
            raise ValueError('Verify cap reached (' + str(failed) + '/' + str(cap) + ') on ' + a.task +
                             ': no further fix/verify cycle without an answered escalation; run `verify status` for the question')
        return verify_state(st, a.task)
    if op in ('fail', 'pass') and not a.note.strip():
        raise ValueError('A verdict needs a note naming the evidence or the gap')
    if op == 'fail':
        change = {'failed_verify_cycles': failed + 1,
                  'last_verdict': {'result': 'fail', 'note': a.note, 'ref': a.ref, 'at': now()}}
        if verify_blocked({**data, **change}, cap):
            change.update(status='blocked', blocked_on='verify_escalation')
        st.put('task', a.task, change, managed=True)
        st.event('verify_cycle', 'fail ' + str(failed + 1) + '/' + str(cap) + ': ' + a.note, a.task, ref=a.ref)
        return verify_state(st, a.task)
    if op == 'pass':
        intended = data.get('verification_target')
        st.put('task', a.task, {'last_verdict': {'result': 'pass', 'target': a.target, 'note': a.note,
                                                 'ref': a.ref, 'at': now()}}, managed=True)
        st.event('verify_cycle', 'pass for ' + a.target + ': ' + a.note, a.task, ref=a.ref)
        result = verify_state(st, a.task)
        result['stop_line'] = intended in (None, a.target)
        result['next'] = ('PASS for the task target is the stop line: deliver to ' + a.target + ' now within recorded '
                          'authorization. Findings about a later target (production readiness) become tasks judged at release, '
                          'not another verify round.' if result['stop_line'] else
                          'This verdict covers ' + a.target + ', not the task target ' + str(intended) + '; it does not complete the gate.')
        return result
    if op == 'clear':
        question = st.get(a.question)
        answer = question['data']
        if (question['kind'] != 'question' or question['status'] != 'answered' or answer.get('type') != 'verify_escalation'
                or a.task not in (answer.get('tasks') or []) or answer.get('cycle') != failed):
            raise ValueError('Clearing needs an answered verify_escalation question linked to this task for cycle ' + str(failed))
        if not verify_blocked(data, cap):
            raise ValueError('Task is not waiting on a verify escalation')
        change = {'verify_cleared_at': failed, 'verify_escalation_question': a.question}
        if data.get('blocked_on') == 'verify_escalation':
            change['blocked_on'] = None
        st.put('task', a.task, change, managed=True)
        st.event('verify_cycle', 'escalation answered; one more cycle permitted', a.task, source=a.question)
        return verify_state(st, a.task)
    raise ValueError('Unsupported verify operation')


def commitments(st):
    rows = [st.get(r[0]) for r in st.con.execute(
        "SELECT id FROM records WHERE kind='decision' AND status='active' ORDER BY created_at,id")]
    return [r for r in rows if r['data'].get('type') == 'commitment']


def commitment_view(row):
    return {'id': row['id'], 'title': row['title'], 'channel': row['data'].get('channel'),
            'source': row['data'].get('source'), 'stated_at': row['created_at']}


def commitment(st, a):
    op = a.operation
    if op == 'list':
        return [commitment_view(r) for r in commitments(st)]
    if op == 'add':
        if st.con.execute('SELECT 1 FROM records WHERE id=?', (a.id,)).fetchone():
            raise ValueError('Commitment id already exists')
        if not a.channel.strip():
            raise ValueError('A commitment records the channel it was stated in')
        return commitment_view(st.put('decision', a.id, {'title': a.text, 'type': 'commitment', 'channel': a.channel,
                                                        'source': a.source, 'status': 'active'}))
    row = st.get(a.id)
    if row['kind'] != 'decision' or row['data'].get('type') != 'commitment' or row['status'] != 'active':
        raise ValueError('Not an active commitment')
    if op == 'withdraw':
        if a.channel != row['data'].get('channel'):
            raise ValueError('Withdraw a commitment in the channel it was stated in (' + str(row['data'].get('channel')) +
                             ') before acting, then record that message here')
        st.put('decision', a.id, {'status': 'superseded', 'closed_as': 'withdrawn', 'closed_source': a.source,
                                  'closed_reason': a.reason})
    elif op == 'fulfil':
        st.put('decision', a.id, {'status': 'superseded', 'closed_as': 'fulfilled', 'closed_source': a.evidence})
    else:
        raise ValueError('Unsupported commitment operation')
    return {'closed': a.id, 'remaining': [commitment_view(r) for r in commitments(st)]}


def slot(st, a):
    series = a.series.strip()
    if not series or ' ' in series:
        raise ValueError('Slot series is a short name without spaces')
    claims = [{'slot': int(r['ref']), 'task': r['record_id'], 'at': r['at']} for r in st.con.execute(
        "SELECT ref,record_id,at FROM events WHERE kind='slot_claim' AND source=? ORDER BY id", (series,))]
    if a.operation == 'list':
        return {'series': series, 'claims': claims}
    if task(st, a.task)['status'] in ('done', 'dropped'):
        raise ValueError('Slots are claimed for open tasks at dispatch')
    mine = [c for c in claims if c['task'] == a.task]
    if mine and not a.another:
        return dict(mine[-1], series=series, existing=True)
    if not claims and a.first is None:
        raise ValueError('First claim in a series needs --first N: the first free slot as measured by an agent, not a guess')
    if a.first is not None and a.first < 1:
        raise ValueError('--first must be a positive integer')
    value = max([c['slot'] + 1 for c in claims] + ([a.first] if a.first is not None else []))
    st.event('slot_claim', series + ' ' + str(value), a.task, ref=str(value), source=series,
             key='slot:' + series + ':' + str(value))
    return {'series': series, 'slot': value, 'task': a.task, 'existing': False}
