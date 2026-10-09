"""Independent behavioral tests for the opt-in Telegram idle post.

Only disposable SQLite workspaces and fake clocks/API objects are used.  The
fake service tracks visible posts, so assertions concern observable behavior
and durable state rather than source text or instruction wording.
"""
from contextlib import contextmanager
import datetime as dt
import io
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
FIXTURES = REPO / '.coordinator-scratch/telegram-status-review/fixtures'
sys.path.insert(0, str(PLUGIN / 'scripts'))
import telegram_status as status
from storage import Store


class Clock:
    def __init__(self):
        self.now = dt.datetime(2026, 10, 9, 12, tzinfo=dt.timezone.utc).timestamp()

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    def iso(self, offset=0):
        return dt.datetime.fromtimestamp(self.now + offset, dt.timezone.utc).isoformat()


class Crash(BaseException):
    """A process stop outside the normal caught API-error path."""


class FakeAPI:
    bot_id = '314159'

    def __init__(self):
        self.calls = []
        self.posts = {}
        self.next_id = 100
        self.failure = None
        self.after_delivery = None
        self.observe_call = None

    def __call__(self, method, params):
        if method not in ('sendMessage', 'editMessageText', 'deleteMessage'):
            raise AssertionError('A sender must never consume the inbox')
        self.calls.append((method, dict(params)))
        if self.observe_call:
            self.observe_call(method, params)
        if self.failure:
            failure, self.failure = self.failure, None
            raise failure
        if method == 'sendMessage':
            self.next_id += 1
            self.posts[self.next_id] = dict(params)
            result = {'message_id': self.next_id}
        elif method == 'editMessageText':
            mid = params['message_id']
            if mid not in self.posts:
                raise status.ApiError('not_found')
            self.posts[mid].update(params)
            result = {'message_id': mid}
        else:
            mid = params['message_id']
            if mid not in self.posts:
                raise status.ApiError('not_found')
            del self.posts[mid]
            result = True
        if self.after_delivery:
            failure, self.after_delivery = self.after_delivery, None
            raise failure
        return result


class TelegramStatusTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / 'workspace with spaces'
        self.root.mkdir()
        self.clock = Clock()
        self.api = FakeAPI()
        self.factory_calls = []
        with self.store(create=True):
            pass
        self.restart()
        # Fail closed if any test accidentally reaches the real transport.
        self.network_guard = mock.patch('urllib.request.OpenerDirector.open',
                                        side_effect=AssertionError('Network is prohibited'))
        self.network_guard.start()

    def tearDown(self):
        self.network_guard.stop()
        self.temp.cleanup()

    @contextmanager
    def store(self, **kwargs):
        st = Store(self.root, **kwargs)
        try:
            yield st
        finally:
            st.close()

    def factory(self, config):
        self.factory_calls.append(dict(config))
        return self.api

    def restart(self):
        self.engine = status.IdleStatus(self.root, api_factory=self.factory, clock=self.clock)

    def enable(self, **values):
        return self.engine.configure({'enabled': True, 'chat_id': '271828', **values},
                                     source='fixture:authorized-user-request')

    def state(self):
        with self.store(read_only=True) as st:
            return status.state_read(st)

    def dump(self):
        with self.store(read_only=True) as st:
            return '\n'.join(st.con.iterdump())

    def task(self, key, summary=None, summary_at=None, **fields):
        data = {'title': 'Private title ' + key, 'source': 'fixture:user-request',
                'status': 'in_progress', 'acceptance': ['Outcome works'], **fields}
        if summary is not None:
            data.update(public_summary=summary,
                        summary_updated_at=summary_at or self.clock.iso())
        with self.store() as st, st.transaction():
            st.put('task', key, data)

    def lane(self, key, task, age=0):
        key = 'lane-' + key
        checkout = self.root / ('checkout-' + key)
        checkout.mkdir()
        with self.store() as st, st.transaction():
            st.put('lane', key, {'title': key, 'task': task, 'checkout': str(checkout),
                                'agent': 'fake-agent-' + key})
            st.con.execute('UPDATE records SET updated_at=? WHERE id=?',
                           (self.clock.iso(-age), key))

    def posted(self):
        self.enable()
        self.clock.advance(1800)
        self.assertEqual(self.engine.tick()['action'], 'posted')
        return next(iter(self.api.posts))

    def test_install_is_disabled_and_preview_needs_no_credentials(self):
        before = self.dump()
        preview = self.engine.preview()
        self.assertFalse(preview['enabled'])
        self.assertFalse(preview['configured'])
        self.assertEqual(self.engine.tick(), {'action': 'disabled'})
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.factory_calls, [])

    def test_missing_database_preview_and_tick_do_not_initialize_state(self):
        missing = self.root / 'not-initialized'
        engine = status.IdleStatus(missing, api_factory=self.factory, clock=self.clock)
        for operation in (engine.preview, engine.tick):
            with self.assertRaises(ValueError):
                operation()
        self.assertFalse(missing.exists())
        self.assertEqual(self.api.calls, [])

    def test_configuration_preserves_profile_and_notification_fields(self):
        with self.store() as st, st.transaction():
            st.put('profile', 'workspace', {'title': 'A project', 'owners': ['fixture-owner'],
                   'notification': {'channel': 'existing-bridge', 'quiet': True}})
        self.enable()
        with self.store(read_only=True) as st:
            profile = st.get('workspace')['data']
            source = st.con.execute("SELECT source FROM events WHERE kind='telegram_status_config'").fetchone()[0]
        self.assertEqual(profile['owners'], ['fixture-owner'])
        self.assertEqual(profile['notification']['channel'], 'existing-bridge')
        self.assertTrue(profile['notification']['quiet'])
        self.assertEqual(source, 'fixture:authorized-user-request')
        self.assertEqual(self.factory_calls, [])

    def test_rejected_configuration_is_atomic_and_private_chat_only(self):
        invalid = [{'chat_id': '-1001234'}, {'chat_id': '@public_channel'}, {'chat_id': '0'},
                   {'enabled': 'true'}, {'interval_minutes': 0}, {'refresh_minutes': True},
                   {'summary_max_age_minutes': float('nan')}, {'timezone': 'Invalid/Zone'},
                   {'token_env': 'not-an-environment-name'}, {'unknown': 'value'}]
        for values in invalid:
            with self.subTest(values=values):
                before = self.dump()
                with self.assertRaises(ValueError):
                    self.enable(**values)
                self.assertEqual(self.dump(), before)
        self.assertEqual(self.api.calls, [])

    def test_falsey_non_string_destinations_cannot_enable_publishing(self):
        for chat_id in (False, 0, [], {}):
            with self.subTest(chat_id=chat_id):
                before = self.dump()
                with self.assertRaises(ValueError):
                    self.enable(chat_id=chat_id)
                self.assertEqual(self.dump(), before)

    def test_post_at_thirty_minutes_is_silent_and_edits_same_post_after_restart(self):
        self.enable()
        self.clock.advance(1799)
        self.assertEqual(self.engine.tick()['action'], 'waiting')
        self.assertEqual(self.api.calls, [])
        self.clock.advance(1)
        self.assertEqual(self.engine.tick()['action'], 'posted')
        mid = next(iter(self.api.posts))
        sent = self.api.posts[mid]
        self.assertIs(sent['disable_notification'], True)
        self.assertEqual(sent['chat_id'], '271828')
        self.assertEqual(sent['link_preview_options'], {'is_disabled': True})
        baseline = self.state()['last_exchange_at']
        self.clock.advance(1799)
        self.restart()
        self.assertEqual(self.engine.tick()['action'], 'waiting')
        self.clock.advance(1)
        self.assertEqual(self.engine.tick()['action'], 'edited')
        self.assertEqual(list(self.api.posts), [mid])
        self.assertEqual(self.api.calls[-1][1]['message_id'], mid)
        self.assertEqual(self.state()['last_exchange_at'], baseline)

    def test_inbound_and_outbound_exchange_delete_existing_post(self):
        self.posted()
        for direction in ('inbound', 'outbound'):
            with self.subTest(direction=direction):
                self.clock.advance(1)
                self.engine.exchange(direction, 'fixture:' + direction)
                self.restart()
                self.assertEqual(self.engine.tick()['action'], 'deleted')
                self.assertFalse(self.api.posts)
                self.assertNotIn('message_id', self.state())
                self.clock.advance(1800)
                self.assertEqual(self.engine.tick()['action'], 'posted')

    def test_duplicate_and_historical_exchanges_do_not_reset_silence(self):
        self.enable()
        self.clock.advance(600)
        self.engine.exchange('inbound', 'bot:update:1', self.clock.iso())
        accepted = self.state()
        self.clock.advance(600)
        self.assertEqual(self.engine.exchange('inbound', 'bot:update:1'), {'duplicate': True})
        self.assertTrue(self.engine.exchange('inbound', 'bot:update:0', self.clock.iso(-900))['historical'])
        self.assertEqual(self.state()['last_exchange_at'], accepted['last_exchange_at'])
        self.assertEqual(self.state()['exchange_seq'], accepted['exchange_seq'])
        self.clock.advance(1200)
        self.assertEqual(self.engine.tick()['action'], 'posted')

    def test_exchange_rejects_invalid_direction_id_and_timestamp_without_writes(self):
        self.enable()
        cases = [('reaction', 'event', None), ('typing', 'event', None), ('inbound', '', None),
                 ('inbound', 'x' * 201, None), ('inbound', 'event', '2026-10-09T12:00:00'),
                 ('inbound', 'event', self.clock.iso(6)), ('outbound', 'event', 'nonsense')]
        for direction, event_id, at in cases:
            with self.subTest(direction=direction, event_id=event_id, at=at):
                before = self.dump()
                with self.assertRaises(ValueError):
                    self.engine.exchange(direction, event_id, at)
                self.assertEqual(self.dump(), before)

    def test_send_rejection_backs_off_and_real_exchange_restarts_idle_interval(self):
        self.enable()
        self.clock.advance(1800)
        self.api.failure = status.ApiError('api_rejected', retry_after=600)
        self.assertEqual(self.engine.tick()['action'], 'retry')
        self.assertNotIn('pending', self.state())
        self.clock.advance(1)
        self.assertEqual(self.engine.tick()['action'], 'backoff')
        self.assertEqual(len(self.api.calls), 1)
        self.engine.exchange('inbound', 'accepted-new-message')
        self.assertEqual(self.engine.tick()['action'], 'waiting')
        self.clock.advance(1800)
        self.assertEqual(self.engine.tick()['action'], 'posted')

    def test_edit_backoff_does_not_delay_delete_when_conversation_resumes(self):
        self.posted()
        self.clock.advance(1800)
        self.api.failure = status.ApiError('api_rejected', retry_after=600)
        self.assertEqual(self.engine.tick()['action'], 'retry')
        self.clock.advance(1)
        self.engine.exchange('outbound', 'confirmed-ordinary-message')
        self.assertEqual(self.engine.tick()['action'], 'deleted')
        self.assertFalse(self.api.posts)

    def test_unknown_send_result_survives_restart_without_duplicate_send(self):
        self.enable()
        self.clock.advance(1800)
        self.api.after_delivery = status.ApiError('transport_unknown')
        self.assertEqual(self.engine.tick()['action'], 'reconcile_send')
        observed_mid = next(iter(self.api.posts))
        self.restart()
        self.clock.advance(86400)
        self.assertEqual(self.engine.tick()['action'], 'reconcile_send')
        self.assertEqual(len(self.api.calls), 1)
        self.engine.exchange('inbound', 'conversation-resumed')
        self.assertEqual(self.engine.tick()['action'], 'reconcile_send')
        self.engine.reconcile(message_id=observed_mid, source='fixture:observed-post')
        self.assertEqual(self.engine.tick()['action'], 'deleted')
        self.assertFalse(self.api.posts)

    def test_crash_after_send_acceptance_requires_observed_reconciliation(self):
        self.enable()
        self.clock.advance(1800)
        self.api.after_delivery = Crash()
        with self.assertRaises(Crash):
            self.engine.tick()
        self.restart()
        self.assertEqual(self.engine.tick()['action'], 'reconcile_send')
        mid = next(iter(self.api.posts))
        self.engine.reconcile(message_id=mid, source='fixture:inspected-chat')
        self.assertEqual(self.engine.tick()['action'], 'waiting')
        self.assertEqual(len(self.api.calls), 1)

    def test_unknown_send_confirmed_absent_allows_one_retry(self):
        self.enable()
        self.clock.advance(1800)
        self.api.failure = status.ApiError('transport_unknown')
        self.assertEqual(self.engine.tick()['action'], 'reconcile_send')
        self.engine.reconcile(absent=True, source='fixture:confirmed-absent')
        self.assertEqual(self.engine.tick()['action'], 'posted')
        self.assertEqual(len(self.api.posts), 1)

    def test_crashed_edit_is_retried_on_same_message_after_restart(self):
        mid = self.posted()
        self.clock.advance(1800)
        self.api.after_delivery = Crash()
        with self.assertRaises(Crash):
            self.engine.tick()
        self.restart()
        self.assertEqual(self.engine.tick()['action'], 'edited')
        self.assertEqual(list(self.api.posts), [mid])
        self.assertEqual([p['message_id'] for m, p in self.api.calls if m == 'editMessageText'], [mid, mid])

    def test_crashed_delete_is_retried_and_missing_confirmation_clears_identity(self):
        self.posted()
        self.engine.exchange('inbound', 'resumed')
        self.api.after_delivery = Crash()
        with self.assertRaises(Crash):
            self.engine.tick()
        self.restart()
        self.assertEqual(self.engine.tick()['action'], 'deleted')
        self.assertNotIn('message_id', self.state())
        self.assertEqual([method for method, _ in self.api.calls],
                         ['sendMessage', 'deleteMessage', 'deleteMessage'])

    def test_cannot_delete_keeps_identity_and_blocks_replacement_until_reconciled(self):
        mid = self.posted()
        self.engine.exchange('inbound', 'resumed')
        self.api.failure = status.ApiError('cannot_delete')
        self.assertEqual(self.engine.tick()['action'], 'retry_delete')
        self.restart()
        self.clock.advance(86400)
        self.assertEqual(self.engine.tick()['action'], 'reconcile_cleanup')
        self.assertEqual(self.state()['message_id'], mid)
        self.assertEqual(list(self.api.posts), [mid])
        self.assertEqual(len(self.api.calls), 2)

    def test_transient_delete_failure_preserves_identity_and_retries(self):
        mid = self.posted()
        self.engine.exchange('inbound', 'resumed')
        self.api.failure = status.ApiError('api_rejected', retry_after=60)
        self.assertEqual(self.engine.tick()['action'], 'retry_delete')
        self.assertEqual(self.state()['message_id'], mid)
        self.clock.advance(59)
        self.assertEqual(self.engine.tick()['action'], 'backoff')
        self.clock.advance(1)
        self.assertEqual(self.engine.tick()['action'], 'deleted')
        self.assertFalse(self.api.posts)

    def test_not_modified_edit_counts_as_confirmed_refresh(self):
        mid = self.posted()
        self.clock.advance(1800)
        self.api.failure = status.ApiError('not_modified')
        self.assertEqual(self.engine.tick()['action'], 'edited')
        self.assertEqual(self.state()['updated_at'], self.clock())
        self.assertEqual(self.engine.tick()['action'], 'waiting')
        self.assertEqual(list(self.api.posts), [mid])

    def test_deleted_elsewhere_is_replaced_only_after_confirmed_missing_edit(self):
        mid = self.posted()
        del self.api.posts[mid]
        self.clock.advance(1800)
        self.assertEqual(self.engine.tick()['action'], 'missing')
        self.assertNotIn('message_id', self.state())
        self.assertEqual(self.engine.tick()['action'], 'posted')
        self.assertEqual(len(self.api.posts), 1)

    def test_rotation_deletes_old_post_before_sending_replacement(self):
        old_mid = self.posted()
        self.clock.advance(46 * 3600)
        self.assertEqual(self.engine.tick()['action'], 'posted')
        self.assertEqual([method for method, _ in self.api.calls],
                         ['sendMessage', 'deleteMessage', 'sendMessage'])
        self.assertEqual(len(self.api.posts), 1)
        self.assertNotIn(old_mid, self.api.posts)

    def test_disable_cleans_existing_post_and_refuses_destination_change_until_clean(self):
        self.posted()
        self.engine.configure({'enabled': False}, source='fixture:stop')
        before = self.dump()
        for values in ({'chat_id': '12345'}, {'token_env': 'OTHER_FAKE_BOT_ENV'}):
            with self.assertRaises(ValueError):
                self.engine.configure(values, source='fixture:change-destination')
            self.assertEqual(self.dump(), before)
        self.assertEqual(self.engine.tick()['action'], 'deleted')
        self.assertEqual(self.engine.tick()['action'], 'disabled')
        self.engine.configure({'chat_id': '12345'}, source='fixture:change-destination')
        self.assertFalse(self.api.posts)

    def test_changed_bot_identity_cannot_edit_or_delete_another_bots_post(self):
        self.posted()
        self.api.bot_id = '999999'
        self.engine.exchange('inbound', 'resumed')
        before = self.dump()
        with self.assertRaises(ValueError):
            self.engine.tick()
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(self.dump(), before)

    def test_journal_is_committed_before_api_call_without_holding_sqlite_transaction(self):
        self.enable()
        self.clock.advance(1800)

        def inspect_journal(method, _params):
            with sqlite3.connect(self.root / '.coordinator/coord.db', timeout=0.01) as con:
                state = json.loads(con.execute('SELECT value FROM meta WHERE key=?',
                                               (status.STATE_KEY,)).fetchone()[0])
                self.assertEqual(state['pending']['method'], method)
                con.execute('BEGIN IMMEDIATE')
                con.rollback()

        self.api.observe_call = inspect_journal
        self.assertEqual(self.engine.tick()['action'], 'posted')

    def test_database_is_only_authoritative_state_artifact(self):
        self.posted()
        self.engine.exchange('inbound', 'resumed')
        self.engine.tick()
        artifacts = {str(path.relative_to(self.root)) for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(artifacts, {'.coordinator/coord.db', '.coordinator/telegram-status.lock'})

    def test_render_groups_fresh_lanes_and_excludes_private_source_fields(self):
        self.enable()
        self.task('owned', 'Checking <checkout> & receipt totals.',
                  notes='private task notes', evidence=['private proof link'])
        self.lane('builder', 'owned')
        self.lane('verifier', 'owned')
        self.task('stale', 'Obsolete progress', summary_at=self.clock.iso(-6 * 3600))
        self.lane('stale-worker', 'stale')
        self.task('owner-gone', 'Must not imply alive')
        self.lane('old-worker', 'owner-gone', age=24 * 3600 + 1)
        self.task('unowned', 'No active lane')
        self.task('finished', 'Finished should not appear', status='done')
        self.lane('finished-worker', 'finished')
        before = self.dump()
        preview = self.engine.preview()
        self.assertEqual(preview['active_task_count'], 2)
        self.assertEqual(preview['missing_summary_count'], 1)
        self.assertEqual(preview['ownership_review_count'], 2)
        self.assertEqual(preview['text'].count('Checking &lt;checkout&gt; &amp; receipt totals.'), 1)
        for private in ('Private title', 'private task notes', 'private proof link', 'Obsolete progress',
                        'Must not imply alive', 'No active lane', 'Finished should not appear', str(self.root)):
            self.assertNotIn(private, preview['text'])
        self.assertEqual(self.dump(), before)

    def test_render_reports_future_or_invalid_summary_and_lane_dates_as_gaps(self):
        self.enable()
        for key, date in [('future-summary', self.clock.iso(1)), ('invalid-summary', 'yesterday')]:
            self.task(key, 'Unsupported progress ' + key, summary_at=date)
            self.lane(key, key)
        self.task('future-lane', 'Unsupported future lane')
        self.lane('future-lane', 'future-lane', age=-1)
        preview = self.engine.preview()
        self.assertEqual(preview['missing_summary_count'], 2)
        self.assertEqual(preview['ownership_review_count'], 1)
        self.assertNotIn('Unsupported', preview['text'])

    def test_render_bounds_output_and_reports_omitted_active_tasks(self):
        self.enable()
        for index in range(12):
            key = 'active-' + str(index)
            self.task(key, 'x' * 1000)
            self.lane(key, key)
        preview = self.engine.preview()
        self.assertEqual(preview['active_task_count'], 12)
        self.assertEqual(preview['text'].count('• '), 8)
        self.assertIn('4 more active tasks', preview['text'])
        self.assertLess(len(preview['text']), 4096)

    def test_migration_review_blocks_publishing(self):
        self.enable()
        self.task('legacy', status='needs_review')
        self.clock.advance(1800)
        self.assertEqual(self.engine.tick()['action'], 'state_unavailable')
        self.assertFalse(self.engine.preview()['available'])
        self.assertEqual(self.api.calls, [])

    def test_generated_event_sequences_keep_one_post_and_cleanup_after_each_exchange(self):
        self.enable()
        generator = random.Random(8675309)
        for step in range(150):
            self.clock.advance(generator.choice([0, 1, 59, 600, 1799, 1800, 3600, 86400]))
            operation = generator.choice(['tick', 'tick', 'restart', 'inbound', 'outbound'])
            if operation == 'restart':
                self.restart()
            elif operation in ('inbound', 'outbound'):
                self.engine.exchange(operation, 'generated-event-' + str(step))
            outcome = self.engine.tick()
            with self.subTest(step=step, operation=operation, outcome=outcome):
                self.assertLessEqual(len(self.api.posts), 1)
                if operation in ('inbound', 'outbound'):
                    self.assertFalse(self.api.posts)
                state = self.state()
                if self.api.posts:
                    self.assertEqual(state['message_id'], next(iter(self.api.posts)))
                    self.assertGreaterEqual(self.clock() - state['last_exchange_at'], 1800)
                self.assertNotIn('pending', state)
        self.assertTrue(all(params['chat_id'] == '271828' for _, params in self.api.calls))

    def test_cli_error_hides_arbitrary_exception_details(self):
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(status.IdleStatus, 'tick', side_effect=RuntimeError('private diagnostic marker')):
            with mock.patch('sys.stderr', err), mock.patch('sys.stdout', out):
                code = status.main(['--root', str(self.root), 'tick'])
        self.assertEqual(code, 1)
        self.assertNotIn('private diagnostic marker', err.getvalue() + out.getvalue())
        self.assertIn('RuntimeError', err.getvalue())

    def test_concurrent_ticks_serialize_and_publish_only_one_post(self):
        self.enable()
        self.clock.advance(1800)
        entered = threading.Event()
        release = threading.Event()
        results, errors = [], []

        def delayed_send(_method, _params):
            entered.set()
            if not release.wait(5):
                raise AssertionError('Fixture did not release sender')

        def tick():
            try:
                results.append(self.engine.tick()['action'])
            except BaseException as error:
                errors.append(error)

        self.api.observe_call = delayed_send
        first = threading.Thread(target=tick)
        second = threading.Thread(target=tick)
        first.start()
        try:
            self.assertTrue(entered.wait(5))
            second.start()
        finally:
            release.set()
            first.join(5)
            if second.ident is not None:
                second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(errors)
        self.assertCountEqual(results, ['posted', 'waiting'])
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(len(self.api.posts), 1)

    def test_sender_loop_reports_only_changed_outcomes_without_receiving(self):
        self.enable()
        out = io.StringIO()
        sleeps = []

        def advance_until_done(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 4:
                raise KeyboardInterrupt()
            self.clock.advance(900)

        with mock.patch.object(status, 'IdleStatus', return_value=self.engine):
            with mock.patch.object(status.time, 'sleep', side_effect=advance_until_done):
                with mock.patch('sys.stdout', out):
                    code = status.main(['--root', str(self.root), 'run', '--poll-seconds', '15'])
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)['action'] for line in out.getvalue().splitlines()],
                         ['waiting', 'posted', 'waiting'])
        self.assertEqual(sleeps, [15] * 4)
        self.assertEqual([method for method, _ in self.api.calls], ['sendMessage'])

    def test_protocol_forbids_inbox_and_unsupported_api_methods(self):
        # Bypass credential construction; these methods must fail before transport.
        api = object.__new__(status.TelegramAPI)
        for method in ('getUpdates', 'getWebhookInfo', 'sendChatAction', 'setMessageReaction'):
            with self.subTest(method=method), self.assertRaises(ValueError):
                api(method, {})


if __name__ == '__main__':
    unittest.main()
