"""Offline Codex compatibility tests using disposable workspaces only.

Run: python3 -B -m unittest discover -s plugins/coordinator-kit/tests -p test_codex_compat.py -v
These exercise the shared CLI and configured hook, not model output or native hook trust.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
CLI = PLUGIN / 'scripts/coord.py'
HOOK = PLUGIN / 'scripts/session_start.py'
FIXTURES = REPO / '.coordinator-scratch/codex-compat-review/fixtures'
# The only Claude-named environment variable used by the configured-hook test is
# the documented plugin-root compatibility variable supplied by either host.
ENV = {key: value for key, value in os.environ.items() if not key.startswith('CLAUDE_')}
ENV['PYTHONDONTWRITEBYTECODE'] = '1'


class CodexCompatibilityTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace with spaces'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, content, root=None):
        path = (root or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return path

    def cli(self, *args, root=None):
        result = subprocess.run(
            [sys.executable, str(CLI), '--root', str(root or self.root), *args],
            cwd=self.base, env=ENV, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def hook(self, *, cwd=None, command=None, plugin_root=None, **fields):
        payload = {'cwd': str(cwd or self.root), 'session_id': 'codex-fixture-session',
                   'hook_event_name': 'SessionStart', 'source': 'startup', **fields}
        env = dict(ENV)
        if plugin_root is not None:
            env['CLAUDE_PLUGIN_ROOT'] = str(plugin_root)
        result = subprocess.run(
            command or [sys.executable, str(HOOK)], input=json.dumps(payload),
            cwd=self.base, env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout) if result.stdout else None

    def rows(self, query, root=None):
        with sqlite3.connect((root or self.root) / '.coordinator/coord.db') as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(query)]

    def assert_preserved_sources(self, originals):
        rows = self.rows('SELECT * FROM sources')
        self.assertEqual({row['path'] for row in rows}, set(originals))
        for row in rows:
            expected = originals[row['path']]
            self.assertEqual(row['content'], expected)
            self.assertEqual((self.root / row['archive_path']).read_bytes(), expected)
            self.assertNotEqual((self.root / row['path']).read_bytes(), expected)
            self.assertEqual(row['retired'], 1)
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_agents_only_first_run_preserves_instructions_and_source_bytes(self):
        instructions = b'# Team instructions\r\nUse coordinator-kit.\r\n@POLICY.md\r\n'
        policy = b'Do not publish without the owner\xe2\x80\x99s explicit approval.\n'
        self.write('AGENTS.md', instructions)
        self.write('POLICY.md', policy)
        originals = {
            'STATE.md': b'# Current work\r\nPreserve the deploy hold.\r\n',
            'plan.md': b'# Plan\n- [x] Claimed complete but still requires verification.\n',
        }
        for name, content in originals.items():
            self.write(name, content)

        result = self.cli('ensure')

        self.assertTrue(result['detected'])
        self.assertFalse(result['ready_for_dispatch'])
        self.assertEqual(result['imported_sources'], 2)
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), instructions)
        self.assertEqual((self.root / 'POLICY.md').read_bytes(), policy)
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        self.assert_preserved_sources(originals)
        self.assertEqual({task['status'] for task in self.cli('task', 'list')}, {'needs_review'})
        self.assertEqual(self.cli('decision', 'list'), [])

    def test_legacy_coordinator_heading_in_agents_is_recognized(self):
        instructions = b'# Coordinator Instructions\nKeep existing project constraints.\n'
        self.write('AGENTS.md', instructions)
        self.write('STATE.md', '# Current work\nA legacy coordinator task.\n')
        self.assertTrue(self.cli('ensure')['detected'])
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), instructions)
        self.assertEqual(len(self.rows('SELECT * FROM sources')), 1)

    def test_dual_host_instructions_survive_migration_and_repeated_ensure(self):
        instructions = {
            'AGENTS.md': b'# Codex instructions\nUse coordinator-kit.\n@codex-policy.md\n',
            'CLAUDE.md': b'# Claude instructions\r\n@claude-policy.md\r\n',
            'codex-policy.md': b'Preserve the Codex policy.\n',
            'claude-policy.md': b'Preserve the Claude policy.\r\n',
        }
        for name, content in instructions.items():
            self.write(name, content)
        self.write('STATE.md', '# Current work\nFinish the existing work.\n')
        self.cli('ensure')
        counts = {table: len(self.rows('SELECT * FROM ' + table))
                  for table in ('sources', 'sections', 'events', 'migrations')}

        self.assertEqual(self.cli('ensure')['imported_sources'], 0)

        self.assertEqual(counts, {table: len(self.rows('SELECT * FROM ' + table)) for table in counts})
        for name, content in instructions.items():
            self.assertEqual((self.root / name).read_bytes(), content)
        self.assertEqual({row['path'] for row in self.rows('SELECT path FROM sources')}, {'STATE.md'})

    @unittest.skipUnless(shutil.which('bash'), 'The configured common hook requires Bash')
    def test_configured_hook_uses_compat_environment_and_parent_agents_workspace(self):
        # Exercise an installed plugin path with spaces, independently of shell cwd.
        installed = self.base / 'installed plugin with spaces'
        shutil.copytree(PLUGIN, installed,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        config = json.loads((PLUGIN / 'hooks/hooks.json').read_text())
        command = ['bash', '-c', config['hooks']['SessionStart'][0]['hooks'][0]['command']]
        self.write('AGENTS.md', '# Workspace instructions\nUse coordinator-kit.\n')
        original = '# State\nPreserve Unicode: café.\n'.encode()
        self.write('STATE.md', original)
        child = self.root / 'repos/product'
        child_instructions = b'# Product instructions\nUse the existing lint command.\n'
        self.write('AGENTS.md', child_instructions, root=child)

        first = self.hook(cwd=child, command=command, plugin_root=installed)

        self.assertEqual(first['hookSpecificOutput']['hookEventName'], 'SessionStart')
        context = first['hookSpecificOutput']['additionalContext']
        self.assertIn(str(self.root / '.coordinator/coord.db'), context)
        self.assertIn(str(installed / 'scripts/coord.py'), context)
        skill = installed / 'skills/coordination-state/SKILL.md'
        self.assertTrue(skill.is_file())
        self.assertIn(str(skill), context)
        self.assertFalse((child / '.coordinator').exists())
        self.assertFalse((self.base / '.coordinator').exists())
        self.assertEqual((child / 'AGENTS.md').read_bytes(), child_instructions)
        self.assert_preserved_sources({'STATE.md': original})
        counts = {table: len(self.rows('SELECT * FROM ' + table))
                  for table in ('sources', 'events', 'migrations')}

        resumed = self.hook(cwd=child, command=command, plugin_root=installed, source='resume')

        self.assertEqual(resumed['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertEqual(counts, {table: len(self.rows('SELECT * FROM ' + table)) for table in counts})

    def test_unrelated_agents_and_application_state_are_not_auto_migrated(self):
        originals = {'AGENTS.md': b'# App instructions\nRun tests before committing.\n',
                     'STATE.md': b'# Application state\nThis is application documentation.\n'}
        for name, content in originals.items():
            self.write(name, content)
        self.assertIsNone(self.hook())
        self.assertFalse(self.cli('ensure')['detected'])
        self.assertFalse((self.root / '.coordinator').exists())
        for name, content in originals.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_codex_only_kit_source_is_not_auto_migrated_from_root_or_child(self):
        self.write('plugins/coordinator-kit/.codex-plugin/plugin.json', '{"name":"coordinator-kit"}')
        originals = {'AGENTS.md': b'# Coordinator Instructions\nUse coordinator-kit.\n',
                     'STATE.md': b'# Distributable state template\nKeep this template intact.\n'}
        for name, content in originals.items():
            self.write(name, content)
        child = self.root / 'plugins/coordinator-kit'
        self.assertFalse((child / '.claude-plugin/plugin.json').exists())

        self.assertIsNone(self.hook())
        self.assertIsNone(self.hook(cwd=child))
        self.assertFalse(self.cli('ensure')['detected'])

        self.assertFalse((self.root / '.coordinator').exists())
        self.assertFalse((child / '.coordinator').exists())
        for name, content in originals.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_explicit_bootstrap_without_hook_preserves_unrelated_instructions(self):
        instructions = b'# Existing application instructions\n@POLICY.md\n'
        self.write('AGENTS.md', instructions)
        self.write('POLICY.md', 'Preserve all existing development rules.\n')

        result = self.cli('ensure', '--init')

        self.assertTrue(result['detected'])
        self.assertTrue(result['ready_for_dispatch'])
        self.assertEqual(result['imported_sources'], 0)
        self.assertEqual((self.root / 'AGENTS.md').read_bytes(), instructions)
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        self.assertEqual(self.cli('check'), {'ok': True})

    def test_worker_session_does_not_migrate_parent_workspace(self):
        self.write('AGENTS.md', 'Use coordinator-kit.\n')
        original = b'# State\nCoordinator owns migration.\n'
        self.write('STATE.md', original)

        self.assertIsNone(self.hook(agent_id='codex-worker'))

        self.assertFalse((self.root / '.coordinator').exists())
        self.assertEqual((self.root / 'STATE.md').read_bytes(), original)

    def test_failed_hook_reports_context_without_claiming_success(self):
        missing = self.root / 'missing checkout'
        result = self.hook(cwd=missing)
        self.assertEqual(result['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertTrue(result['systemMessage'])
        self.assertEqual(result['hookSpecificOutput']['additionalContext'], result['systemMessage'])
        self.assertFalse(missing.exists())
        self.assertFalse((self.root / '.coordinator').exists())


if __name__ == '__main__':
    unittest.main()
