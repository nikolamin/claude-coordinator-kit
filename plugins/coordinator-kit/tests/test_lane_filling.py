"""Automatic lane filling: the autolane hook records dispatched agents, `idle` names what to fill.

Disposable workspaces under .coordinator-scratch/lane-filling/fixtures; no native agent, model,
network or live workspace is used. Hook payloads mirror the host's PostToolUse / SubagentStop input.
"""
import datetime
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
SCRIPTS = PLUGIN / 'scripts'
CLI = SCRIPTS / 'coord.py'
HOOK = SCRIPTS / 'autolane.py'
FIXTURES = REPO / '.coordinator-scratch/lane-filling/fixtures'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import idle  # noqa: E402
import storage  # noqa: E402

ENV = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
ENV.pop('COORDINATOR_KIT_AUTOLANE', None)
SECRET = 'PROMPT-BODY-MUST-NOT-LEAK'


def utc(minutes=0):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)).isoformat(timespec='seconds')


class LaneFillingTests(unittest.TestCase):
    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=FIXTURES)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()
        self.cli('ensure', '--init')

    def tearDown(self):
        self.temp.cleanup()

    # -- helpers -------------------------------------------------------------------------------
    def cli(self, *args, data=None, expected=0, raw=False, actor=None):
        command = [sys.executable, str(CLI), '--root', str(self.root)] + (['--actor', actor] if actor else []) + list(args)
        result = subprocess.run(command, input=json.dumps(data) if data is not None else '', cwd=self.root,
                                env=ENV, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if raw or expected == 1:
            return result.stdout if expected != 1 else result.stderr
        return json.loads(result.stdout)

    def task(self, key, **fields):
        data = {'title': key, 'source': 'fixture:request', 'acceptance': ['Requested behavior works.'], **fields}
        return self.cli('task', 'put', key, '--data', '-', data=data)

    def profile(self, **capacity):
        return self.cli('profile', 'put', 'workspace', '--data', '-', data={'title': 'profile', 'capacity': capacity})

    def hook(self, mode, payload, cwd=None, env=None):
        payload = {'cwd': str(cwd or self.root), **payload}
        result = subprocess.run([sys.executable, '-B', str(HOOK), mode], input=json.dumps(payload), cwd=str(self.root),
                                env=env or ENV, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result.stdout

    def launch(self, launched_id, prompt='Do the work.', description='Build thing', response=None, **extra):
        payload = {'hook_event_name': 'PostToolUse', 'tool_name': 'Agent', 'session_id': 's1',
                   'transcript_path': str(self.root / 'sessions' / 's1.jsonl'),
                   'tool_input': {'description': description, 'prompt': prompt, 'model': 'opus',
                                  'subagent_type': 'general-purpose', 'run_in_background': True},
                   'tool_response': response if response is not None else
                   {'status': 'async_launched', 'agentId': launched_id, 'description': description}}
        payload.update(extra)
        return self.hook('post', payload)

    def stop(self, agent_id, **extra):
        return self.hook('stop', {'hook_event_name': 'SubagentStop', 'session_id': 's1', 'agent_id': agent_id, **extra})

    def lanes(self, status='active'):
        return {r['id']: r for r in self.cli('lane', 'list', '--status', status)}

    def idle(self, *args, mem=50):
        return self.cli('idle', '--mem-free-pct', str(mem), *args)

    # -- storage: shared checkouts ---------------------------------------------------------------
    def test_agents_sharing_one_checkout_do_not_collide_but_exclusive_claims_still_do(self):
        self.task('t1'); self.task('t2')
        (self.root / 'repo').mkdir()
        for n in ('1', '2'):
            self.cli('lane', 'put', 'shared-' + n, '--data', '-', data={
                'title': 'x', 'task': 't' + n, 'checkout': 'repo', 'agent': 'a', 'agent_id': 'agent-00' + n,
                'shared_checkout': True})
        self.assertEqual(len(self.lanes()), 2)
        self.cli('lane', 'put', 'own-1', '--data', '-', data={'title': 'x', 'task': 't1', 'checkout': 'repo', 'agent': 'a'})
        error = self.cli('lane', 'put', 'own-2', '--data', '-', expected=1,
                         data={'title': 'x', 'task': 't2', 'checkout': 'repo', 'agent': 'a'})
        self.assertIn('UNIQUE', error)
        error = self.cli('lane', 'put', 'shared-3', '--data', '-', expected=1, data={
            'title': 'x', 'task': 't2', 'checkout': 'repo', 'agent': 'a', 'shared_checkout': True})
        self.assertIn('requires agent_id', error)
        error = self.cli('lane', 'put', 'shared-4', '--data', '-', expected=1, data={
            'title': 'x', 'task': 't2', 'checkout': '.', 'agent': 'a', 'agent_id': 'agent-001', 'shared_checkout': True})
        self.assertIn('UNIQUE', error)  # the same agent cannot hold two active lanes either

    # -- hook: post ------------------------------------------------------------------------------
    def test_background_dispatch_registers_a_lane_with_agent_id_and_auto_task(self):
        self.assertEqual(self.launch('abc123def456', prompt=SECRET + '\nLane: web'), '')
        lane = self.lanes()['lane-agent-abc123def456']
        data = lane['data']
        self.assertEqual((data['agent_id'], data['task'], data['lane'], data['checkout']),
                         ('abc123def456', 'agent-abc123def456', 'web', '.'))
        self.assertTrue(data['shared_checkout'] and data['auto_lane'])
        self.assertEqual(lane['resource'], 'agent:abc123def456')
        self.assertTrue(data['transcript'].endswith('sessions/s1/subagents/agent-abc123def456.jsonl'))
        task = self.cli('task', 'show', 'agent-abc123def456')
        self.assertEqual((task['status'], task['data']['lane']), ('in_progress', 'web'))
        self.assertNotIn(SECRET, (self.root / '.coordinator/coord.db').read_bytes().decode('utf-8', 'replace'))
        self.assertNotIn(SECRET, (self.root / '.coordinator/autolane-health.json').read_text())

    def test_task_marker_links_existing_task_and_attaches_to_the_coordinators_claim(self):
        self.task('login-fix', lane='web')
        (self.root / 'repo').mkdir()
        self.cli('lane', 'put', 'claim-1', '--data', '-', data={'title': 'x', 'task': 'login-fix', 'checkout': 'repo',
                                                               'agent': 'pending dispatch'})
        self.launch('agent000001', prompt='Brief.\nTask: login-fix\nmore')
        lanes = self.lanes()
        self.assertEqual(list(lanes), ['claim-1'])
        self.assertEqual(lanes['claim-1']['data']['agent_id'], 'agent000001')
        self.assertTrue(lanes['claim-1']['resource'].endswith('repo'))  # exclusive claim kept
        # A second agent on the same task without a free claim gets its own shared lane.
        self.launch('agent000002', prompt='Task: `login-fix`')
        self.assertEqual(self.lanes()['lane-agent-agent000002']['data']['task'], 'login-fix')

    def test_task_found_by_task_id_mention_or_backticked_open_task_only(self):
        self.task('alpha'); self.task('beta'); self.task('closed-one', status='done')
        self.launch('agent00000a', prompt='Run with TASK_ID=alpha now')
        self.launch('agent00000b', prompt='See `closed-one` and then `beta` and `nope`')
        lanes = self.lanes()
        self.assertEqual(lanes['lane-agent-agent00000a']['data']['task'], 'alpha')
        self.assertEqual(lanes['lane-agent-agent00000b']['data']['task'], 'beta')

    def test_recorded_host_payload_shape_registers(self):
        # Key set of a real Claude Code async Agent PostToolUse tool_response (values replaced).
        self.launch('a1b2c3d4e5f6a7b8c', response={
            'isAsync': True, 'status': 'async_launched', 'agentId': 'a1b2c3d4e5f6a7b8c', 'description': 'd',
            'resolvedModel': 'opus', 'prompt': SECRET, 'outputFile': '/x/tasks/a1.output',
            'canReadOutputFile': True, 'canContinueAgent': True})
        self.assertEqual(self.lanes()['lane-agent-a1b2c3d4e5f6a7b8c']['data']['agent_id'], 'a1b2c3d4e5f6a7b8c')

    def test_payload_variants_sync_nested_and_foreign_calls(self):
        self.launch('agentblock1', response={'content': [{'type': 'text', 'text': 'Async agent launched. agentId: agentblock1'}],
                                             'isAsync': True})
        self.launch('agenttext01', response='Agent is running in the background. agent_id="agenttext01"')
        self.launch('agentsync01', response={'status': 'completed', 'agentId': 'agentsync01', 'content': []})
        self.launch('agentnest01', agent_id='parent-agent-1')
        self.launch('agentbash01', tool_name='Bash')
        self.assertEqual(set(self.lanes()), {'lane-agent-agentblock1', 'lane-agent-agenttext01'})
        # Repeating the same PostToolUse is idempotent.
        self.launch('agentblock1', response={'status': 'async_launched', 'agentId': 'agentblock1'})
        self.assertEqual(len(self.lanes()), 2)
        outside = Path(self.temp.name) / 'elsewhere'
        outside.mkdir()
        self.hook('post', {'tool_name': 'Agent', 'tool_input': {}, 'tool_response':
                           {'status': 'async_launched', 'agentId': 'agentaway01'}}, cwd=outside)
        self.assertNotIn('lane-agent-agentaway01', self.lanes())

    def test_disabled_by_workspace_config_or_environment(self):
        (self.root / '.coordinator/guards.json').write_text('{"autolane": {"mode": "off"}}')
        self.launch('agentoff001')
        (self.root / '.coordinator/guards.json').unlink()
        self.hook('post', {'tool_name': 'Agent', 'tool_input': {}, 'tool_response': {
            'status': 'async_launched', 'agentId': 'agentoff002'}}, env={**ENV, 'COORDINATOR_KIT_AUTOLANE': 'off'})
        self.assertEqual(self.lanes(), {})

    def test_hook_failure_is_reported_once_and_surfaces_in_idle_until_fixed(self):
        self.task('ready', lane='web', queue_pos=1)
        out = self.launch('x', response={'status': 'async_launched', 'unexpected': 1})
        self.assertIn('could not record', json.loads(out)['systemMessage'])
        self.assertEqual(self.launch('y', response={'status': 'async_launched'}), '')  # same streak: quiet
        health = json.loads((self.root / '.coordinator/autolane-health.json').read_text())
        self.assertEqual(health['failures'], 2)
        self.assertIn('response shape', health['last_error'])
        view = self.idle()
        self.assertTrue(view['action_required'])
        self.assertTrue(view['lines'][0].startswith('IDLE-LANES: AUTOLANE-HOOK FAILING x2'))
        sweep = self.cli('sweep', '--available-slots', 'auto', '--now', utc())
        self.assertIn('lane_hook_failing', [i['kind'] for i in sweep['items']])
        self.launch('agentgood01')
        self.assertIsNone(self.idle()['hook_health'])

    # -- hook: stop ------------------------------------------------------------------------------
    def test_subagent_stop_releases_every_lane_of_that_agent_and_closes_its_auto_task(self):
        self.task('manual-task')
        self.cli('lane', 'put', 'manual', '--data', '-', data={'title': 'x', 'task': 'manual-task', 'checkout': '.',
                                                              'agent': 'a', 'agent_id': 'agentstop01'})
        self.launch('agentstop02')
        self.stop('agentstop01')
        self.stop('unknown0001')
        self.assertEqual(set(self.lanes()), {'lane-agent-agentstop02'})
        self.assertEqual(self.cli('task', 'show', 'manual-task')['status'], 'pending')
        self.stop('', agent_transcript_path='/x/subagents/agent-agentstop02.jsonl')
        self.assertEqual(self.lanes(), {})
        released = self.lanes('released')['lane-agent-agentstop02']['data']
        self.assertEqual(released['released_by'], 'autolane SubagentStop')
        self.assertEqual(self.cli('task', 'show', 'agent-agentstop02')['status'], 'done')

    @unittest.skipUnless(shutil.which('bash'), 'The configured hooks require Bash')
    def test_configured_hooks_record_and_release_through_bash(self):
        hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
        post = [h['command'] for g in hooks['PostToolUse'] if g.get('matcher') == 'Agent' for h in g['hooks']
                if 'autolane' in h['command']]
        stop = [h['command'] for g in hooks['SubagentStop'] for h in g['hooks'] if 'autolane' in h['command']]
        self.assertEqual((len(post), len(stop)), (1, 1))
        env = {**ENV, 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)}
        for command, payload in ((post[0], {'tool_name': 'Agent', 'tool_input': {'prompt': 'Lane: api'},
                                            'tool_response': {'status': 'async_launched', 'agentId': 'agentbash99'}}),):
            subprocess.run(['bash', '-c', command], input=json.dumps({'cwd': str(self.root), **payload}), env=env,
                           text=True, capture_output=True, timeout=60, check=True)
        self.assertIn('lane-agent-agentbash99', self.lanes())
        subprocess.run(['bash', '-c', stop[0]], input=json.dumps({'cwd': str(self.root), 'agent_id': 'agentbash99'}),
                       env=env, text=True, capture_output=True, timeout=60, check=True)
        self.assertEqual(self.lanes(), {})

    # -- idle ------------------------------------------------------------------------------------
    def test_one_ranked_pick_per_idle_lane_p0_first_and_last_resort_last(self):
        self.task('web-low', lane='web', priority='P2', queue_pos=1)
        self.task('web-top', lane='web', priority='P0', queue_pos=5)
        self.task('weekly-api-fail', lane='api', priority='P0', queue_pos=2)
        self.task('api-flagged', lane='api', priority='P0', queue_pos=3, last_resort=True)
        self.task('api-numeric', lane='api', priority=7, queue_pos=4)
        self.task('ops-only-weekly', lane='ops', priority='P1', queue_pos=6, last_resort=True)
        view = self.idle()
        self.assertEqual([(p['lane'], p['task']) for p in view['idle_lanes']],
                         [('web', 'web-top'), ('api', 'api-numeric'), ('ops', 'ops-only-weekly')])
        self.assertEqual(view['idle_lanes'][1]['ready'], 3)
        self.assertEqual(view['free_slots'], 4)
        self.assertEqual(view['lines'][0], 'IDLE-LANES: FREE-SLOTS: 4 (agents 0/4, mem 50% free)')
        self.assertEqual(view['lines'][1], 'IDLE-LANES: web (2) pick web-top P0 web-top')

    def test_running_agent_binds_its_lane_and_takes_a_slot(self):
        self.profile(max_agents=3)
        self.task('web-1', lane='web', queue_pos=1); self.task('api-1', lane='api', queue_pos=2)
        self.task('ops-1', lane='ops', queue_pos=3)
        self.task('web-running', lane='web', status='in_progress')
        self.launch('agentweb001', prompt='Task: web-running')  # lane from its task
        self.launch('agentops001', prompt='Lane: ops')          # lane from the brief marker
        view = self.idle()
        self.assertEqual(view['busy_lanes'], {'ops': ['agentops001'], 'web': ['agentweb001']})
        self.assertEqual(([p['lane'] for p in view['idle_lanes']], view['free_slots'], view['max_agents_source']),
                         (['api'], 1, 'profile'))
        self.assertEqual(self.idle('--max-agents', '2')['free_slots'], 0)
        self.assertEqual(self.idle('--max-agents', '2')['lines'], [])
        self.stop('agentops001')
        self.assertEqual([p['lane'] for p in self.idle()['idle_lanes']], ['api', 'ops'])

    def test_free_slots_fill_best_lanes_first_then_the_unassigned_pool(self):
        self.profile(max_agents=3)
        self.task('a-1', lane='a', priority='P3', queue_pos=1)
        self.task('b-1', lane='b', priority='P1', queue_pos=2)
        self.task('pool-1', queue_pos=3); self.task('pool-2', queue_pos=4); self.task('pool-3')
        view = self.idle()
        self.assertEqual([(p['lane'], p['task'], p['action']) for p in view['dispatch']],
                         [('b', 'b-1', 'dispatch'), ('a', 'a-1', 'dispatch'), ('unassigned', 'pool-1', 'dispatch')])
        self.assertEqual(view['pool_ready'], 3)
        self.profile(max_agents=1)
        self.assertEqual([p['task'] for p in self.idle()['dispatch']], ['b-1'])

    def test_memory_gate_and_host_readers(self):
        self.task('t', lane='web', queue_pos=1)
        self.profile(min_free_memory_pct=20)
        gated = self.idle(mem=19)
        self.assertEqual((gated['free_slots'], gated['memory_gated'], gated['dispatch'], gated['action_required']),
                         (0, True, [], False))
        self.assertEqual(self.idle(mem=20)['free_slots'], 4)
        fake = lambda *a, **k: subprocess.CompletedProcess(a, 0, 'System-wide memory free percentage: 37%\n')  # noqa: E731
        self.assertEqual(idle.memory_free_pct('darwin', run=fake), 37)
        broken = lambda *a, **k: (_ for _ in ()).throw(OSError('missing'))  # noqa: E731
        self.assertIsNone(idle.memory_free_pct('darwin', run=broken))
        meminfo = Path(self.temp.name) / 'meminfo'
        meminfo.write_text('MemTotal:       1000 kB\nMemFree: 1 kB\nMemAvailable:    250 kB\n')
        self.assertEqual(idle.memory_free_pct('linux', meminfo=str(meminfo)), 25)
        self.assertIsNone(idle.memory_free_pct('linux', meminfo=str(meminfo) + '.missing'))

    def test_quiet_agents_and_stale_unattached_claims_do_not_hold_a_lane(self):
        self.task('web-1', lane='web', queue_pos=1)
        self.task('web-busy', lane='web', status='in_progress')
        self.launch('agentquiet1', prompt='Task: web-busy')
        transcript = Path(self.lanes()['lane-agent-agentquiet1']['data']['transcript'])
        transcript.parent.mkdir(parents=True)
        transcript.write_text('{}')
        self.assertEqual(self.idle()['busy_lanes'], {'web': ['agentquiet1']})
        old = transcript.stat().st_mtime - 31 * 60
        os.utime(transcript, (old, old))
        view = self.idle()
        self.assertEqual(([p['lane'] for p in view['idle_lanes']], view['quiet_agents'][0]['agent_id']),
                         (['web'], 'agentquiet1'))
        self.assertTrue(any('QUIET-AGENTS 1: agentquiet1' in line for line in view['lines']))
        self.stop('agentquiet1')
        # A claim without agent id holds its lane for claim_minutes, then is reported as unattached.
        self.task('api-1', lane='api', queue_pos=2); self.task('api-claimed', lane='api')
        self.cli('lane', 'put', 'claim', '--data', '-', data={'title': 'x', 'task': 'api-claimed', 'checkout': '.', 'agent': 'a'})
        self.assertIn('api', self.idle()['busy_lanes'])
        later = self.idle('--now', utc(31))
        self.assertNotIn('api', later['busy_lanes'])
        self.assertEqual(later['unattached_lanes'][0]['lane_record'], 'claim')
        self.assertTrue(later['action_required'])
        sweep = self.cli('sweep', '--available-slots', 'auto', '--now', utc(31))
        self.assertIn('attach_or_release_lane', [i['kind'] for i in sweep['items']])

    def test_lane_blocker_silences_one_lane_until_it_expires_or_is_cleared(self):
        self.task('web-1', lane='web', queue_pos=1); self.task('api-1', lane='api', queue_pos=2)
        self.cli('idle', 'block', 'web', '--reason', 'waits for the API contract decision', '--hours', '2')
        view = self.idle()
        self.assertEqual([p['lane'] for p in view['idle_lanes']], ['api'])
        self.assertEqual(view['blocked_lanes'][0]['blocker']['reason'], 'waits for the API contract decision')
        self.assertEqual([p['lane'] for p in self.idle('--now', utc(121))['idle_lanes']], ['web', 'api'])
        self.cli('idle', 'unblock', 'web')
        self.assertEqual(len(self.idle()['idle_lanes']), 2)
        self.cli('idle', 'block', '*', '--reason', 'user stop in force')
        self.assertEqual((self.idle()['dispatch'], self.cli('idle', '--mem-free-pct', '50', '--lines', '--check', raw=True)), ([], ''))
        self.assertIn('concrete reason', self.cli('idle', 'block', 'web', expected=1))
        self.assertIn('lane name', self.cli('idle', 'block', expected=1))
        self.assertIn('Agent mode', self.cli('idle', 'block', 'web', '--reason', 'x', expected=1, actor='agent'))
        self.assertIn('idle_lanes', self.cli('idle', '--mem-free-pct', '50', actor='agent'))

    def test_holds_and_unprepared_picks_name_the_action(self):
        self.task('prepped', lane='web', queue_pos=1)
        self.task('raw', lane='api')
        self.assertEqual({p['task']: p['action'] for p in self.idle()['dispatch']}, {'prepped': 'dispatch', 'raw': 'prepare'})
        self.cli('decision', 'put', 'hold-1', '--data', '-', data={'title': 'hold', 'source': 'user', 'type': 'hold'})
        view = self.idle()
        self.assertEqual({p['action'] for p in view['dispatch']}, {'review_hold'})
        self.assertTrue(view['lines'][1].endswith('[check hold scope]'))

    def test_lines_and_check_for_watch_commands(self):
        self.assertEqual(self.cli('idle', '--mem-free-pct', '50', '--lines', raw=True), '')
        self.cli('idle', '--mem-free-pct', '50', '--check')
        self.task('t', lane='web', queue_pos=1, priority='P1')
        out = self.cli('idle', '--mem-free-pct', '50', '--lines', '--check', raw=True, expected=2)
        self.assertEqual(out.splitlines(), ['IDLE-LANES: FREE-SLOTS: 4 (agents 0/4, mem 50% free)',
                                            'IDLE-LANES: web (1) pick t P1 t'])
        self.assertIn('timezone-aware', self.cli('idle', '--now', '2026-01-01T00:00:00', expected=1))
        self.assertIn('between 1 and 64', self.cli('idle', '--max-agents', '0', expected=1))

    def test_sweep_auto_requires_dispatch_or_blocker_before_idle(self):
        self.task('web-1', lane='web', queue_pos=1); self.task('web-2', lane='web', queue_pos=2)
        self.task('api-1', lane='api', queue_pos=3)
        now = utc()
        sweep = self.cli('sweep', '--available-slots', 'auto', '--now', now)
        self.assertEqual([(i['kind'], i['task'], i['lane']) for i in sweep['items']],
                         [('dispatch_candidate', 'web-1', 'web'), ('dispatch_candidate', 'api-1', 'api')])
        self.assertEqual(sweep['capacity']['idle_lanes'], ['web', 'api'])
        self.cli('sweep', '--available-slots', 'auto', '--check-idle', '--now', now, expected=2)
        self.launch('agentweb777', prompt='Task: web-1')
        self.cli('idle', 'block', 'api', '--reason', 'needs staging database access')
        self.assertTrue(self.cli('sweep', '--available-slots', 'auto', '--check-idle', '--now', utc())['idle_ready'])
        bad = subprocess.run([sys.executable, str(CLI), '--root', str(self.root), 'sweep', '--available-slots', 'many'],
                             env=ENV, text=True, capture_output=True, timeout=60)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("'auto'", bad.stderr)

    def test_combined_watch_wakes_on_idle_lanes_once_and_can_be_turned_off(self):
        def watch():
            result = subprocess.run([sys.executable, str(SCRIPTS / 'watch.py'), '--root', str(self.root), '--once'],
                                    env=ENV, text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout
        self.profile(min_free_memory_pct=0)  # host memory never gates this test
        self.assertEqual(watch(), '')
        self.task('web-1', lane='web', queue_pos=1)
        self.assertEqual(watch(), 'IDLE_LANES free=4 picks=web:web-1 (coord.py idle; dispatch each pick now or record '
                                  'coord.py idle block LANE --reason)\n')
        self.assertEqual(watch(), '')  # unchanged state is not repeated before repeat_after_seconds
        self.task('api-1', lane='api', queue_pos=2)
        self.assertIn('picks=web:web-1,api:api-1', watch())
        self.task('api-2', lane='api', queue_pos=3)
        (self.root / '.coordinator/watch.json').write_text('{"idle": false, "checks": []}')
        self.assertEqual(watch(), '')
        (self.root / '.coordinator/watch.json').unlink()
        self.launch('broken', response={'status': 'async_launched'})
        self.assertTrue(watch().startswith('LANE_HOOK_FAILING since '))

    def test_brief_contract_prints_the_marker_lines_the_hook_reads(self):
        out = self.cli('brief-contract', '--scratch', '.coordinator-scratch/t1', '--task', 'login-fix', '--lane', 'web',
                       '--checkout', 'repo', raw=True)
        self.assertTrue(out.startswith('Task: login-fix\nLane: web\nCheckout: repo\nExecution contract'))
        self.task('login-fix')
        (self.root / 'repo').mkdir()
        self.launch('agentbrief1', prompt=out)
        lane = self.lanes()['lane-agent-agentbrief1']['data']
        self.assertEqual((lane['task'], lane['lane'], lane['checkout']), ('login-fix', 'web', 'repo'))
        self.assertIn('single tokens', self.cli('brief-contract', '--scratch', '.coordinator-scratch/t', '--task', 'a b',
                                                expected=1))


if __name__ == '__main__':
    unittest.main()
