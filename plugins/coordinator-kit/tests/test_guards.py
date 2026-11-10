"""Guard hook regressions: sample hook inputs in, allow/deny/warn decisions out.

Run: python3 -B -m unittest discover -s plugins/coordinator-kit/tests -v
Fixtures are disposable under .coordinator-scratch/guard-review; HOME is pinned to the fixture so
workspace discovery can never climb into a real coordinator workspace around the checkout.
Input field names follow the Claude Code hooks reference (tool_name, tool_input, agent_id,
transcript_path, tool_response.totalTokens); no model, network or host process is used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
GUARD = PLUGIN / 'scripts/guard.py'
CLI = PLUGIN / 'scripts/coord.py'
FIXTURES = REPO / '.coordinator-scratch/guard-review/fixtures'
GOOD_BRIEF = ('Build task T1. Do not delegate; execute directly. Step cap ~80 steps, then checkpoint and report. '
              'Write logs under .coordinator-scratch/t1/. Long runs: launch with run_in_background and poll in '
              'bounded calls; never end your turn while a run is live.')


class GuardHookTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.base = Path(self.temp.name)
        self.root = self.base / 'workspace'
        self.root.mkdir()
        self.env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(self.base)}
        self.env.pop('COORDINATOR_KIT_GUARDS', None)
        subprocess.run([sys.executable, str(CLI), '--root', str(self.root), 'ensure', '--init'],
                       check=True, capture_output=True, env=self.env, timeout=30)

    def tearDown(self):
        self.temp.cleanup()

    def run_guard(self, guard, payload, env=None, raw=None, command=None):
        payload = {'session_id': 's1', 'cwd': str(self.root), 'hook_event_name': 'PreToolUse', **payload}
        result = subprocess.run(command or [sys.executable, str(GUARD), guard],
                                input=raw if raw is not None else json.dumps(payload),
                                text=True, capture_output=True, timeout=30, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def decision(self, output):
        return None if output is None else output.get('hookSpecificOutput', {}).get('permissionDecision')

    def agent(self, prompt=GOOD_BRIEF, model='build-tier', **fields):
        tool_input = {'description': 'task', 'prompt': prompt, **fields}
        if model is not None:
            tool_input['model'] = model
        return {'tool_name': 'Agent', 'tool_input': tool_input}

    def bash(self, command, **fields):
        return self.run_guard('bash', {'tool_name': 'Bash', 'tool_input': {'command': command}, **fields})

    def configure(self, config):
        (self.root / '.coordinator/guards.json').write_text(json.dumps(config))

    # -- agent dispatch contract -------------------------------------------------------------

    def test_complete_brief_with_explicit_model_is_allowed(self):
        self.assertIsNone(self.run_guard('agent', self.agent()))

    def test_missing_model_is_denied_with_the_way_to_comply(self):
        output = self.run_guard('agent', self.agent(model=None))
        self.assertEqual(self.decision(output), 'deny')
        reason = output['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('model', reason)
        self.assertNotIn('wait_recipe', reason)
        self.assertEqual(self.decision(self.run_guard('agent', self.agent(model='  '))), 'deny')

    def test_each_missing_marker_is_named(self):
        cases = {
            'no_delegation': GOOD_BRIEF.replace('Do not delegate; execute directly. ', ''),
            'step_cap': GOOD_BRIEF.replace('Step cap ~80 steps, then checkpoint and report. ', ''),
            'scratch_dir': GOOD_BRIEF.replace('.coordinator-scratch/t1/', 'a temp folder'),
            'wait_recipe': GOOD_BRIEF.replace('never end your turn while a run is live', 'wait for it'),
        }
        for name, prompt in cases.items():
            with self.subTest(marker=name):
                output = self.run_guard('agent', self.agent(prompt=prompt))
                self.assertEqual(self.decision(output), 'deny')
                reason = output['hookSpecificOutput']['permissionDecisionReason']
                self.assertIn(name, reason)
                self.assertIn('brief-contract', reason)
                for other in set(cases) - {name}:
                    self.assertNotIn(other + ':', reason)

    def test_bundled_contract_text_satisfies_the_guard(self):
        contract = subprocess.run([sys.executable, str(CLI), 'brief-contract', '--scratch', '.coordinator-scratch/t1'],
                                  check=True, capture_output=True, text=True, env=self.env, timeout=30).stdout
        self.assertIsNone(self.run_guard('agent', self.agent(prompt='Fix the parser bug.\n\n' + contract)))
        self.assertEqual(self.decision(self.run_guard('agent', self.agent(prompt='Fix the parser bug.'))), 'deny')

    def test_subagent_calls_other_workspaces_and_exempt_types_pass_untouched(self):
        bare = self.agent(prompt='look around', model=None)
        self.assertEqual(self.decision(self.run_guard('agent', bare)), 'deny')
        self.assertIsNone(self.run_guard('agent', {**bare, 'agent_id': 'agent-7', 'agent_type': 'general-purpose'}))
        outside = self.base / 'plain-project'
        outside.mkdir()
        self.assertIsNone(self.run_guard('agent', {**bare, 'cwd': str(outside)}))
        child = self.root / 'product/src'
        child.mkdir(parents=True)
        self.assertEqual(self.decision(self.run_guard('agent', {**bare, 'cwd': str(child)})), 'deny')
        self.assertIsNone(self.run_guard('agent', self.agent(prompt='look around', model=None, subagent_type='Explore')))
        self.assertIsNone(self.run_guard('agent', self.agent(prompt='continue', model=None, subagent_type='fork')))

    def test_modes_markers_and_kill_switch_are_configurable_per_workspace(self):
        bare = self.agent(prompt='look around', model=None)
        self.configure({'agent_brief': {'mode': 'warn'}})
        output = self.run_guard('agent', bare)
        self.assertIsNone(self.decision(output))
        self.assertIn('model', output['hookSpecificOutput']['additionalContext'])
        self.configure({'agent_brief': {'mode': 'off'}})
        self.assertIsNone(self.run_guard('agent', bare))
        self.configure({'agent_brief': {'require_model': False, 'markers': {'wait_recipe': None, 'step_cap': None}}})
        partial = self.agent(prompt='Do not delegate. Logs in .coordinator-scratch/x.', model=None)
        self.assertIsNone(self.run_guard('agent', partial))
        self.assertEqual(self.decision(self.run_guard('agent', bare)), 'deny')
        self.configure({})
        self.assertIsNone(self.run_guard('agent', bare, env={**self.env, 'COORDINATOR_KIT_GUARDS': 'off'}))

    def test_guard_faults_fail_open(self):
        bare = self.agent(prompt='look around', model=None)
        (self.root / '.coordinator/guards.json').write_text('{not json')
        output = self.run_guard('agent', bare)
        self.assertIsNone(self.decision(output))
        self.assertIn('guard error', output['systemMessage'])
        self.configure({})
        self.assertIsNone(self.decision(self.run_guard('agent', {}, raw='not json at all')))
        self.assertIsNone(self.decision(self.run_guard('nonsense', bare)))
        self.assertIsNone(self.run_guard('agent', {'tool_name': 'Agent', 'cwd': str(self.base / 'missing')}))

    # -- coordinator self-execution ----------------------------------------------------------

    def test_investigative_commands_are_denied_in_the_coordinator_session(self):
        for command in (
                'ssh prod-host free -m',
                'cd repo && git log --oneline -20',
                'git -C product show HEAD~1',
                'git diff --stat',
                'git fetch origin',
                'FOO=1 sudo ssh host uptime',
                'echo start\ncurl -s https://example.test/health',
                'gh run list --commit abc',
                'true; /usr/bin/ssh host',
                'grep -c error ~/.claude/projects/-work/abc.jsonl',
                'tail -5 /private/x/tasks/a1b2.output',
                'git log origin/main',
                'for h in a b; do ssh $h uptime; done',
                'if true; then git show HEAD; fi',
        ):
            with self.subTest(command=command):
                output = self.bash(command)
                self.assertEqual(self.decision(output), 'deny', command)
                self.assertIn('dispatch', output['hookSpecificOutput']['permissionDecisionReason'])

    def test_bookkeeping_and_quoted_text_stay_allowed(self):
        for command in (
                'git status --short',
                'git log origin/main..',
                'git log origin/main..HEAD --oneline',
                'git -C product log @{u}..',
                'git add docs/plan.md && git commit -m "record ssh finding; git log reviewed" && git push origin main',
                'python3 scripts/coord.py --root . summary',
                './notify.sh "the ssh check and the curl probe both passed"',
                'echo "git log" > .coordinator-scratch/note.txt',
                'python3 scripts/watch.py --root . --once',
                'echo "unbalanced',
                'for i in $(seq 1 16); do grep -q rc= .coordinator-scratch/run.log && break; sleep 10; done',
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.bash(command), command)

    def test_subagents_and_plain_projects_run_the_same_commands(self):
        self.assertIsNone(self.bash('ssh prod-host free -m', agent_id='agent-3'))
        outside = self.base / 'plain-project'
        outside.mkdir()
        self.assertIsNone(self.bash('git log --oneline', cwd=str(outside)))

    def test_bash_rules_are_configurable(self):
        self.configure({'coordinator_bash': {'allow': [r'^git diff --cached --stat$'], 'wrappers': ['sudo', 'proxy'],
                                              'deny_commands': {'kubectl': 'cluster inspection'}}})
        self.assertIsNone(self.bash('git diff --cached --stat'))
        self.assertEqual(self.decision(self.bash('git diff HEAD~3')), 'deny')
        self.assertEqual(self.decision(self.bash('proxy git log -3')), 'deny')
        self.assertEqual(self.decision(self.bash('kubectl get pods')), 'deny')
        self.assertEqual(self.decision(self.bash('ssh host')), 'deny')
        self.configure({'coordinator_bash': {'mode': 'warn'}})
        output = self.bash('ssh host')
        self.assertIsNone(self.decision(output))
        self.assertIn('investigative', output['hookSpecificOutput']['additionalContext'])
        self.configure({'coordinator_bash': {'mode': 'off'}})
        self.assertIsNone(self.bash('ssh host'))

    # -- context size -------------------------------------------------------------------------

    def transcript(self, *sizes, sidechain_last=False):
        path = self.base / 'transcript.jsonl'
        lines = [json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'hi'}})]
        for size in sizes:
            lines.append(json.dumps({'type': 'assistant', 'isSidechain': False, 'message': {'usage': {
                'input_tokens': 5, 'cache_creation_input_tokens': 1000, 'cache_read_input_tokens': size - 1005,
                'output_tokens': 700}}}))
        if sidechain_last:
            lines.append(json.dumps({'type': 'assistant', 'isSidechain': True, 'message': {'usage': {
                'input_tokens': 900000, 'output_tokens': 1}}}))
        path.write_text('\n'.join(lines) + '\n{"truncated": ')
        return str(path)

    def context(self, **payload):
        output = self.run_guard('context', {'hook_event_name': 'UserPromptSubmit', **payload})
        return None if output is None else output['hookSpecificOutput']

    def test_coordinator_context_warning_is_thresholded_and_throttled(self):
        self.assertIsNone(self.context(transcript_path=self.transcript(230000)))  # the old 200k cap is silent now
        self.assertIsNone(self.context(transcript_path=self.transcript(400000)))
        first = self.context(transcript_path=self.transcript(400000, 480000, sidechain_last=True))
        self.assertEqual(first['hookEventName'], 'UserPromptSubmit')
        self.assertIn('480k', first['additionalContext'])
        self.assertIsNone(self.context(transcript_path=self.transcript(490000)))
        self.assertIn('540k', self.context(transcript_path=self.transcript(540000))['additionalContext'])
        self.assertIn('460k', self.context(transcript_path=self.transcript(460000))['additionalContext'])
        self.assertIsNone(self.context(transcript_path=self.transcript(480000), agent_id='agent-1'))
        self.assertIsNone(self.context(transcript_path=str(self.base / 'missing.jsonl')))
        self.assertIsNone(self.context())

    def test_context_warning_checkpoints_and_continues_in_the_same_session(self):
        text = self.context(context_tokens=470000)['additionalContext']
        self.assertIn('450k checkpoint cap', text)
        self.assertIn('handoff record', text)
        self.assertIn('backup', text)
        self.assertIn('keep going in this session', text)
        self.assertIn('compaction is the reset', text)
        self.assertIn('never ask the user to open a new session', text)
        self.assertIn('briefs', text)
        self.assertNotIn('fresh session', text)
        self.assertNotIn('ready for', text)

    def test_resume_context_tokens_and_caps_are_configurable(self):
        self.assertIsNone(self.context(hook_event_name='SessionStart', context_tokens=400000))
        self.assertIn('460k', self.context(hook_event_name='SessionStart', context_tokens=460000)['additionalContext'])
        self.configure({'context': {'coordinator_tokens': 500000}})
        self.assertIsNone(self.context(session_id='s2', context_tokens=480000))
        self.configure({'context': {'coordinator_tokens': 200000}})
        self.assertIn('200k checkpoint cap', self.context(session_id='s4', context_tokens=210000)['additionalContext'])
        self.configure({'context': {'mode': 'off'}})
        self.assertIsNone(self.context(session_id='s3', context_tokens=900000))

    def test_oversized_agent_result_is_reported_after_the_agent_tool(self):
        payload = {'hook_event_name': 'PostToolUse', 'tool_name': 'Agent', 'tool_input': {'prompt': 'x'}}
        big = self.context(**payload, tool_response={'totalTokens': 312000, 'content': []})
        self.assertEqual(big['hookEventName'], 'PostToolUse')
        self.assertIn('312k', big['additionalContext'])
        self.assertIsNone(self.context(**payload, tool_response={'totalTokens': 90000}))
        self.assertIsNone(self.context(**payload, tool_response='launched in background'))

    # -- configured hook commands -------------------------------------------------------------

    @unittest.skipUnless(shutil.which('bash'), 'The configured hooks require Bash')
    def test_configured_hook_commands_run_the_guards(self):
        config = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
        matchers = {(event, group.get('matcher')): group['hooks'][0]['command']
                    for event in ('PreToolUse', 'PostToolUse', 'UserPromptSubmit') for group in config[event]}
        self.assertEqual(set(matchers), {('PreToolUse', 'Agent'), ('PreToolUse', 'Bash'), ('PostToolUse', 'Agent'),
                                         ('UserPromptSubmit', None)})
        env = {**self.env, 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)}
        denied = self.run_guard('agent', self.agent(model=None), env=env,
                                command=['bash', '-c', matchers[('PreToolUse', 'Agent')]])
        self.assertEqual(self.decision(denied), 'deny')
        blocked = self.run_guard('bash', {'tool_name': 'Bash', 'tool_input': {'command': 'ssh host'}}, env=env,
                                 command=['bash', '-c', matchers[('PreToolUse', 'Bash')]])
        self.assertEqual(self.decision(blocked), 'deny')
        allowed = self.run_guard('bash', {'tool_name': 'Bash', 'tool_input': {'command': 'git status'}}, env=env,
                                 command=['bash', '-c', matchers[('PreToolUse', 'Bash')]])
        self.assertIsNone(allowed)


if __name__ == '__main__':
    unittest.main()
