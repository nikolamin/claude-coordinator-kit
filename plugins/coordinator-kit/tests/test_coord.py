"""Offline integration tests for the bundled coordinator store and first-run migration.

Run: python3 -B -m unittest discover -s plugins/coordinator-kit/tests -v
All disposable workspaces live under .coordinator-scratch/db-review/fixtures.
No model, live repository state, external service, or third-party module is used.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
SCRIPTS = PLUGIN / 'scripts'
CLI = SCRIPTS / 'coord.py'
HOOK = SCRIPTS / 'session_start.py'
FIXTURES = REPO / '.coordinator-scratch/db-review/fixtures'
sys.dont_write_bytecode = True
SUBPROCESS_ENV = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
sys.path.insert(0, str(SCRIPTS))
migrate = importlib.import_module('migrate')
storage = importlib.import_module('storage')


class CoordinatorIntegrationTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, content, root=None):
        path = (root or self.root) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return path

    def cli(self, *args, root=None, actor=None, data=None, ok=True):
        command = [sys.executable, str(CLI), '--root', str(root or self.root)]
        if actor:
            command += ['--actor', actor]
        result = subprocess.run(command + list(args), input=data, text=True,
                                capture_output=True, timeout=30, env=SUBPROCESS_ENV)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def hook(self, root=None, **fields):
        result = subprocess.run([sys.executable, str(HOOK)], text=True,
                                input=json.dumps({'cwd': str(root or self.root), **fields}),
                                capture_output=True, timeout=30, env=SUBPROCESS_ENV)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def init(self):
        return self.cli('ensure', '--init')

    def sql(self, query, args=()):
        with sqlite3.connect(self.root / '.coordinator/coord.db') as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute(query, args)]

    def put(self, kind, key, data, **kwargs):
        return self.cli(kind, 'put', key, '--json', json.dumps(data), **kwargs)

    def task(self, key='T1', **fields):
        return self.put('task', key, {'title': 'Ship requested change', 'source': 'user:1', **fields})

    def legacy_db(self):
        path = self.root / 'docs/coordination/coord.db'
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as con:
            con.executescript('''
                CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT,status TEXT,notes TEXT);
                CREATE TABLE decisions(id TEXT PRIMARY KEY,text TEXT,status TEXT);
                CREATE TABLE questions(id TEXT PRIMARY KEY,title TEXT,answer TEXT);
                CREATE TABLE guidelines(id TEXT PRIMARY KEY,rule TEXT);
                CREATE TABLE custom_ledger(id INTEGER,payload BLOB);
                INSERT INTO tasks VALUES ('T9','Preserve original task','done','Multiline\nnotes');
                INSERT INTO decisions VALUES ('D2','Do not deploy','active');
                INSERT INTO questions VALUES ('Q1','Pick a date','No answer yet');
                INSERT INTO guidelines VALUES ('G1','Keep the source');
                INSERT INTO custom_ledger VALUES (1,X'0001FF');
            ''')
        return path

    def test_fresh_init_and_repeat_are_idempotent(self):
        self.assertFalse(self.cli('ensure')['detected'])
        self.assertFalse((self.root / '.coordinator').exists())
        first = self.init()
        self.assertTrue(first['detected'])
        self.assertTrue(first['ready_for_dispatch'])
        self.assertEqual(first['imported_sources'], 0)
        self.task()
        second = self.cli('ensure')
        self.assertEqual(second['imported_sources'], 0)
        self.assertEqual(self.cli('task', 'show', 'T1')['version'], 1)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_markdown_preserves_all_bytes_prose_duplicate_headings_and_holds(self):
        raw = (b'\xef\xbb\xbfUnheaded note: never publish without owner approval.\r\n'
               b'<!-- Keep this provenance comment -->\r\n# Active\r\n'
               b'Use the legacy branch and preserve all unstructured details.\r\n'
               b'## Duplicate\r\nFirst requirement.\r\n## Duplicate\r\n'
               b'Second requirement, distinct despite matching heading.\r\n'
               b'```markdown\r\n# A heading in a code sample\r\n```\r\nTrailing text.')
        path = self.write('docs/coordination/STATE.md', raw)
        self.write('docs/coordination/DECISIONS.md', '# Hold\nDo not deploy until explicitly approved.\n')
        result = self.cli('ensure')
        self.assertFalse(result['ready_for_dispatch'])
        self.assertEqual(result['imported_sources'], 2)
        row = self.sql("SELECT * FROM sources WHERE path='docs/coordination/STATE.md'")[0]
        self.assertEqual(row['content'], raw)
        self.assertEqual((self.root / row['archive_path']).read_bytes(), raw)
        parts = self.sql('SELECT heading,body FROM sections WHERE source_id=? ORDER BY line', (row['id'],))
        self.assertEqual(''.join(part['body'] for part in parts), raw.decode('utf-8-sig'))
        self.assertEqual(sum(part['heading'] == 'Duplicate' for part in parts), 2)
        self.assertEqual(path.read_bytes(), migrate.pointer(row['id']))
        self.assertFalse(self.cli('decision', 'list'))
        counts = {table: len(self.sql('SELECT * FROM ' + table))
                  for table in ('sources', 'sections', 'events', 'migrations')}
        self.assertEqual(self.cli('ensure')['imported_sources'], 0)
        self.assertEqual(counts, {table: len(self.sql('SELECT * FROM ' + table)) for table in counts})
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_plan_checkboxes_do_not_infer_completed_or_approved_work(self):
        self.write('CLAUDE.md', 'Use coordinator-kit.')
        self.write('docs/plan.md', '# Plan\n- [x] Claimed finished\n- [ ] Needs implementation\n')
        self.cli('ensure')
        tasks = self.cli('task', 'list')
        self.assertEqual(len(tasks), 2)
        self.assertEqual({task['status'] for task in tasks}, {'needs_review'})
        self.assertEqual({task['data']['legacy_checked'] for task in tasks}, {True, False})
        self.assertFalse(self.cli('summary')['ready_for_dispatch'])

    def test_all_builtin_companions_and_custom_sources_are_retired(self):
        expected = {}
        for index, name in enumerate(migrate.NAMES):
            expected['docs/coordination/' + name] = f'# Companion {index}\nKeep {name}.\n'.encode()
        expected['docs/decisions/0001-preserve.md'] = b'# Preserve history\nRecorded decision.\n'
        expected['docs/coordination/state-archive/2025.md'] = b'# Old state\nAn old task.\n'
        expected['custom/extra.md'] = b'# Custom source\nKeep me too.\n'
        for path, body in expected.items():
            self.write(path, body)
        self.write('.coordinator/migration.json', json.dumps({'sources': ['custom/extra.md']}))
        self.assertEqual(self.cli('ensure')['imported_sources'], len(expected))
        rows = self.sql('SELECT path,content,id FROM sources')
        self.assertEqual({row['path']: row['content'] for row in rows}, expected)
        for row in rows:
            self.assertEqual((self.root / row['path']).read_bytes(), migrate.pointer(row['id']))

    def test_failed_pointer_write_retries_without_duplicate_import(self):
        source = self.write('docs/coordination/STATE.md', '# State\nKeep this requirement.\n')
        original = source.read_bytes()
        real_link = migrate.os.link
        injected = []

        def fail_pointer(origin, destination, *args, **kwargs):
            if Path(destination) == source:
                injected.append(True)
                raise OSError('simulated permission error during retirement')
            return real_link(origin, destination, *args, **kwargs)

        with mock.patch.object(migrate.os, 'link', side_effect=fail_pointer):
            with self.assertRaisesRegex(OSError, 'simulated permission'):
                migrate.ensure(self.root)
        self.assertTrue(injected, 'Retirement publication failure was not injected')
        self.assertEqual(self.sql('SELECT content FROM sources')[0]['content'], original)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 1)
        self.assertEqual(self.cli('summary')['unretired_sources'], 1)
        retried = self.cli('ensure')
        self.assertEqual(retried['imported_sources'], 0)
        self.assertEqual(retried['unretired_sources'], 0)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 1)

    def test_interruption_after_pointer_replacement_recovers(self):
        source = self.write('docs/coordination/STATE.md', '# State\nOriginal body.\n')
        real_link = migrate.os.link
        injected = []

        def interrupt_after_pointer(origin, destination, *args, **kwargs):
            real_link(origin, destination, *args, **kwargs)
            if Path(destination) == source:
                injected.append(True)
                raise KeyboardInterrupt('simulated process interruption')

        with mock.patch.object(migrate.os, 'link', side_effect=interrupt_after_pointer):
            with self.assertRaises(KeyboardInterrupt):
                migrate.ensure(self.root)
        self.assertTrue(injected, 'Interruption after pointer publication was not injected')
        self.assertEqual(self.cli('summary')['unretired_sources'], 1)
        self.assertTrue(source.read_text().startswith(migrate.MARKER))
        self.assertEqual(self.cli('ensure')['unretired_sources'], 0)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 1)
        self.assertEqual(self.sql('SELECT state FROM migrations'), [{'state': 'complete'}])

    def test_concurrent_source_revision_is_preserved_on_retry(self):
        original = b'# State\nFirst version.\n'
        revised = b'# State\nA concurrent edit introducing a hold.\n'
        source = self.write('docs/coordination/STATE.md', original)
        real_retire = migrate.retire

        def edit_before_retire(store):
            source.write_bytes(revised)
            return real_retire(store)

        with mock.patch.object(migrate, 'retire', side_effect=edit_before_retire):
            with self.assertRaisesRegex(ValueError, 'changed during migration'):
                migrate.ensure(self.root)
        self.assertEqual(source.read_bytes(), revised)
        result = self.cli('ensure')
        self.assertEqual(result['imported_sources'], 1)
        self.assertEqual(result['unretired_sources'], 0)
        self.assertEqual({row['content'] for row in self.sql('SELECT content FROM sources')}, {original, revised})
        self.assertTrue(all(row['state'] == 'complete' for row in self.sql('SELECT state FROM migrations')))
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_source_change_immediately_before_pointer_commit_is_not_lost(self):
        original = b'# State\nOriginal version.\n'
        revised = b'# State\nConcurrent final hold.\n'
        source = self.write('docs/coordination/STATE.md', original)
        real_replace = migrate.os.replace
        injected = []

        def edit_at_cutover(origin, destination, *args, **kwargs):
            if Path(origin) == source:
                injected.append(True)
                source.write_bytes(revised)
            return real_replace(origin, destination, *args, **kwargs)

        with mock.patch.object(migrate.os, 'replace', side_effect=edit_at_cutover):
            try:
                migrate.ensure(self.root)
            except (ValueError, OSError):
                pass
        self.assertTrue(injected, 'Concurrent source change was not injected')
        preserved = {row['content'] for row in self.sql('SELECT content FROM sources')}
        preserved.update(path.read_bytes() for path in self.root.rglob('*') if path.is_file())
        self.assertTrue(revised in preserved, 'Concurrent final legacy revision was overwritten without preservation')
        self.cli('ensure')
        self.assertTrue(revised in {row['content'] for row in self.sql('SELECT content FROM sources')})

    def test_interruption_after_source_displacement_recovers(self):
        source = self.write('docs/coordination/STATE.md', '# State\nPreserve displaced source.\n')
        original = source.read_bytes()
        real_replace = migrate.os.replace
        injected = []

        def interrupt_after_displacement(origin, destination, *args, **kwargs):
            real_replace(origin, destination, *args, **kwargs)
            if Path(origin) == source:
                injected.append(True)
                raise KeyboardInterrupt('interruption after displacement')

        with mock.patch.object(migrate.os, 'replace', side_effect=interrupt_after_displacement):
            with self.assertRaises(KeyboardInterrupt):
                migrate.ensure(self.root)
        self.assertTrue(injected, 'Source displacement interruption was not injected')
        self.assertFalse(source.exists())
        self.assertEqual(self.cli('summary')['unretired_sources'], 1)
        retried = self.cli('ensure')
        self.assertEqual(retried['imported_sources'], 0)
        self.assertEqual(retried['unretired_sources'], 0)
        row = self.sql('SELECT id,content FROM sources')[0]
        self.assertEqual(row['content'], original)
        self.assertEqual(source.read_bytes(), migrate.pointer(row['id']))

    def test_late_open_descriptor_write_is_imported_on_next_ensure(self):
        original = b'# State\nInitial state.\n'
        revised = b'# State\nHold written by a legacy process after migration.\n'
        source = self.write('docs/coordination/STATE.md', original)
        with source.open('r+b') as legacy_writer:
            self.cli('ensure')
            legacy_writer.seek(0)
            legacy_writer.write(revised)
            legacy_writer.truncate()
            legacy_writer.flush()
            os.fsync(legacy_writer.fileno())
            result = self.cli('ensure')
        self.assertEqual(result['imported_sources'], 1)
        self.assertEqual({row['content'] for row in self.sql('SELECT content FROM sources')}, {original, revised})
        self.assertEqual(self.cli('ensure')['imported_sources'], 0)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_racing_recreation_before_pointer_publication_is_preserved(self):
        original = b'# State\nOriginal state.\n'
        revised = b'# State\nNew file from a competing legacy writer.\n'
        source = self.write('docs/coordination/STATE.md', original)
        real_link = migrate.os.link
        injected = []

        def recreate_before_publication(origin, destination, *args, **kwargs):
            if Path(destination) == source:
                self.assertFalse(source.exists())
                source.write_bytes(revised)
                injected.append(True)
            return real_link(origin, destination, *args, **kwargs)

        with mock.patch.object(migrate.os, 'link', side_effect=recreate_before_publication):
            try:
                migrate.ensure(self.root)
            except (ValueError, OSError):
                pass
        self.assertTrue(injected, 'Competing source recreation was not injected')
        self.assertEqual(source.read_bytes(), revised)
        self.cli('ensure')
        self.assertEqual({row['content'] for row in self.sql('SELECT content FROM sources')}, {original, revised})
        self.assertTrue(source.read_text().startswith(migrate.MARKER))

    def test_archive_corruption_refuses_retirement(self):
        source = self.write('docs/coordination/STATE.md', '# State\nKeep original.\n')
        original = source.read_bytes()
        with mock.patch.object(migrate, 'retire', side_effect=OSError('cut power')):
            with self.assertRaises(OSError):
                migrate.ensure(self.root)
        row = self.sql('SELECT * FROM sources')[0]
        (self.root / row['archive_path']).write_bytes(b'corrupted')
        result = self.cli('ensure', ok=False)
        self.assertIn('archive missing/corrupt', result.stderr)
        self.assertEqual(source.read_bytes(), original)
        self.cli('check', ok=False)

    def test_legacy_sqlite_import_preserves_unknown_tables_and_is_repeatable(self):
        legacy = self.legacy_db()
        original = legacy.read_bytes()
        first = self.cli('ensure')
        self.assertEqual(first['imported_sources'], 1)
        self.assertFalse(first['ready_for_dispatch'])
        self.assertEqual(legacy.read_bytes(), original)
        self.assertTrue(Path(str(legacy) + '.MIGRATED.md').exists())
        source = self.sql('SELECT * FROM sources')[0]
        with sqlite3.connect(self.root / source['archive_path']) as snapshot:
            self.assertEqual(snapshot.execute('SELECT payload FROM custom_ledger').fetchone()[0], b'\x00\x01\xff')
        for kind in ('task', 'decision', 'question', 'guideline'):
            self.assertEqual(len(self.cli(kind, 'list')), 1)
        self.assertEqual(self.cli('task', 'list')[0]['status'], 'needs_review')
        self.assertTrue(self.cli('search', '0001ff'))
        before = {table: len(self.sql('SELECT * FROM ' + table)) for table in ('sources', 'records', 'sections')}
        self.assertEqual(self.cli('ensure')['imported_sources'], 0)
        self.assertEqual(before, {table: len(self.sql('SELECT * FROM ' + table)) for table in before})
        with sqlite3.connect(legacy) as con:
            con.execute("INSERT INTO tasks VALUES ('T10','External new task','pending','new')")
        self.assertEqual(self.cli('ensure')['imported_sources'], 1)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 2)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_sqlite_snapshot_includes_committed_wal_content(self):
        legacy = self.root / 'docs/coordination/coord.db'
        legacy.parent.mkdir(parents=True)
        with sqlite3.connect(legacy) as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE tasks(id TEXT,title TEXT)')
            con.execute("INSERT INTO tasks VALUES ('T1','Committed in WAL')")
            con.commit()
            self.cli('ensure')
            self.assertEqual(self.cli('task', 'list')[0]['title'], 'Committed in WAL')
            self.assertEqual(self.cli('ensure')['imported_sources'], 0)
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(list((self.root / '.coordinator').glob('legacy-*')), [])

    def test_external_and_traversal_sources_are_rejected(self):
        outside = self.write('outside.md', '# Outside\nDo not touch.\n', root=self.base)
        for filename in (str(outside), '../outside.md'):
            with self.subTest(path=filename):
                self.write('.coordinator/migration.json', json.dumps({'sources': [filename]}))
                self.cli('ensure', ok=False)
                self.assertEqual(outside.read_bytes(), b'# Outside\nDo not touch.\n')
                self.assertEqual(self.sql('SELECT * FROM sources'), [])

    def test_symlink_sources_outputs_and_store_are_rejected(self):
        outside = self.write('outside.md', '# Outside\nPreserve.\n', root=self.base)
        source = self.root / 'docs/coordination/STATE.md'
        source.parent.mkdir(parents=True)
        source.symlink_to(outside)
        self.cli('ensure', ok=False)
        self.assertEqual(outside.read_text(), '# Outside\nPreserve.\n')
        source.unlink()
        self.init()
        target = self.base / 'outside-dir'
        target.mkdir()
        (self.root / 'escape').symlink_to(target, target_is_directory=True)
        self.cli('backup', 'escape/backup.db', ok=False)
        self.assertFalse((target / 'backup.db').exists())
        other = self.base / 'symlinked-store'
        other.mkdir()
        (other / '.coordinator').symlink_to(target, target_is_directory=True)
        self.cli('ensure', '--init', root=other, ok=False)
        self.assertFalse((target / 'coord.db').exists())

    def test_existing_unrecognized_or_newer_database_is_not_overwritten(self):
        db = self.root / '.coordinator/coord.db'
        db.parent.mkdir()
        with sqlite3.connect(db) as con:
            con.execute('CREATE TABLE unrelated(value TEXT)')
            con.execute("INSERT INTO unrelated VALUES ('preserve me')")
        before = db.read_bytes()
        self.cli('ensure', ok=False)
        self.assertEqual(db.read_bytes(), before)
        with sqlite3.connect(db) as con:
            con.execute('PRAGMA user_version=999')
        before = db.read_bytes()
        self.cli('ensure', ok=False)
        self.assertEqual(db.read_bytes(), before)

    def test_case_alias_cannot_import_canonical_database_into_itself(self):
        self.init()
        alias = self.root / '.COORDINATOR/coord.db'
        if not alias.exists():
            self.skipTest('Case-sensitive filesystem has no storage alias')
        self.write('.coordinator/migration.json', json.dumps({'sources': ['.COORDINATOR/coord.db']}))
        self.cli('ensure', ok=False)
        self.assertEqual(self.sql('SELECT * FROM sources'), [])

    def test_concurrent_ensure_imports_once(self):
        self.write('docs/coordination/STATE.md', '# State\nExactly one source and migration.\n')
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.cli('ensure'), range(6)))
        self.assertEqual(sum(result['imported_sources'] for result in results), 1)
        self.assertEqual(len(self.sql('SELECT * FROM migrations')), 1)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 1)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_concurrent_writers_preserve_records_events_and_compare_and_swap(self):
        self.init()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: self.task('T' + str(i)), range(16)))
        self.assertEqual(len(self.cli('task', 'list')), 16)
        self.assertEqual(len(self.cli('event', 'list', '--limit', '100')), 16)
        def update(i):
            return subprocess.run([sys.executable, str(CLI), '--root', str(self.root),
                                   'task', 'put', 'T0', '--json', json.dumps({'title': str(i)}),
                                   '--if-version', '1'], capture_output=True, text=True,
                                  timeout=30, env=SUBPROCESS_ENV)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(update, range(2)))
        self.assertEqual(sorted(result.returncode for result in results), [0, 1])
        self.assertEqual(self.cli('task', 'show', 'T0')['version'], 2)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_question_uniqueness_and_answer_contract(self):
        self.init()
        question = {'title': 'Choose deployment date', 'source': 'user:3', 'status': 'presented',
                    'options': ['Today', 'Tomorrow']}
        self.put('question', 'Q1', question)
        self.put('question', 'Q2', question, ok=False)
        self.assertEqual(len(self.cli('question', 'list')), 1)
        self.put('question', 'Q1', {'status': 'answered', 'answer': 'Today'}, ok=False)
        self.put('question', 'Q1', {'status': 'answered', 'answer': 'Today', 'answer_source': 'user:4'})
        self.put('question', 'Q2', question)
        self.assertEqual(self.cli('summary')['presented_question'][0]['id'], 'Q2')

    def test_lane_exclusivity_canonicalizes_checkout_paths(self):
        self.init()
        self.task()
        (self.root / 'repo').mkdir()
        (self.root / 'another').mkdir()
        lane = {'title': 'Agent checkout', 'checkout': 'repo', 'task': 'T1', 'agent': 'agent-one'}
        self.put('lane', 'L1', lane)
        self.put('lane', 'L2', {**lane, 'checkout': './repo', 'agent': 'agent-two'}, ok=False)
        self.put('lane', 'L1', {'status': 'released'})
        self.put('lane', 'L2', {**lane, 'agent': 'agent-two'})
        self.assertEqual(self.cli('summary')['active_lanes'][0]['id'], 'L2')
        self.put('lane', 'L3', {**lane, 'checkout': 'another', 'task': 'missing'}, ok=False)

    def test_lane_case_alias_cannot_create_second_writer(self):
        checkout = self.root / 'product-repo'
        checkout.mkdir()
        if not (self.root / 'PRODUCT-REPO').exists():
            self.skipTest('Case-sensitive filesystem has no checkout alias')
        self.init()
        self.task()
        lane = {'title': 'Assigned checkout', 'checkout': 'product-repo', 'task': 'T1', 'agent': 'one'}
        self.put('lane', 'L1', lane)
        self.put('lane', 'L2', {**lane, 'checkout': 'PRODUCT-REPO', 'agent': 'two'}, ok=False)
        self.assertEqual(len(self.cli('summary')['active_lanes']), 1)

    def test_decision_supersession_is_atomic_and_preserves_original(self):
        self.init()
        self.put('decision', 'D1', {'title': 'Keep deploy hold', 'source': 'user:1', 'type': 'hold'})
        original = self.cli('decision', 'show', 'D1')
        self.cli('decision', 'supersede', 'D1', 'D2', '--data', '-', data=json.dumps({'title': 'Lift hold'}), ok=False)
        self.assertEqual(self.cli('decision', 'show', 'D1'), original)
        self.cli('decision', 'show', 'D2', ok=False)
        new = self.cli('decision', 'supersede', 'D1', 'D2', '--data', '-',
                       data=json.dumps({'title': 'Approved release', 'source': 'user:2'}))
        self.assertEqual(new['data']['supersedes'], 'D1')
        old = self.cli('decision', 'show', 'D1')
        self.assertEqual(old['status'], 'superseded')
        self.assertEqual(old['data']['source'], 'user:1')
        self.assertEqual(old['data']['superseded_by'], 'D2')
        self.assertEqual(self.cli('summary')['active_holds'], [])

    def test_agents_have_read_and_append_only_task_event_access(self):
        self.init()
        self.task()
        self.put('decision', 'D1', {'title': 'Keep hold', 'source': 'user:1'})
        before = self.cli('task', 'show', 'T1')
        self.put('task', 'T1', {'title': 'Agent overwrote task'}, actor='agent', ok=False)
        self.cli('ensure', actor='agent', ok=False)
        self.cli('backup', 'agent.db', actor='agent', ok=False)
        self.cli('event', 'add', 'No task reference', actor='agent', ok=False)
        self.cli('event', 'add', 'A decision event', '--record', 'D1', actor='agent', ok=False)
        event = self.cli('event', 'add', 'Tests passed', '--record', 'T1', '--key', 'agent-test:1', actor='agent')
        repeat = self.cli('event', 'add', 'Tests passed', '--record', 'T1', '--key', 'agent-test:1', actor='agent')
        self.assertEqual(event, repeat)
        self.cli('event', 'add', 'Different result', '--record', 'T1', '--key', 'agent-test:1', actor='agent', ok=False)
        self.assertEqual(self.cli('task', 'show', 'T1', actor='agent'), before)
        self.assertEqual(self.cli('event', 'list', '--record', 'T1', actor='agent')[0]['actor'], 'agent')

    def test_review_resolution_needs_explicit_reconciliation(self):
        self.write('docs/coordination/STATE.md', '# Requirements\nPreserve a hold.\n')
        self.cli('ensure')
        review = self.cli('review', 'list')[0]
        self.cli('review', 'resolve', review['id'], '--note', 'Mapped', '--refs', 'missing', ok=False)
        self.assertFalse(self.cli('summary')['ready_for_dispatch'])
        self.put('decision', 'H1', {'title': 'Preserve hold', 'source': review['id'], 'type': 'hold'})
        self.cli('review', 'resolve', review['id'], '--note', 'Preserved original hold', '--refs', 'H1')
        self.assertTrue(self.cli('summary')['ready_for_dispatch'])
        self.assertEqual(self.cli('summary')['active_holds'][0]['id'], 'H1')

    def test_backup_is_consistent_private_and_refuses_overwrite_or_escape(self):
        self.init()
        self.task()
        backup = self.cli('backup', '.coordinator/backups/first.db')['backup']
        with sqlite3.connect(backup) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(con.execute('SELECT id FROM records').fetchall(), [('T1',)])
        if os.name != 'nt':
            self.assertEqual(Path(backup).stat().st_mode & 0o777, 0o600)
        first = Path(backup).read_bytes()
        self.cli('backup', backup, ok=False)
        self.cli('backup', '.coordinator/coord.db', ok=False)
        self.cli('backup', '../escape.db', ok=False)
        self.cli('backup', str(self.base / 'escape.db'), ok=False)
        self.assertEqual(Path(backup).read_bytes(), first)
        self.assertFalse((self.base / 'escape.db').exists())

    def test_source_extraction_and_render_do_not_overwrite_existing_files(self):
        original = b'# State\nUnique source body.\n'
        self.write('docs/coordination/STATE.md', original)
        self.cli('ensure')
        source = self.cli('source', 'list')[0]
        self.assertEqual(self.cli('source', 'show', source['id'])['content'], original.decode())
        self.cli('source', 'show', source['id'], '--output', 'recovered.md')
        self.assertEqual((self.root / 'recovered.md').read_bytes(), original)
        self.cli('source', 'show', source['id'], '--output', 'recovered.md', ok=False)
        self.cli('source', 'show', source['id'], '--output', '../escape.md', ok=False)
        self.cli('render', '--output', 'CLAUDE.md', ok=False)
        report = self.cli('render', '--output', '.coordinator/reports/status.md')
        self.assertTrue(Path(report['output']).is_file())

    def test_hook_noop_for_unrelated_source_kit_and_agent_sessions(self):
        self.write('STATE.md', '# Arbitrary application state\nNot coordinator state.\n')
        self.assertIsNone(self.hook(source='startup'))
        self.assertFalse((self.root / '.coordinator').exists())
        self.write('CLAUDE.md', 'Coordinator Instructions with coordinator-kit.')
        self.write('plugins/coordinator-kit/.claude-plugin/plugin.json', '{}')
        self.assertIsNone(self.hook(source='startup'))
        self.assertFalse((self.root / '.coordinator').exists())
        (self.root / 'plugins/coordinator-kit/.claude-plugin/plugin.json').unlink()
        self.assertIsNone(self.hook(source='startup', agent_id='worker-one'))
        self.assertFalse((self.root / '.coordinator').exists())

    def test_hook_first_startup_resume_and_child_workspace_share_database(self):
        self.write('docs/coordination/STATE.md', '# State\nFirst run needs migration.\n')
        child = self.root / 'repos/product'
        child.mkdir(parents=True)
        first = self.hook(root=child, source='startup')
        self.assertEqual(first['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIn(str(self.root / '.coordinator/coord.db'), first['hookSpecificOutput']['additionalContext'])
        self.assertFalse((child / '.coordinator').exists())
        counts = len(self.sql('SELECT * FROM events'))
        self.hook(root=child, source='resume')
        self.assertEqual(len(self.sql('SELECT * FROM events')), counts)
        self.assertEqual(len(self.sql('SELECT * FROM sources')), 1)

    def test_nonstandard_project_folders_require_explicit_migration_sources(self):
        original = b'# State\nPreserve this custom coordinator source.\n'
        custom_paths = ['sample-autopilot/STATE.md', 'autopilot-notes/STATE.md',
                        'team-coordination/STATE.md']
        for path in custom_paths:
            self.write(path, original)
        self.assertIsNone(self.hook(source='startup'))
        self.assertFalse((self.root / '.coordinator').exists())
        # Even a recognized workspace must not assume similarly named folders are state.
        self.init()
        self.assertEqual(self.cli('source', 'list'), [])
        for path in custom_paths:
            self.assertEqual((self.root / path).read_bytes(), original)
        self.write('.coordinator/migration.json', json.dumps({'sources': custom_paths}))
        self.assertEqual(self.cli('ensure')['imported_sources'], len(custom_paths))
        self.assertEqual({r['path'] for r in self.cli('source', 'list')}, set(custom_paths))
        self.assertEqual({r['content'] for r in self.sql('SELECT content FROM sources')}, {original})
        self.assertEqual(self.cli('ensure')['imported_sources'], 0)

    def test_hook_reports_migration_failure_without_false_success(self):
        outside = self.write('outside.md', '# Outside', root=self.base)
        self.write('.coordinator/migration.json', json.dumps({'sources': [str(outside)]}))
        result = self.hook(source='startup')
        self.assertIn('migration did not complete', result['systemMessage'])
        self.assertIn('Do not dispatch', result['hookSpecificOutput']['additionalContext'])
        self.assertEqual(outside.read_text(), '# Outside')

    @unittest.skipUnless(shutil.which('bash'), 'The configured plugin hook requires bash')
    def test_configured_shell_hook_migrates_workspace_with_spaces(self):
        root = self.base / 'workspace with spaces'
        root.mkdir()
        self.write('docs/coordination/STATE.md', '# State\nPreserve Unicode: café.\n', root=root)
        config = json.loads((PLUGIN / 'hooks/hooks.json').read_text())
        command = config['hooks']['SessionStart'][0]['hooks'][0]['command']
        result = subprocess.run(['bash', '-c', command],
                                env={**SUBPROCESS_ENV, 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)},
                                input=json.dumps({'cwd': str(root), 'source': 'startup'}),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertTrue((root / '.coordinator/coord.db').is_file())
        self.assertEqual(self.cli('check', root=root), {'ok': True})


if __name__ == '__main__':
    unittest.main()
