"""Independent CLI regressions for queue views and follow-up suggestions.

All fixtures are disposable and remain under .coordinator-scratch/queue-review.
The views must preserve records, authority and legacy data; no model/network calls.
"""
import json
import itertools
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
FIXTURES = REPO / '.coordinator-scratch/queue-review/fixtures'
NOW = '2026-09-27T12:00:00+00:00'
OLD = '2026-09-26T12:00:00+00:00'
RECENT = '2026-09-27T11:45:00+00:00'


class OperationalViewsTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / 'workspace with spaces'
        self.root.mkdir()
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    @property
    def db(self):
        return self.root / '.coordinator/coord.db'

    def cli(self, *args, data=None, success=True):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run(
            [sys.executable, str(CLI), '--root', str(self.root), *args],
            input=json.dumps(data) if data is not None else '', cwd=self.root,
            env=env, text=True, capture_output=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        return result.stderr

    def put(self, kind, key, **fields):
        payload = {'title': key, 'source': 'fixture:user-request', **fields}
        return self.cli(kind, 'put', key, '--data', '-', data=payload)

    def task(self, key, **fields):
        return self.put('task', key, acceptance=['The requested outcome works.'], **fields)

    def dump(self):
        with sqlite3.connect(self.db) as connection:
            return '\n'.join(connection.iterdump())

    def age_task(self, key):
        # Replay real timestamps without sleeping or rewriting implementation clocks.
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE records SET updated_at=? WHERE id=?', (OLD, key))
            connection.execute('UPDATE events SET at=? WHERE record_id=?', (OLD, key))

    def kinds(self, result, kind):
        return [item for item in result['items'] if item['kind'] == kind]

    def test_mixed_queue_views_preserve_authority_and_records(self):
        self.task('building', status='in_progress', queue_pos=1)
        self.task('release', status='awaiting_release', queue_pos=2,
                  release_target='production', evidence=['test:revision-a'])
        self.task('owner-action', status='awaiting_release', queue_pos=3,
                  release_target='production', evidence=['test:revision-b'], user_initiated=True)
        self.task('needs-input', queue_pos=4, needs_user=True)
        self.task('verifying', status='verifying', queue_pos=5)
        self.task('new-request', queue_pos=8, priority='normal')
        self.task('test-only', status='on_test', evidence=['verified:test'])
        self.put('question', 'current-decision', status='presented', tasks=['needs-input'],
                 options=['Use option A', 'Use option B'], outbound_id='fixture:message-1')
        for key in ('building', 'verifying'):
            self.age_task(key)
        # The verifier is alive despite its task status not having changed recently.
        self.cli('--actor', 'agent', 'event', 'add', 'Acceptance check running',
                 '--record', 'verifying', '--kind', 'progress')
        with sqlite3.connect(self.db) as connection:
            connection.execute('UPDATE events SET at=? WHERE id=(SELECT max(id) FROM events)', (RECENT,))
        before = self.dump()

        status = self.cli('status')
        sweep = self.cli('sweep', '--now', NOW, '--available-slots', '2')

        self.assertEqual(status['running_count'], 2)
        self.assertEqual({r['id'] for r in status['running']}, {'building', 'verifying'})
        self.assertEqual(status['awaiting_release_count'], 1)
        self.assertEqual(status['waiting_on_user_count'], 2)
        self.assertEqual(status['user_initiated_count'], 1)
        self.assertEqual(status['presented_question']['id'], 'current-decision')
        self.assertEqual([r['id'] for r in status['next_tasks']], ['new-request'])
        self.assertEqual([r['task'] for r in self.kinds(sweep, 'queue_release_question')], ['release'])
        self.assertEqual([r['task'] for r in self.kinds(sweep, 'check_liveness')], ['building'])
        self.assertEqual([r['task'] for r in self.kinds(sweep, 'dispatch_candidate')], ['new-request'])
        self.assertFalse(self.kinds(sweep, 'present_question'))
        self.assertTrue(sweep['read_only'])
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.cli('task', 'show', 'test-only')['status'], 'on_test')

    def test_dispatch_candidates_need_capacity_order_and_finished_dependencies(self):
        self.task('finished', status='done')
        self.task('later', queue_pos=9)
        self.task('ready', queue_pos=4, dependencies=['finished'])
        self.task('dependent', queue_pos=2, dependencies=['later'])
        self.task('unknown-dependency', queue_pos=1, dependencies=['missing'])
        self.task('unranked')
        self.task('owner-starts', queue_pos=3, user_initiated=True)
        self.task('free-text-blocked', queue_pos=5, blocked_on='Need supplier response')
        self.task('owned', queue_pos=6)
        self.put('lane', 'writer', checkout=str(self.root), task='owned', agent='fixture-agent')
        self.task('question-blocked', queue_pos=7)
        self.put('question', 'approval', tasks=['question-blocked'])

        self.assertEqual([r['id'] for r in self.cli('status')['next_tasks']], ['ready', 'later'])
        self.assertFalse(self.kinds(self.cli('sweep', '--now', NOW), 'dispatch_candidate'))
        self.assertFalse(self.kinds(self.cli('sweep', '--now', NOW, '--available-slots', '0'), 'dispatch_candidate'))
        result = self.cli('sweep', '--now', NOW, '--available-slots', '1')
        self.assertEqual([r['task'] for r in self.kinds(result, 'dispatch_candidate')], ['ready'])

    def test_generated_dispatch_eligibility_requires_every_gate(self):
        self.task('finished', status='done')
        self.task('unfinished')
        expected = []
        for index, combination in enumerate(itertools.product(
                ('pending', 'in_progress'), (False, True), (False, True),
                (False, True), (False, True), (False, True))):
            status, user_initiated, needs_user, blocked, ranked, dependency_done = combination
            key = 'generated-' + str(index)
            self.task(key, status=status, user_initiated=user_initiated, needs_user=needs_user,
                      blocked_on='External prerequisite' if blocked else None,
                      queue_pos=index + 1 if ranked else None,
                      dependencies=['finished' if dependency_done else 'unfinished'])
            if status == 'pending' and not (user_initiated or needs_user or blocked) and ranked and dependency_done:
                expected.append(key)

        result = self.cli('sweep', '--now', NOW, '--available-slots', '64')

        self.assertEqual([r['task'] for r in self.kinds(result, 'dispatch_candidate')], expected)
        self.assertEqual([r['id'] for r in self.cli('status', '--limit', '20')['next_tasks']], expected)

    def test_answer_does_not_implicitly_present_next_question(self):
        self.put('question', 'a-current', status='presented', options=['Proceed', 'Wait'], outbound_id='m1')
        self.put('question', 'b-next', options=['Option A', 'Option B'])
        self.cli('question', 'put', 'a-current', '--data', '-', data={
            'status': 'answered', 'answer': 'Wait', 'answer_source': 'fixture:reply-to-m1'})
        before = self.dump()

        result = self.cli('sweep', '--now', NOW)

        self.assertEqual([r['question'] for r in self.kinds(result, 'present_question')], ['b-next'])
        self.assertIsNone(self.cli('status')['presented_question'])
        self.assertEqual(self.dump(), before)

    def test_outdated_first_question_does_not_hide_next_valid_question(self):
        self.task('finished', status='done')
        self.task('ready-release', status='awaiting_release', release_target='production', evidence=['verified'])
        self.put('question', 'a-outdated', tasks=['finished'], options=['Release', 'Wait'])
        self.put('question', 'b-valid', tasks=['ready-release'], options=['Release', 'Wait'])
        before = self.dump()

        result = self.cli('sweep', '--now', NOW)

        self.assertEqual([r['question'] for r in self.kinds(result, 'review_question')], ['a-outdated'])
        self.assertEqual([r['question'] for r in self.kinds(result, 'present_question')], ['b-valid'])
        self.assertEqual(self.dump(), before)

    def test_user_initiated_scope_reconciles_old_question_without_reminder(self):
        self.task('owner-release', status='awaiting_release', release_target='production',
                  evidence=['verified'], user_initiated=True)
        self.put('question', 'old-question', tasks=['owner-release'], options=['Release', 'Wait'])
        before = self.dump()

        result = self.cli('sweep', '--now', NOW, '--available-slots', '1')

        self.assertEqual([r['question'] for r in self.kinds(result, 'review_question')], ['old-question'])
        for kind in ('queue_release_question', 'queue_user_question', 'present_question', 'dispatch_candidate'):
            self.assertFalse(self.kinds(result, kind))
        self.assertEqual(self.cli('status')['waiting_on_user_count'], 0)
        self.assertEqual(self.dump(), before)

    def test_answered_and_parked_questions_are_reconciled_before_reasking(self):
        expected = {}
        for terminal, release in itertools.product(('answered', 'parked'), (False, True)):
            key = terminal + ('-release' if release else '-input')
            if release:
                self.task(key, status='awaiting_release', release_target='production', evidence=['verified'])
            else:
                self.task(key, needs_user=True)
            question = 'question-' + key
            fields = {'tasks': [key], 'status': terminal, 'options': ['Proceed', 'Wait']}
            if terminal == 'answered':
                fields.update(answer='Wait', answer_source='fixture:reply-to-' + question)
            self.put('question', question, **fields)
            expected[key] = [question]
        before = self.dump()

        result = self.cli('sweep', '--now', NOW)

        self.assertEqual({row['task']: row['questions'] for row in self.kinds(result, 'reconcile_answer')}, expected)
        self.assertFalse(self.kinds(result, 'queue_release_question'))
        self.assertFalse(self.kinds(result, 'queue_user_question'))
        self.assertFalse(self.kinds(result, 'present_question'))
        self.assertEqual(self.dump(), before)

    def test_hold_and_legacy_review_remain_in_force_after_views(self):
        original = b'# Current state\r\nHold production release until owner approval.\r\n'
        (self.root / 'STATE.md').write_bytes(original)
        self.cli('ensure', '--init')
        self.task('new-request', queue_pos=1)
        self.put('decision', 'release-hold', type='hold', scope='production',
                 source_text='Hold production release until owner approval.')
        before = self.dump()

        status = self.cli('status')
        result = self.cli('sweep', '--now', NOW, '--available-slots', '2')

        self.assertFalse(status['migration_ready'])
        self.assertEqual(status['active_hold_count'], 1)
        self.assertEqual(status['next_tasks'], [])
        self.assertTrue(self.kinds(result, 'migration_review'))
        self.assertEqual(self.kinds(result, 'review_holds')[0]['records'], ['release-hold'])
        self.assertFalse(self.kinds(result, 'dispatch_candidate'))
        self.assertEqual(self.dump(), before)
        with sqlite3.connect(self.db) as connection:
            stored = connection.execute('SELECT content,archive_path FROM sources WHERE path=?', ('STATE.md',)).fetchone()
        self.assertEqual(stored[0], original)
        self.assertEqual((self.root / stored[1]).read_bytes(), original)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_schema_one_old_nullable_question_links_are_tolerated(self):
        # Prior releases accepted arbitrary extension fields including tasks:null.
        # Insert the historical payload directly to avoid the new input validator.
        self.task('old-on-test', status='on_test')
        self.task('pending-work', queue_pos=1)
        old_question = {'title': 'Legacy question', 'source': 'old:request',
                        'status': 'queued', 'tasks': None, 'options': ['Proceed', 'Wait']}
        with sqlite3.connect(self.db) as connection:
            connection.execute('INSERT INTO records(id,kind,title,status,data,version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                               ('legacy-question', 'question', old_question['title'], 'queued', json.dumps(old_question), 1, OLD, OLD))
            connection.execute("UPDATE meta SET value='0.6.1' WHERE key='plugin_version'")
        self.assertEqual(self.cli('summary')['schema_version'], 1)
        for malformed in (None, 'pending-work', {'task': 'pending-work'}, [None]):
            with self.subTest(old_links=malformed):
                old_question['tasks'] = malformed
                with sqlite3.connect(self.db) as connection:
                    connection.execute('UPDATE records SET data=? WHERE id=?',
                                       (json.dumps(old_question), 'legacy-question'))
                before = self.dump()
                status = self.cli('status')
                result = self.cli('sweep', '--now', NOW, '--available-slots', '2')
                self.assertEqual(status['next_tasks'], [])
                self.assertEqual(status['question_link_review'], ['legacy-question'])
                self.assertEqual([r['question'] for r in self.kinds(result, 'review_question')], ['legacy-question'])
                self.assertFalse(self.kinds(result, 'present_question'))
                self.assertFalse(self.kinds(result, 'dispatch_candidate'))
                self.assertEqual(self.dump(), before)
        self.assertEqual(self.cli('task', 'show', 'old-on-test')['status'], 'on_test')

    def test_new_fields_require_explicit_valid_release_and_queue_data(self):
        for fields in ({'queue_pos': True}, {'queue_pos': 0}, {'queue_pos': 1.5},
                       {'needs_user': 'yes'}, {'user_initiated': 'false'},
                       {'status': 'awaiting_release', 'release_target': 'production'},
                       {'status': 'awaiting_release', 'evidence': ['verified']}):
            with self.subTest(fields=fields):
                self.cli('task', 'put', 'invalid', '--data', '-', success=False, data={
                    'title': 'Invalid input', 'source': 'fixture', 'acceptance': ['Works'], **fields})
        self.assertEqual(self.cli('task', 'list'), [])
        for args in (('status', '--limit', '0'), ('sweep', '--stale-hours', 'nan'),
                     ('sweep', '--stale-hours', '-1'), ('sweep', '--available-slots', '65'),
                     ('sweep', '--now', '2026-09-27T12:00:00')):
            with self.subTest(args=args):
                self.cli(*args, success=False)


if __name__ == '__main__':
    unittest.main()
