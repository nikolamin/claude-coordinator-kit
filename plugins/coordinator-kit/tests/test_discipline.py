"""CLI regressions for the verify-cycle cap, stated commitments, sequential slots, brief contract and watch.

Run: python3 -B -m unittest discover -s plugins/coordinator-kit/tests -v
Fixtures are disposable under .coordinator-scratch/discipline-review; no model or network calls.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
CLI = PLUGIN / 'scripts/coord.py'
WATCH = PLUGIN / 'scripts/watch.py'
FIXTURES = REPO / '.coordinator-scratch/discipline-review/fixtures'


class DisciplineTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', HOME=self.temp.name)
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, data=None, success=True, actor=None, text=False):
        command = [sys.executable, str(CLI), '--root', str(self.root)] + (['--actor', actor] if actor else [])
        result = subprocess.run(command + list(args), input=json.dumps(data) if data is not None else '',
                                env=self.env, text=True, capture_output=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout if text else json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        return result.stderr

    def put(self, kind, key, **fields):
        return self.cli(kind, 'put', key, '--data', '-', data={'title': key, 'source': 'fixture:user', **fields})

    def task(self, key='T1', **fields):
        return self.put('task', key, acceptance=['Works.'], **fields)

    def escalation(self, key, cycle, task='T1', answered=True, **fields):
        self.put('question', key, type='verify_escalation', cycle=cycle, tasks=[task], **fields)
        if answered:
            self.put('question', key, status='answered', answer='3', answer_source='user:9')

    # -- verify-cycle cap -----------------------------------------------------------------------

    def test_second_failed_cycle_blocks_until_an_answered_escalation(self):
        self.task(status='verifying')
        self.assertEqual(self.cli('verify', 'start', 'T1')['cycle'], '0/2')
        first = self.cli('verify', 'fail', 'T1', '--note', 'totals wrong for empty cart', '--ref', 'verify1.md')
        self.assertEqual((first['cycle'], first['escalation_required'], first['status']), ('1/2', False, 'verifying'))
        self.put('task', 'T1', status='in_progress')
        self.cli('verify', 'start', 'T1')
        second = self.cli('verify', 'fail', 'T1', '--note', 'a different finding still counts')
        self.assertEqual((second['cycle'], second['escalation_required'], second['status']), ('2/2', True, 'blocked'))
        question = second['escalation_question']
        self.assertEqual(len(question['options']), 4)
        self.assertEqual(question['record'], {'type': 'verify_escalation', 'cycle': 2, 'tasks': ['T1']})
        self.assertIn('Verify cap reached', self.cli('verify', 'start', 'T1', success=False))
        for status in ('in_progress', 'verifying'):
            self.assertIn('Verify cap reached', self.cli('task', 'put', 'T1', '--json', json.dumps({'status': status}), success=False))
        self.assertEqual(self.cli('task', 'show', 'T1')['status'], 'blocked')
        sweep = self.cli('sweep')
        self.assertEqual([i['task'] for i in sweep['items'] if i['kind'] == 'verify_escalation'], ['T1'])
        self.assertFalse(sweep['idle_ready'])
        self.assertEqual(self.cli('status')['verify_escalations'], ['T1'])
        self.assertEqual([e['text'][:8] for e in self.cli('event', 'list', '--record', 'T1') if e['kind'] == 'verify_cycle'],
                         ['fail 2/2', 'fail 1/2'])

    def test_counter_cannot_be_reset_or_cleared_by_hand(self):
        self.task(status='verifying')
        self.cli('verify', 'fail', 'T1', '--note', 'gap one')
        self.cli('verify', 'fail', 'T1', '--note', 'gap two')
        for change in ({'failed_verify_cycles': 0}, {'verify_cleared_at': 2}, {'verify_escalation_question': 'Q1'}):
            self.assertIn('verify commands', self.cli('task', 'put', 'T1', '--json', json.dumps(change), success=False))
        self.cli('task', 'put', 'T1', '--json', json.dumps({'failed_verify_cycles': 2, 'next_step': 'ask'}))
        self.escalation('Q-open', 2, answered=False)
        self.assertIn('answered verify_escalation', self.cli('verify', 'clear', 'T1', '--question', 'Q-open', success=False))
        self.escalation('Q-old', 1)
        self.assertIn('for cycle 2', self.cli('verify', 'clear', 'T1', '--question', 'Q-old', success=False))
        self.task('T2')
        self.escalation('Q-other', 2, task='T2')
        self.cli('verify', 'clear', 'T1', '--question', 'Q-other', success=False)
        self.put('question', 'Q-plain', tasks=['T1'], status='answered', answer='yes', answer_source='user:3')
        self.cli('verify', 'clear', 'T1', '--question', 'Q-plain', success=False)
        self.assertTrue(self.cli('verify', 'status', 'T1')['escalation_required'])
        self.assertIn('Agent mode', self.cli('verify', 'fail', 'T1', '--note', 'x', actor='agent', success=False))
        self.assertEqual(self.cli('verify', 'status', 'T1', actor='agent')['cycle'], '2/2')

    def test_answered_escalation_permits_exactly_one_more_cycle(self):
        self.task(status='verifying')
        self.cli('verify', 'fail', 'T1', '--note', 'gap one')
        self.cli('verify', 'fail', 'T1', '--note', 'gap two')
        self.assertEqual([i['kind'] for i in self.cli('sweep')['items'] if i.get('task') == 'T1'], ['verify_escalation'])
        self.escalation('Q1', 2, answered=False)
        self.assertEqual([i for i in self.cli('sweep')['items'] if i['kind'] == 'verify_escalation'], [])
        self.put('question', 'Q1', status='answered', answer='3', answer_source='user:9')
        cleared = self.cli('verify', 'clear', 'T1', '--question', 'Q1')
        self.assertFalse(cleared['escalation_required'])
        self.cli('verify', 'clear', 'T1', '--question', 'Q1', success=False)
        self.put('task', 'T1', status='in_progress')
        self.cli('verify', 'start', 'T1')
        third = self.cli('verify', 'fail', 'T1', '--note', 'gap three')
        self.assertEqual((third['cycle'], third['escalation_required'], third['status']), ('3/2', True, 'blocked'))
        self.cli('verify', 'clear', 'T1', '--question', 'Q1', success=False)
        self.assertIn('Verify cap reached', self.cli('verify', 'start', 'T1', success=False))
        # Shipping as is, cutting scope or parking stay ordinary status changes.
        self.put('task', 'T1', status='dropped')

    def test_pass_for_the_task_target_is_the_stop_line(self):
        self.task(status='verifying', verification_target='staging')
        self.cli('verify', 'fail', 'T1', '--note', 'gap one')
        self.cli('verify', 'pass', 'T1', '--note', 'x', success=False)
        passed = self.cli('verify', 'pass', 'T1', '--target', 'staging', '--note', 'acceptance met on staging build')
        self.assertTrue(passed['stop_line'])
        self.assertIn('judged at release', passed['next'])
        self.assertEqual((passed['cycle'], passed['last_verdict']['result'], passed['status']), ('1/2', 'pass', 'verifying'))
        other = self.cli('verify', 'pass', 'T1', '--target', 'release', '--note', 'release checks')
        self.assertFalse(other['stop_line'])
        self.task('T2', status='verifying')
        self.assertTrue(self.cli('verify', 'pass', 'T2', '--target', 'staging', '--note', 'ok')['stop_line'])
        self.put('decision', 'D1')
        self.assertIn('task records', self.cli('verify', 'fail', 'D1', '--note', 'x', success=False))

    def test_profile_can_set_the_cap(self):
        self.put('profile', 'workspace', verify_cycle_cap=1)
        self.task(status='verifying')
        failed = self.cli('verify', 'fail', 'T1', '--note', 'gap')
        self.assertEqual((failed['cycle'], failed['escalation_required']), ('1/1', True))

    # -- commitments ----------------------------------------------------------------------------

    def test_commitment_stays_visible_until_withdrawn_in_its_channel(self):
        added = self.cli('commitment', 'add', 'C1', '--text', 'Ask before pushing when free memory is under 30 GB',
                         '--channel', 'chat', '--source', 'coordinator-msg:15:07')
        self.assertEqual((added['id'], added['channel']), ('C1', 'chat'))
        self.cli('commitment', 'add', 'C1', '--text', 'again', '--channel', 'chat', '--source', 's', success=False)
        for view in (self.cli('summary'), self.cli('status')):
            self.assertEqual([c['id'] for c in view['active_commitments']], ['C1'])
        self.assertEqual(self.cli('summary')['active_holds'], [])
        self.assertTrue(self.cli('sweep')['idle_ready'])
        self.assertEqual(len(self.cli('commitment', 'list', actor='agent')), 1)
        self.cli('commitment', 'withdraw', 'C1', '--channel', 'chat', '--source', 'm', '--reason', 'r', actor='agent', success=False)
        wrong = self.cli('commitment', 'withdraw', 'C1', '--channel', 'telegram', '--source', 'm:1', '--reason', 'changed', success=False)
        self.assertIn('channel it was stated in (chat)', wrong)
        self.assertEqual(len(self.cli('commitment', 'list')), 1)
        closed = self.cli('commitment', 'withdraw', 'C1', '--channel', 'chat', '--source', 'coordinator-msg:15:16', '--reason', 'user said proceed')
        self.assertEqual(closed, {'closed': 'C1', 'remaining': []})
        self.assertEqual(self.cli('summary')['active_commitments'], [])
        record = self.cli('decision', 'show', 'C1')
        self.assertEqual((record['status'], record['data']['closed_as']), ('superseded', 'withdrawn'))
        self.cli('commitment', 'withdraw', 'C1', '--channel', 'chat', '--source', 'm', '--reason', 'r', success=False)

    def test_commitment_can_be_fulfilled_and_ordinary_decisions_are_not_commitments(self):
        self.cli('commitment', 'add', 'C2', '--text', 'Report the count by 18:00', '--channel', 'chat', '--source', 'm:2')
        self.put('decision', 'D1')
        self.assertEqual([c['id'] for c in self.cli('commitment', 'list')], ['C2'])
        self.cli('commitment', 'fulfil', 'D1', '--evidence', 'x', success=False)
        self.cli('commitment', 'fulfil', 'C2', '--evidence', 'coordinator-msg:17:40')
        self.assertEqual(self.cli('decision', 'show', 'C2')['data']['closed_as'], 'fulfilled')

    # -- sequential slots -----------------------------------------------------------------------

    def test_slots_are_assigned_once_in_order_at_dispatch(self):
        for key in ('T1', 'T2', 'T3'):
            self.task(key)
        self.assertIn('--first', self.cli('slot', 'claim', 'migration', '--task', 'T1', success=False))
        self.assertEqual(self.cli('slot', 'claim', 'migration', '--task', 'T1', '--first', '406')['slot'], 406)
        again = self.cli('slot', 'claim', 'migration', '--task', 'T1')
        self.assertEqual((again['slot'], again['existing']), (406, True))
        self.assertEqual(self.cli('slot', 'claim', 'migration', '--task', 'T2')['slot'], 407)
        self.assertEqual(self.cli('slot', 'claim', 'migration', '--task', 'T1', '--another')['slot'], 408)
        self.assertEqual(self.cli('slot', 'claim', 'migration', '--task', 'T3', '--first', '420')['slot'], 420)
        self.assertEqual(self.cli('slot', 'claim', 'port', '--task', 'T3', '--first', '9001')['slot'], 9001)
        self.assertEqual([(c['slot'], c['task']) for c in self.cli('slot', 'list', 'migration', actor='agent')['claims']],
                         [(406, 'T1'), (407, 'T2'), (408, 'T1'), (420, 'T3')])
        self.cli('slot', 'claim', 'migration', '--task', 'T2', actor='agent', success=False)
        self.cli('slot', 'claim', 'migration', '--task', 'missing', success=False)
        self.put('task', 'T2', status='dropped')
        self.cli('slot', 'claim', 'migration', '--task', 'T2', '--another', success=False)

    # -- brief contract -------------------------------------------------------------------------

    def test_brief_contract_names_the_caps_scratch_and_wait_recipe(self):
        text = self.cli('brief-contract', '--scratch', '.coordinator-scratch/t1/', text=True)
        for needle in ('Do not delegate', '~80 tool steps', '~200k tokens', '.coordinator-scratch/t1/run.log',
                       'run_in_background', 'under 170 s', 'Never end your turn', 'checkpoint.md'):
            self.assertIn(needle, text)
        self.assertIn('~40 tool steps', self.cli('brief-contract', '--scratch', '.coordinator-scratch/x', '--steps', '40', text=True))
        self.cli('brief-contract', '--scratch', '/tmp/x', success=False)
        self.cli('brief-contract', '--scratch', '.coordinator-scratch/x', '--steps', '5000', success=False)

    # -- combined watch -------------------------------------------------------------------------

    def watch(self, *args, expect=0):
        result = subprocess.run([sys.executable, str(WATCH), '--root', str(self.root), '--once', *args],
                                env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expect, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result.stdout

    def checks(self, *checks, **settings):
        (self.root / '.coordinator/watch.json').write_text(json.dumps({'checks': list(checks), **settings}))

    def test_watch_is_silent_when_benign_and_speaks_once_when_actionable(self):
        self.assertEqual(self.watch(), '')
        flag = self.root / 'pending.txt'
        self.checks({'name': 'inbox', 'command': 'test -f pending.txt && cat pending.txt || true'},
                    {'name': 'quiet', 'command': 'true'})
        self.assertEqual(self.watch(), '')
        flag.write_text('pending=2\nsecond line\n')
        self.assertEqual(self.watch(), 'INBOX pending=2\n')
        self.assertEqual(self.watch(), '')
        flag.write_text('pending=3\n')
        self.assertEqual(self.watch(), 'INBOX pending=3\n')
        self.checks({'name': 'inbox', 'command': 'cat pending.txt'}, repeat_after_seconds=0)
        self.assertEqual(self.watch(), 'INBOX pending=3\n')
        self.assertEqual(self.watch(), 'INBOX pending=3\n')

    def test_watch_reports_overdue_lanes_once_and_broken_setups_loudly(self):
        self.task(status='in_progress')
        (self.root / 'repo').mkdir()
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
        future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        self.put('lane', 'L1', checkout='repo', task='T1', agent='builder-1', deadline=future)
        self.assertEqual(self.watch(), '')
        self.put('lane', 'L1', deadline=past)
        out = self.watch()
        self.assertTrue(out.startswith('AGENT_OVERDUE lane=L1 task=T1 agent=builder-1'), out)
        self.assertEqual(self.watch(), '')
        self.put('lane', 'L1', status='released')
        self.checks({'name': 'broken', 'command': 'echo boom >&2; exit 7'})
        self.assertEqual(self.watch(), '')
        looped = subprocess.run([sys.executable, str(WATCH), '--root', str(self.root), '--interval', '1'],
                                env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(looped.stdout, 'CHECK_BROKEN broken exit=7 boom\n')
        (self.root / '.coordinator/watch.json').write_text('[]')
        self.assertIn('WATCH_BROKEN', self.watch(expect=1))


if __name__ == '__main__':
    unittest.main()
