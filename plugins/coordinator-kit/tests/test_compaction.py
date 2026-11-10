"""Checkpoint-and-continue regressions: PreCompact checkpoint, SessionStart after compaction, docs.

Run: python3 -B -m unittest discover -s plugins/coordinator-kit/tests -v
Fixtures are disposable under .coordinator-scratch/compaction-review; HOME is pinned to the fixture
so workspace discovery never climbs into a real coordinator workspace. Git repositories and the
"remote" are local fixture directories; nothing touches the network or a host process.
Hook input field names follow the Claude Code hooks reference (PreCompact `trigger`,
SessionStart `source: compact`).
"""
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
CHECKPOINT = PLUGIN / 'scripts/checkpoint.py'
SESSION_START = PLUGIN / 'scripts/session_start.py'
CLI = PLUGIN / 'scripts/coord.py'
FIXTURES = REPO / '.coordinator-scratch/compaction-review/fixtures'
RECORD = 'handoff-auto-checkpoint'


class CompactionTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace'
        self.root.mkdir()
        self.env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(self.base),
                    'GIT_CONFIG_GLOBAL': str(self.base / 'gitconfig'), 'GIT_CONFIG_NOSYSTEM': '1'}
        for name in ('COORDINATOR_KIT_GUARDS', 'COORDINATOR_KIT_CHECKPOINT'):
            self.env.pop(name, None)
        (self.base / 'gitconfig').write_text('[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n'
                                             '[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n')
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    # -- helpers ------------------------------------------------------------------------------

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(CLI), '--root', str(self.root), *args],
                                capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout

    def put(self, kind, key, data):
        return self.cli(kind, 'put', key, '--json', json.dumps(data))

    def git(self, repo, *args):
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                                env=self.env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def run_hook(self, script, payload, env=None):
        payload = {'session_id': 's1', 'cwd': str(self.root), 'transcript_path': str(self.base / 't.jsonl'),
                   **payload}
        result = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), text=True,
                                capture_output=True, timeout=60, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result.stdout

    def precompact(self, **payload):
        return self.run_hook(CHECKPOINT, {'hook_event_name': 'PreCompact', 'trigger': 'auto',
                                          'custom_instructions': None, **payload})

    def compact_start(self, source='compact'):
        output = self.run_hook(SESSION_START, {'hook_event_name': 'SessionStart', 'source': source})
        return json.loads(output)['hookSpecificOutput']['additionalContext']

    def record(self):
        return self.cli('handoff', 'show', RECORD)

    def seed_state(self):
        self.put('task', 'T1', {'title': 'Build the floor plan', 'status': 'in_progress', 'source': 'user:1',
                                'acceptance': ['plan renders'], 'lane': 'web'})
        self.put('question', 'Q1', {'title': 'Ship to TEST?', 'status': 'presented', 'source': 'user:2',
                                    'options': ['yes', 'not yet']})
        self.put('question', 'Q2', {'title': 'Pick a colour', 'source': 'user:3'})
        self.put('decision', 'H1', {'title': 'No production writes', 'source': 'user:4', 'type': 'hold',
                                    'scope': 'production'})
        self.put('lane', 'lane-agent-abc123', {'title': 'web lane', 'task': 'T1', 'agent': 'builder',
                                               'agent_id': 'abc123def', 'checkout': '.', 'shared_checkout': True})
        self.put('handoff', 'H-evening', {'title': 'Coordinator handoff'})

    def snapshot_repo(self, push=None, remote=False):
        repo = self.root / 'bridge'
        repo.mkdir()
        self.git(repo, 'init', '-q')
        (repo / 'README').write_text('bridge\n')
        self.git(repo, 'add', 'README')
        self.git(repo, 'commit', '-q', '-m', 'init')
        if remote:
            bare = self.base / 'remote.git'
            self.git(self.base, 'init', '-q', '--bare', str(bare))
            self.git(repo, 'remote', 'add', 'origin', str(bare))
            self.git(repo, 'push', '-q', '-u', 'origin', 'main')
        snapshot = {'path': 'bridge/snapshots/coord.db', 'repository': 'bridge'}
        if push is not None:
            snapshot['push'] = push
        self.put('profile', 'workspace', {'title': 'Workspace', 'persistence': {'snapshot': snapshot}})
        return repo

    # -- PreCompact checkpoint ----------------------------------------------------------------

    def test_precompact_refreshes_the_handoff_from_canonical_state(self):
        self.seed_state()
        out = self.precompact()
        data = self.record()['data']
        self.assertEqual(self.record()['status'], 'active')
        self.assertEqual(data['type'], 'checkpoint')
        self.assertEqual(data['trigger'], 'auto')
        self.assertEqual(data['errors'], [])
        self.assertEqual([q['id'] for q in data['presented_question']], ['Q1'])
        self.assertEqual(data['presented_question'][0]['options'], ['yes', 'not yet'])
        self.assertEqual([q['id'] for q in data['queued_questions']], ['Q2'])
        self.assertEqual([h['id'] for h in data['active_holds']], ['H1'])
        self.assertEqual(data['active_lanes'][0]['agent_id'], 'abc123def')
        self.assertEqual([t['id'] for t in data['open_tasks']], ['T1'])
        self.assertEqual(data['active_handoffs'], ['H-evening'])
        self.assertTrue(any('abc123def' in step and 'do not relaunch' in step for step in data['resume']))
        self.assertTrue(any('Never ask the user to open a new session' in step for step in data['resume']))
        # stdout is the instruction for the compaction summary: role, ids, unrecorded instructions.
        self.assertIn('keeps working here after compaction', out)
        self.assertIn('never asks the user to open a new session', out)
        self.assertIn('Q1', out)
        self.assertIn('lane-agent-abc123=abc123def', out)
        self.assertIn('H1', out)
        self.assertIn('H-evening', out)
        self.assertIn('not yet recorded in the database', out)
        self.assertNotIn('FAILED', out)
        events = self.cli('event', 'list', '--record', RECORD)
        self.assertTrue(any(e['kind'] == 'checkpoint' for e in events))

    def test_precompact_takes_a_consistent_local_backup_and_keeps_ten(self):
        backups = self.root / '.coordinator/backups'
        backups.mkdir(parents=True)
        for index in range(12):
            (backups / ('precompact-20260101T0000%02dZ.db' % index)).write_bytes(b'old')
        (backups / 'manual.db').write_bytes(b'mine')
        self.precompact()
        path = Path(self.record()['data']['backup'])
        self.assertTrue(path.is_file())
        with sqlite3.connect(str(path)) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(con.execute('SELECT status FROM records WHERE id=?', (RECORD,)).fetchone()[0], 'active')
        self.assertEqual(len(list(backups.glob('precompact-*.db'))), 10)
        self.assertIn(path, list(backups.glob('precompact-*.db')))
        self.assertTrue((backups / 'manual.db').is_file())

    def test_precompact_commits_only_the_designated_snapshot(self):
        repo = self.snapshot_repo()
        (repo / 'unrelated.txt').write_text('staged work in progress\n')
        self.git(repo, 'add', 'unrelated.txt')
        out = self.precompact()
        snapshot = self.record()['data']['snapshot']
        self.assertEqual(snapshot['path'], 'snapshots/coord.db')
        self.assertEqual(self.git(repo, 'rev-parse', '--short', 'HEAD'), snapshot['commit'])
        self.assertEqual(self.git(repo, 'show', '--name-only', '--format=', 'HEAD'), 'snapshots/coord.db')
        self.assertIn('before compaction', self.git(repo, 'log', '-1', '--format=%s'))
        self.assertIn('unrelated.txt', self.git(repo, 'diff', '--cached', '--name-only'))  # still only staged
        self.assertIn('commit ' + snapshot['commit'], out)
        self.assertNotIn('pushed', snapshot)
        with sqlite3.connect(str(repo / 'snapshots/coord.db')) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertFalse(list((repo / 'snapshots').glob('.*precompact-tmp')))

    def test_precompact_pushes_only_snapshot_commits(self):
        repo = self.snapshot_repo(push=True, remote=True)
        self.precompact()
        snapshot = self.record()['data']['snapshot']
        self.assertEqual(snapshot['pushed'], 1)
        self.assertEqual(self.git(repo, 'rev-list', '@{u}..HEAD'), '')
        # An unpushed commit with other work blocks the push; the snapshot is still committed.
        (repo / 'work.txt').write_text('product work\n')
        self.git(repo, 'add', 'work.txt')
        self.git(repo, 'commit', '-q', '-m', 'unverified work')
        out = self.precompact()
        data = self.record()['data']
        self.assertTrue(any('not pushed' in e for e in data['errors']))
        self.assertIn('FAILED', out)
        self.assertEqual(len(self.git(repo, 'rev-list', '@{u}..HEAD').split()), 2)

    def test_precompact_failure_never_blocks_compaction(self):
        (self.root / 'bridge').mkdir()  # not a git repository
        self.put('profile', 'workspace', {'title': 'Workspace', 'persistence': {
            'snapshot': {'path': 'bridge/snapshots/coord.db', 'repository': 'bridge'}}})
        out = self.precompact()
        data = self.record()['data']
        self.assertTrue(data['errors'] and data['errors'][0].startswith('snapshot:'))
        self.assertTrue(Path(data['backup']).is_file())
        self.assertIn('FAILED', out)
        self.assertIn('stop-and-save steps 4-5', out)

    def test_precompact_clears_the_context_warning_throttle_for_this_session(self):
        state = self.root / '.coordinator/guard-state.json'
        state.write_text(json.dumps({'s1': 455000}))
        self.precompact()
        self.assertEqual(json.loads(state.read_text()), {})
        state.write_text(json.dumps({'other': 455000}))
        self.precompact()
        self.assertEqual(json.loads(state.read_text()), {'other': 455000})

    def test_precompact_is_scoped_and_can_be_disabled(self):
        self.assertEqual(self.precompact(agent_id='agent-1'), '')
        outside = self.base / 'plain-project'
        outside.mkdir()
        self.assertEqual(self.precompact(cwd=str(outside)), '')
        (self.root / '.coordinator/guards.json').write_text(json.dumps({'checkpoint': {'mode': 'off'}}))
        self.assertEqual(self.precompact(), '')
        (self.root / '.coordinator/guards.json').unlink()
        self.assertEqual(self.run_hook(CHECKPOINT, {'hook_event_name': 'PreCompact', 'trigger': 'manual'},
                                       env={**self.env, 'COORDINATOR_KIT_CHECKPOINT': 'off'}), '')
        self.assertEqual(self.cli('handoff', 'list'), [])
        self.assertFalse((self.root / '.coordinator/backups').exists())

    # -- SessionStart after compaction ----------------------------------------------------------

    def test_session_start_after_compaction_continues_in_the_same_session(self):
        self.seed_state()
        self.precompact()
        text = self.compact_start()
        self.assertIn('context was compacted', text)
        self.assertIn('Re-read `summary`', text)
        self.assertIn('active handoff', text)
        self.assertIn('still report to this session', text)
        self.assertIn('presented', text)
        self.assertIn('continue the proactive cycle', text)
        self.assertIn('Do not tell the user to start a new session', text)
        self.assertIn(RECORD + ' was written at ' + self.record()['data']['generated_at'], text)
        self.assertNotIn('failed', text)
        self.assertNotIn('Migration review sections', text)

    def test_session_start_after_compaction_names_missing_or_failed_checkpoint(self):
        self.assertIn('No pre-compaction checkpoint record was found', self.compact_start())
        (self.root / 'bridge').mkdir()
        self.put('profile', 'workspace', {'title': 'Workspace', 'persistence': {
            'snapshot': {'path': 'bridge/snapshots/coord.db', 'repository': 'bridge'}}})
        self.precompact()
        text = self.compact_start()
        self.assertIn('failed', text)
        self.assertIn('snapshot:', text)

    def test_startup_and_resume_keep_the_bootstrap_context(self):
        for source in ('startup', 'resume'):
            text = self.compact_start(source)
            self.assertIn('Run summary first', text)
            self.assertNotIn('context was compacted', text)

    # -- wiring and docs ----------------------------------------------------------------------

    def test_hooks_wire_precompact_and_compact_session_start(self):
        config = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
        command = config['PreCompact'][0]['hooks'][0]['command']
        self.assertIn('checkpoint.sh', command)
        self.assertNotIn('matcher', config['PreCompact'][0])  # manual and auto
        # The unmatched SessionStart entry also fires on source "compact".
        self.assertNotIn('matcher', config['SessionStart'][0])
        self.assertIn('session-start.sh', config['SessionStart'][0]['hooks'][0]['command'])
        self.seed_state()
        result = subprocess.run(['bash', '-c', command], text=True, capture_output=True, timeout=60,
                                input=json.dumps({'session_id': 's1', 'cwd': str(self.root),
                                                  'hook_event_name': 'PreCompact', 'trigger': 'manual'}),
                                env={**self.env, 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Q1', result.stdout)
        self.assertEqual(self.record()['data']['trigger'], 'manual')

    def test_docs_checkpoint_and_continue_instead_of_fresh_session(self):
        stop = (PLUGIN / 'skills/stop-and-save/SKILL.md').read_text()
        spine = (PLUGIN / 'skills/bootstrap/templates/coordinator-spine.md').read_text()
        cycle = (PLUGIN / 'references/proactive-cycle.md').read_text()
        for text in (stop, spine, cycle):
            self.assertNotIn('ready for a fresh session', text)
            self.assertNotIn('continue in a fresh session', text)
        self.assertIn('checkpoint and continue', stop.lower())
        self.assertIn('explicit user stop', stop)
        self.assertIn('Never ask the user to open a new session', spine)
        self.assertIn('After a compaction', cycle)
        readme = (PLUGIN / 'README.md').read_text()
        self.assertIn('CLAUDE_CODE_AUTO_COMPACT_WINDOW', readme)
        self.assertIn('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', readme)

    def test_versions_are_consistent(self):
        sys.path.insert(0, str(PLUGIN / 'scripts'))
        try:
            from storage import VERSION
        finally:
            sys.path.pop(0)
        claude = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text())['version']
        codex = json.loads((PLUGIN / '.codex-plugin/plugin.json').read_text())['version']
        profile = json.loads((PLUGIN / 'skills/bootstrap/templates/operating-profile.json').read_text())
        self.assertEqual({claude, codex, profile['plugin_version']}, {VERSION})
        self.assertTrue((PLUGIN / 'CHANGELOG.md').read_text().split('\n## ', 1)[1].startswith(VERSION))


if __name__ == '__main__':
    unittest.main()
