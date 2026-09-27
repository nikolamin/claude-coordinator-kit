"""Independent pre-wait/cycle regressions using disposable coordinator records.

The tests simulate recorded progress only. They do not dispatch native agents,
send questions externally, run model CLIs, or alter a live workspace.
"""
import itertools
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
CLI = PLUGIN / 'scripts/coord.py'
FIXTURES = REPO / '.coordinator-scratch/proactive-review/fixtures'


class ProactiveCycleTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, data=None, expected=0):
        result = subprocess.run(
            [sys.executable, str(CLI), '--root', str(self.root), *args],
            input=json.dumps(data) if data is not None else '', cwd=self.root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if expected == 1:
            self.assertTrue(result.stderr)
            return result.stderr
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def put(self, kind, key, **fields):
        return self.cli(kind, 'put', key, '--data', '-', data={
            'title': key, 'source': 'fixture:original-user-request', **fields})

    def task(self, key, **fields):
        return self.put('task', key, acceptance=['Requested behavior works.'], **fields)

    def update(self, kind, key, **fields):
        return self.cli(kind, 'put', key, '--data', '-', data=fields)

    def dump(self):
        with sqlite3.connect(self.root / '.coordinator/coord.db') as connection:
            return '\n'.join(connection.iterdump())

    def items(self, result, kind):
        return [item for item in result['items'] if item['kind'] == kind]

    def lane(self, key, task, checkout):
        (self.root / checkout).mkdir(exist_ok=True)
        return self.put('lane', key, task=task, checkout=checkout, agent='fixture-only:' + key)

    def test_idle_check_distinguishes_action_readiness_and_failure_without_writes(self):
        self.assertTrue(self.cli('sweep', '--check-idle', '--available-slots', '0')['idle_ready'])
        self.task('ready', queue_pos=1)
        before = self.dump()

        plain = self.cli('sweep')
        unknown = self.cli('sweep', '--check-idle', expected=2)
        free = self.cli('sweep', '--available-slots', '1', '--check-idle', expected=2)
        occupied = self.cli('sweep', '--available-slots', '0', '--check-idle')

        self.assertFalse(plain['idle_ready'])
        self.assertEqual(self.items(unknown, 'check_capacity')[0]['tasks'], ['ready'])
        self.assertEqual([item['task'] for item in self.items(free, 'dispatch_candidate')], ['ready'])
        self.assertTrue(occupied['idle_ready'])
        self.assertEqual(occupied['required_action_count'], 0)
        self.cli('sweep', '--available-slots', '-1', '--check-idle', expected=1)
        self.assertEqual(self.dump(), before)

    def test_answer_reconciliation_question_delivery_and_worker_fill_are_independent(self):
        self.task('answered-work', needs_user=True)
        self.put('question', 'a-answered', status='answered', tasks=['answered-work'],
                 options=['Continue', 'Wait'], answer='Continue', answer_source='fixture:reply-a')
        self.task('question-work', needs_user=True)
        self.put('question', 'b-next', tasks=['question-work'], options=['A', 'B'])
        self.task('third-question-work', needs_user=True)
        self.put('question', 'c-later', tasks=['third-question-work'], options=['A', 'B'])
        self.task('independent', queue_pos=2)
        before = self.dump()

        first = self.cli('sweep', '--available-slots', '1', '--check-idle', expected=2)

        self.assertEqual([item['task'] for item in self.items(first, 'reconcile_answer')], ['answered-work'])
        self.assertEqual([item['question'] for item in self.items(first, 'present_question')], ['b-next'])
        self.assertEqual([item['task'] for item in self.items(first, 'dispatch_candidate')], ['independent'])
        self.assertEqual(self.dump(), before)
        # Fixture bookkeeping represents completed reconciliation and real delivery.
        # No outbound question or native agent is created by this test.
        self.update('task', 'answered-work', needs_user=False, queue_pos=1)
        self.update('question', 'b-next', status='presented', outbound_id='fixture:delivered-b')

        second = self.cli('sweep', '--available-slots', '1', '--check-idle', expected=2)

        self.assertFalse(self.items(second, 'reconcile_answer'))
        self.assertFalse(self.items(second, 'present_question'))
        self.assertEqual([item['task'] for item in self.items(second, 'dispatch_candidate')], ['answered-work'])
        self.assertEqual(self.cli('question', 'show', 'c-later')['status'], 'queued')
        self.assertEqual(self.cli('question', 'show', 'a-answered')['data']['answer_source'], 'fixture:reply-a')

    def test_unranked_or_undefined_requests_require_intake_before_dispatch(self):
        for ranked, defined in itertools.product((False, True), repeat=2):
            key = 'task-' + str(ranked) + '-' + str(defined)
            self.put('task', key, queue_pos=1 if ranked else None,
                     acceptance=['Works'] if defined else [])
        before = self.dump()

        result = self.cli('sweep', '--available-slots', '4', '--check-idle', expected=2)

        self.assertEqual({item['task'] for item in self.items(result, 'prepare_task')}, {
            'task-False-False', 'task-False-True', 'task-True-False'})
        self.assertEqual([item['task'] for item in self.items(result, 'dispatch_candidate')], ['task-True-True'])
        self.assertEqual(self.dump(), before)
        self.update('task', 'task-False-False', queue_pos=2, acceptance=['Defined from the original request.'])
        prepared = self.cli('sweep', '--available-slots', '4', '--check-idle', expected=2)
        self.assertIn('task-False-False', {item['task'] for item in self.items(prepared, 'dispatch_candidate')})

    def test_unrelated_hold_requires_scope_review_instead_of_hiding_free_work(self):
        self.put('decision', 'production-hold', type='hold', scope='production releases',
                 source_text='Do not publish production until I approve it.')
        self.task('held-release', status='blocked', blocked_on='production-hold')
        self.task('authorized-docs', queue_pos=1, environment='local',
                  source_text='Update these local documents now.')
        before = self.dump()

        result = self.cli('sweep', '--available-slots', '1', '--check-idle', expected=2)

        self.assertEqual([item['task'] for item in self.items(result, 'review_dispatch_scope')], ['authorized-docs'])
        self.assertFalse(self.items(result, 'dispatch_candidate'))
        self.assertEqual(self.dump(), before)
        # Represent an independently checked, authorized local task taking the free lane.
        self.update('task', 'authorized-docs', status='in_progress')
        self.lane('docs-lane', 'authorized-docs', 'docs-checkout')

        occupied = self.cli('sweep', '--available-slots', '0', '--check-idle')

        self.assertTrue(occupied['idle_ready'])
        self.assertEqual(self.cli('decision', 'show', 'production-hold')['status'], 'active')
        self.assertEqual(self.cli('task', 'show', 'held-release')['status'], 'blocked')

    def test_first_agent_completion_releases_capacity_without_waiting_for_other_agent(self):
        self.task('first-active', status='in_progress')
        self.task('second-active', status='verifying')
        self.lane('first-lane', 'first-active', 'checkout-a')
        self.lane('second-lane', 'second-active', 'checkout-b')
        self.task('follows-first', queue_pos=1, dependencies=['first-active'])
        self.task('independent-next', queue_pos=2)
        self.assertTrue(self.cli('sweep', '--available-slots', '0', '--check-idle')['idle_ready'])
        # A confirmed completion and settled processes are represented in fixture records.
        self.update('task', 'first-active', status='done', evidence=['fixture:verified-outcome'])
        self.update('lane', 'first-lane', status='released')
        before = self.dump()

        available = self.cli('sweep', '--available-slots', '1', '--check-idle', expected=2)

        self.assertEqual([item['task'] for item in self.items(available, 'dispatch_candidate')], ['follows-first'])
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.cli('lane', 'show', 'second-lane')['status'], 'active')
        self.assertEqual(self.cli('task', 'show', 'second-active')['status'], 'verifying')
        self.update('task', 'follows-first', status='in_progress')
        self.lane('replacement-lane', 'follows-first', 'checkout-a')
        self.assertTrue(self.cli('sweep', '--available-slots', '0', '--check-idle')['idle_ready'])

    def test_idle_check_does_not_lift_stop_or_supply_release_authority(self):
        self.put('decision', 'explicit-stop', type='hold', scope='all new dispatch',
                 source_text='Stop and save. Do not start new agents.')
        self.task('pending-local', queue_pos=1)
        self.task('verified-release', status='awaiting_release', release_target='production',
                  evidence=['fixture:verified-on-test'])
        before = self.dump()

        result = self.cli('sweep', '--available-slots', '2', '--check-idle', expected=2)

        self.assertFalse(result['idle_ready'])
        self.assertEqual([item['task'] for item in self.items(result, 'queue_release_question')], ['verified-release'])
        self.assertFalse(self.items(result, 'dispatch_candidate'))
        self.assertEqual(self.cli('decision', 'show', 'explicit-stop')['status'], 'active')
        self.assertEqual(self.cli('task', 'show', 'verified-release')['status'], 'awaiting_release')
        self.assertEqual(self.cli('lane', 'list'), [])
        self.assertEqual(self.cli('question', 'list'), [])
        self.assertEqual(self.dump(), before)


if __name__ == '__main__':
    unittest.main()
