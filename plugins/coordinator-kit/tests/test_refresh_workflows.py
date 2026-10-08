"""Behavioral refresh regressions; all stores live in disposable local fixtures.

These exercise CLI/storage outcomes, not model compliance with prose policies.
They never dispatch agents, contact a bridge, or read a real project store.
"""
import hashlib
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
FIXTURES = REPO / '.coordinator-scratch/refresh-2026-10-09-review/fixtures'
NOW = '2026-10-09T12:00:00+00:00'
OLD = '2026-10-08T12:00:00+00:00'
RECENT = '2026-10-09T11:45:00+00:00'


class RefreshWorkflowTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / "workspace with spaces # and 'quotes'"
        self.root.mkdir()
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    @property
    def db(self):
        return self.root / '.coordinator/coord.db'

    def cli(self, *args, data=None, expected=0, root=None, plain=False):
        result = subprocess.run(
            [sys.executable, str(CLI), '--root', str(root or self.root), *args],
            input=json.dumps(data) if data is not None else '',
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if expected == 1:
            self.assertTrue(result.stderr)
            return result.stderr
        self.assertEqual(result.stderr, '')
        return result.stdout if plain else json.loads(result.stdout)

    def put(self, kind, key, **fields):
        return self.cli(kind, 'put', key, '--data', '-', data={
            'title': key, 'source': 'fixture:original-user-request', **fields})

    def task(self, key, **fields):
        return self.put('task', key, acceptance=['The requested outcome is observable.'], **fields)

    def lane(self, key, task, checkout):
        (self.root / checkout).mkdir(exist_ok=True)
        return self.put('lane', key, task=task, checkout=checkout, agent='fixture-only:' + key)

    def disk_state(self, root=None):
        root = root or self.root
        return {
            str(path.relative_to(root)): (
                hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode,
                path.stat().st_mtime_ns, path.stat().st_ctime_ns)
            for path in root.rglob('*') if path.is_file()
        }

    @staticmethod
    def items(result, kind):
        return [item for item in result['items'] if item['kind'] == kind]

    def test_read_commands_do_not_mutate_database_permissions_or_legacy_sources(self):
        self.task('ready', queue_pos=1)
        # A legacy source arriving after bootstrap is not a reason for a status read
        # to perform an implicit migration or retire that source.
        (self.root / 'STATE.md').write_bytes(b'# Current state\nHold production releases.\n')
        self.db.chmod(0o640)
        before = self.disk_state()
        commands = [
            ('summary',), ('status',), ('sweep', '--now', NOW, '--available-slots', '0'),
            ('task', 'show', 'ready'), ('task', 'list'), ('decision', 'list'),
            ('question', 'list'), ('lane', 'list'), ('event', 'list'),
            ('review', 'list'), ('source', 'list'), ('search', 'ready'), ('check',),
            ('--actor', 'agent', 'status'),
        ]
        for command in commands:
            with self.subTest(command=command):
                self.cli(*command)
                self.assertEqual(self.disk_state(), before)
        self.cli('render', plain=True)
        self.assertEqual(self.disk_state(), before)

    def test_read_only_connection_rejects_an_actual_database_write(self):
        self.task('unchanged', queue_pos=1)
        # Positive control: the identical write works on this fixture when a normal
        # writable connection is used, then rollback restores the existing record.
        with sqlite3.connect(self.db) as connection:
            connection.execute("DELETE FROM records WHERE id='unchanged'")
            self.assertEqual(connection.execute("SELECT count(*) FROM records WHERE id='unchanged'").fetchone()[0], 0)
            connection.rollback()
            self.assertEqual(connection.execute("SELECT count(*) FROM records WHERE id='unchanged'").fetchone()[0], 1)
        before = self.disk_state()
        code = '''
import sqlite3, sys
sys.path.insert(0, sys.argv[1])
from storage import Store
store = Store(sys.argv[2], read_only=True)
assert store.con.execute('PRAGMA query_only').fetchone()[0] == 1
if sys.argv[3] == 'off':
    store.con.execute('PRAGMA query_only=OFF')
    assert store.con.execute('PRAGMA query_only').fetchone()[0] == 0
try:
    store.con.execute("DELETE FROM records WHERE id='unchanged'")
    raise SystemExit('Unexpected write succeeded')
except sqlite3.OperationalError as error:
    assert 'readonly' in str(error).lower(), str(error)
finally:
    store.close()
'''
        for query_only in ('on', 'off'):
            with self.subTest(query_only=query_only):
                result = subprocess.run(
                    [sys.executable, '-c', code, str(PLUGIN / 'scripts'), str(self.root), query_only],
                    cwd=self.root, env=self.env, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.disk_state(), before)
        self.assertEqual(self.cli('task', 'show', 'unchanged')['status'], 'pending')

    def test_read_commands_do_not_initialize_missing_or_upgrade_unsupported_store(self):
        missing = self.root / 'missing-store'
        missing.mkdir()
        (missing / 'STATE.md').write_text('# Current state\n- [ ] Preserve this.\n')
        before = self.disk_state(missing)
        for command in ('summary', 'status', 'sweep', 'check', 'render'):
            with self.subTest(command=command, store='missing'):
                self.cli(command, root=missing, expected=1)
                self.assertEqual(self.disk_state(missing), before)
                self.assertFalse((missing / '.coordinator').exists())
        with sqlite3.connect(self.db) as connection:
            connection.execute('PRAGMA user_version=2')
        self.db.chmod(0o644)
        before = self.disk_state()
        for command in ('summary', 'status', 'sweep', 'check', 'render'):
            with self.subTest(command=command, store='unsupported'):
                self.cli(command, expected=1)
                self.assertEqual(self.disk_state(), before)

    def test_two_lanes_are_one_active_task_and_stale_running_record_is_not_redispatched(self):
        self.task('shared-goal', status='verifying', queue_pos=1,
                  public_summary='Checking the restored checkout flow.', summary_updated_at=RECENT)
        self.lane('builder-lane', 'shared-goal', 'checkout-a')
        self.lane('verifier-lane', 'shared-goal', 'checkout-b')
        self.task('orphan-running', status='in_progress', queue_pos=2)
        self.task('ready-next', queue_pos=3)
        with sqlite3.connect(self.db) as connection:
            for key in ('shared-goal', 'orphan-running'):
                connection.execute('UPDATE records SET updated_at=? WHERE id=?', (OLD, key))
                connection.execute('UPDATE events SET at=? WHERE record_id=?', (OLD, key))
            connection.execute("UPDATE events SET at=? WHERE record_id='shared-goal' AND id=(SELECT max(id) FROM events WHERE record_id='shared-goal')", (RECENT,))
        before = self.disk_state()

        status = self.cli('status')
        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '1', '--check-idle', expected=2)

        self.assertEqual(status['running_count'], 2)
        self.assertEqual(status['recorded_active_lane_count'], 2)
        self.assertEqual(status['active_task_count'], 1)
        self.assertEqual([task['id'] for task in status['active_tasks']], ['shared-goal'])
        self.assertEqual(set(status['active_tasks'][0]['lanes']), {'builder-lane', 'verifier-lane'})
        self.assertEqual(status['active_tasks'][0]['public_summary'], 'Checking the restored checkout flow.')
        self.assertEqual(status['active_tasks'][0]['summary_updated_at'], RECENT)
        self.assertEqual(status['running_without_lane'], ['orphan-running'])
        self.assertEqual([item['task'] for item in self.items(sweep, 'check_liveness')], ['orphan-running'])
        self.assertEqual([item['task'] for item in self.items(sweep, 'review_lane')], ['orphan-running'])
        self.assertEqual([item['task'] for item in self.items(sweep, 'dispatch_candidate')], ['ready-next'])
        self.assertEqual(self.disk_state(), before)

    def test_cross_chat_presented_question_keeps_ownership_and_does_not_block_independent_work(self):
        self.task('release', status='awaiting_release', release_target='production', evidence=['fixture:verified'])
        self.task('independent', queue_pos=1)
        self.put('question', 'native-question', status='presented', tasks=['release'],
                 options=['Release the measured range', 'Keep on TEST'], outbound_id='native:question-7',
                 delivery_channel='native', owner_thread='other-chat', owner_lane='release-lane')
        self.put('question', 'later-question', options=['A', 'B'], delivery_channel='authorized-bridge')
        before = self.disk_state()

        status = self.cli('status')
        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '1')

        self.assertEqual(status['presented_question'], {
            'id': 'native-question', 'title': 'native-question',
            'options': ['Release the measured range', 'Keep on TEST'],
            'outbound_id': 'native:question-7', 'delivery_channel': 'native',
            'owner_thread': 'other-chat', 'owner_lane': 'release-lane'})
        self.assertEqual(status['queued_question_count'], 1)
        self.assertFalse(self.items(sweep, 'present_question'))
        self.assertFalse(self.items(sweep, 'queue_release_question'))
        self.assertEqual([item['task'] for item in self.items(sweep, 'dispatch_candidate')], ['independent'])
        self.assertEqual(self.disk_state(), before)

    def test_queued_question_delivery_retains_channel_and_thread_without_marking_presented(self):
        self.task('needs-choice', needs_user=True)
        self.put('question', 'queued-native', tasks=['needs-choice'], options=['A', 'B'],
                 delivery_channel='native', owner_thread='assigned-chat', owner_lane='assigned-lane')
        before = self.disk_state()

        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '0')
        delivery = self.items(sweep, 'present_question')[0]['delivery']

        self.assertEqual(delivery['delivery_channel'], 'native')
        self.assertEqual(delivery['owner_thread'], 'assigned-chat')
        self.assertEqual(delivery['owner_lane'], 'assigned-lane')
        self.assertEqual(self.cli('question', 'show', 'queued-native')['status'], 'queued')
        self.assertIsNone(self.cli('status')['presented_question'])
        self.assertEqual(self.disk_state(), before)

    def test_sweep_flags_queue_conflicts_and_closed_ownership_without_repairing_or_restarting(self):
        self.task('first', queue_pos=4)
        self.task('second', queue_pos=4)
        self.task('finished', status='done', queue_pos=1)
        self.task('abandoned', status='dropped', queue_pos=2)
        self.lane('unsettled-lane', 'finished', 'checkout-unsettled')
        before = self.disk_state()

        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '0', '--check-idle', expected=2)

        self.assertEqual([(item['queue_pos'], item['tasks']) for item in self.items(sweep, 'queue_conflict')], [(4, ['first', 'second'])])
        self.assertEqual({item['task'] for item in self.items(sweep, 'clear_closed_queue')}, {'finished', 'abandoned'})
        self.assertEqual([(item['lane'], item['task']) for item in self.items(sweep, 'review_lane')], [('unsettled-lane', 'finished')])
        self.assertFalse(sweep['idle_ready'])
        self.assertEqual(self.cli('status')['active_tasks'], [])
        self.assertEqual(self.cli('lane', 'show', 'unsettled-lane')['status'], 'active')
        self.assertEqual(self.disk_state(), before)

    def test_conflicting_queue_positions_require_reconciliation_before_dispatch(self):
        self.task('a-normal', queue_pos=1, priority='normal')
        self.task('z-urgent', queue_pos=1, priority='urgent')
        self.task('independent', queue_pos=2)
        before = self.disk_state()

        status = self.cli('status')
        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '1')

        self.assertEqual([task['id'] for task in status['next_tasks']], ['independent'])
        self.assertEqual([item['task'] for item in self.items(sweep, 'dispatch_candidate')], ['independent'])
        self.assertEqual(self.items(sweep, 'queue_conflict')[0]['tasks'], ['a-normal', 'z-urgent'])
        self.assertEqual(self.disk_state(), before)
        # Explicit coordinator reconciliation, not an implicit priority tie-break,
        # determines the next dispatch order.
        for key, position in [('z-urgent', 1), ('a-normal', 2), ('independent', 3)]:
            self.cli('task', 'put', key, '--data', '-', data={'queue_pos': position})
        reconciled = self.cli('sweep', '--now', NOW, '--available-slots', '1')
        self.assertFalse(self.items(reconciled, 'queue_conflict'))
        self.assertEqual([item['task'] for item in self.items(reconciled, 'dispatch_candidate')], ['z-urgent'])
        self.assertEqual([task['id'] for task in self.cli('status')['next_tasks']], ['z-urgent', 'a-normal', 'independent'])


if __name__ == '__main__':
    unittest.main()
