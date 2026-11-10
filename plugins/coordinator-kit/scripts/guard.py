#!/usr/bin/env python3
"""Coordinator guard hooks: enforce the few rules that instructions alone lose under load.

Usage (hook command, JSON on stdin): guard.py agent | bash | context

  agent    PreToolUse on Agent: a coordinator dispatch needs an explicit model and the brief contract.
  bash     PreToolUse on Bash: the coordinator session does not run investigative commands itself.
  context  UserPromptSubmit / PostToolUse on Agent: warn when coordinator or agent context passes its cap.

Scope: only the main session (hook input without agent_id) of an established coordinator workspace
(.coordinator/coord.db found from cwd upward). Everything else is allowed untouched.
Each guard fails closed on its rule and open on its own errors: a broken guard never blocks work.
Configure or disable per workspace in .coordinator/guards.json; COORDINATOR_KIT_GUARDS=off disables all.
"""
import json
import os
from pathlib import Path
import re
import shlex
import sys

CONTRACT_HINT = ('Print the standard contract with the bundled `coord.py --root WORKSPACE brief-contract '
                 '--scratch .coordinator-scratch/<task>` and paste it into the brief.')
DEFAULTS = {
    'agent_brief': {
        'mode': 'deny',
        'require_model': True,
        # Host-defined helpers whose brief is a lookup, and forks, which inherit model and context.
        'exempt_agent_types': ['fork', 'Explore', 'Plan', 'claude-code-guide', 'statusline-setup', 'web-fetch'],
        'markers': {
            'no_delegation': {'all': [r"(?i)do not delegate|don't delegate|no delegation"],
                              'hint': 'say "Do not delegate; execute directly."'},
            'step_cap': {'all': [r'(?i)step cap|cap\D{0,20}\d+\s*(tool\s*)?(steps|calls)|\d+\s*(tool\s*)?steps'],
                         'hint': 'state the step cap and the checkpoint-then-report rule'},
            'scratch_dir': {'all': [r'\.coordinator-scratch'],
                            'hint': 'name the task-owned .coordinator-scratch/ directory for logs and reports'},
            'wait_recipe': {'all': [r'(?i)run_in_background|background launch', r'(?i)end (your|the) turn'],
                            'hint': 'include the wait recipe (background launch, bounded polls, never end the turn while a run is live)'},
        },
    },
    'coordinator_bash': {
        'mode': 'deny',
        'wrappers': ['sudo', 'env', 'time', 'command', 'nohup', 'exec'],
        'deny_commands': {
            'ssh': 'remote shell', 'scp': 'remote copy', 'sftp': 'remote copy',
            'curl': 'network probe', 'wget': 'network probe', 'gh': 'CI/GitHub read',
        },
        'deny_git': ['log', 'show', 'diff', 'fetch', 'rev-list', 'blame', 'reflog', 'grep', 'bisect'],
        # Raw-command regexes for agent transcripts and native task output files.
        'deny_patterns': [
            {'pattern': r'\.claude/projects/\S*\.jsonl|/subagents/\S*\.jsonl|\btasks/\S+\.output\b',
             'label': 'agent transcript/output read'},
        ],
        'allow': [],
    },
    # coordinator_tokens is a checkpoint threshold, not a session end: the session keeps going and the
    # host's compaction is the reset (the PreCompact hook, scripts/checkpoint.py, also checkpoints).
    'context': {'mode': 'warn', 'coordinator_tokens': 450000, 'agent_tokens': 200000, 'step': 50000},
}
CONTROL = {'&&', '||', ';', '|', '&', '(', ')', '|&', ';;'}
KEYWORDS = {'do', 'then', 'else', 'elif', 'if', 'while', 'until', '!', '{', '}', 'done', 'fi'}
GIT_VALUE_OPTIONS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace'}


def find_root(cwd):
    """Nearest ancestor holding the coordinator database; never above the home directory."""
    path = Path(cwd).resolve()
    home = Path.home().resolve()
    for candidate in (path, *path.parents):
        if (candidate / '.coordinator' / 'coord.db').is_file():
            return candidate
        if candidate == home:
            break
    return None


def load_config(root):
    config = json.loads(json.dumps(DEFAULTS))
    path = root / '.coordinator' / 'guards.json'
    if path.is_file():
        custom = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(custom, dict):
            raise ValueError('guards.json must hold a JSON object')
        for section, values in custom.items():
            if section in config and isinstance(values, dict):
                for key, value in values.items():
                    # Named maps merge entry by entry, so one marker can be changed or nulled alone.
                    if isinstance(value, dict) and isinstance(config[section].get(key), dict):
                        config[section][key].update(value)
                    else:
                        config[section][key] = value
    return config


def emit(event, decision=None, reason=None, context=None):
    specific = {'hookEventName': event}
    if decision:
        specific['permissionDecision'] = decision
        specific['permissionDecisionReason'] = reason
    if context:
        specific['additionalContext'] = context[:9000]
    print(json.dumps({'hookSpecificOutput': specific}))


def verdict(mode, event, message):
    """deny blocks the call with the way to comply; warn lets it run and tells the model."""
    if mode == 'deny':
        emit(event, 'deny', message)
    elif mode == 'warn':
        emit(event, context='coordinator-kit guard (warn mode): ' + message)


def check_agent(data, config):
    tool_input = data.get('tool_input') or {}
    if tool_input.get('subagent_type') in config['exempt_agent_types']:
        return None
    problems = []
    if config['require_model'] and not str(tool_input.get('model') or '').strip():
        problems.append('set `model` explicitly from the recorded model routing (an omitted model silently inherits the coordinator model)')
    prompt = tool_input.get('prompt')
    prompt = prompt if isinstance(prompt, str) else ''
    for name, marker in config['markers'].items():
        if marker and not all(re.search(pattern, prompt) for pattern in marker.get('all', [])):
            problems.append(name + ': ' + marker.get('hint', 'required brief marker missing'))
    if not problems:
        return None
    return ('Dispatch blocked: the brief does not meet the coordinator contract. Missing: ' + '; '.join(problems) + '. '
            + CONTRACT_HINT + ' Then dispatch again. Per-workspace settings: .coordinator/guards.json (agent_brief).')


def command_words(command, wrappers):
    """Yield (word, following tokens) for each simple command; quoted text stays one token."""
    # A newline separates commands like `;` does (only for this analysis; the command itself is untouched).
    lexer = shlex.shlex(command.replace('\n', ' ; '), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens = list(lexer)
    start = True
    for index, token in enumerate(tokens):
        if token in CONTROL:
            start = True
            continue
        if not start:
            continue
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', token) or token in wrappers or token in KEYWORDS:
            continue
        start = False
        rest = []
        for following in tokens[index + 1:]:
            if following in CONTROL:
                break
            rest.append(following)
        yield os.path.basename(token), rest


def git_subcommand(rest):
    skip = False
    for position, token in enumerate(rest):
        if skip:
            skip = False
        elif token in GIT_VALUE_OPTIONS:
            skip = True
        elif not token.startswith('-'):
            return token, rest[position + 1:]
    return None, []


def check_bash(data, config):
    command = (data.get('tool_input') or {}).get('command')
    if not isinstance(command, str) or not command.strip():
        return None
    if any(re.search(pattern, command) for pattern in config['allow']):
        return None
    found = None
    for rule in config['deny_patterns']:
        if re.search(rule['pattern'], command):
            found = (rule.get('label', 'restricted read'), rule['pattern'])
            break
    if not found:
        try:
            words = list(command_words(command, set(config['wrappers'])))
        except ValueError:
            return None  # Not parseable as plain shell words: leave it to the normal permission flow.
        for word, rest in words:
            if word in config['deny_commands']:
                found = (config['deny_commands'][word], word)
                break
            if word == 'git':
                sub, args = git_subcommand(rest)
                # The outgoing-commit check before an authorized push stays with the coordinator.
                outgoing = sub == 'log' and any(re.match(r'(origin/\S+|@\{u(pstream)?\})\.\.', arg) for arg in args)
                if sub in config['deny_git'] and not outgoing:
                    found = ('git history/remote inspection', 'git ' + sub)
                    break
    if not found:
        return None
    return ('Coordinator session: `' + found[1] + '` is investigative work (' + found[0] + '), which the coordinator '
            'delegates. An agent report is the input: if it lacks a fact, ask that agent or dispatch a small lookup '
            'agent with the exact question; put recurring checks into the combined watch (scripts/watch.py). '
            'Bookkeeping stays allowed: coord.py, notifications, git status, `git log origin/<branch>..` and an '
            'authorized commit/push. If this workspace has decided otherwise, record the decision and add an allow '
            'pattern in .coordinator/guards.json (coordinator_bash.allow); do not rephrase the command to slip past.')


def transcript_tokens(path):
    """Best effort: prompt size of the last main-thread model request recorded in the transcript."""
    with open(path, 'rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 1024 * 1024))
        lines = stream.read().split(b'\n')
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get('isSidechain'):
            continue
        message = entry.get('message')
        usage = message.get('usage') if isinstance(message, dict) else None
        if isinstance(usage, dict):
            total = sum(usage.get(key) or 0 for key in
                        ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
            if total > 0:
                return total
    return None


def remember(root, session, tokens, step):
    """True when this size deserves a (new) warning; throttled per session by growth step."""
    path = root / '.coordinator' / 'guard-state.json'
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    last = state.get(session)
    if isinstance(last, int) and last <= tokens < last + step:
        return False
    state = {session: tokens}
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    os.replace(temporary, path)
    return True


def check_context(data, config, root):
    notes = []
    response = data.get('tool_response')
    agent_tokens = response.get('totalTokens') if isinstance(response, dict) else None
    if type(agent_tokens) is int and agent_tokens > config['agent_tokens']:
        notes.append('The agent that just returned ended at about ' + str(agent_tokens // 1000) + 'k tokens of context, over the '
                     + str(config['agent_tokens'] // 1000) + 'k agent cap. Size the next brief smaller: one repository, one '
                     'concern; a fix round is a fresh agent that continues from files on disk.')
    transcript = data.get('transcript_path')
    tokens = data.get('context_tokens')
    if type(tokens) is not int and isinstance(transcript, str) and os.path.isfile(transcript):
        tokens = transcript_tokens(transcript)
    if type(tokens) is int and tokens >= config['coordinator_tokens']:
        if remember(root, str(data.get('session_id') or 'session'), tokens, config['step']):
            notes.append('Coordinator context is about ' + str(tokens // 1000) + 'k tokens, over the '
                         + str(config['coordinator_tokens'] // 1000) + 'k checkpoint cap; every further turn re-reads '
                         'all of it. Checkpoint and keep going in this session: write or update the active handoff '
                         'record and take a backup now (coordinator-kit:stop-and-save steps 3-5, no hold), then continue '
                         'the proactive cycle here. The host\'s compaction is the reset, and the PreCompact hook '
                         'checkpoints again before it; never ask the user to open a new session. Keep agent briefs '
                         'and reports small, and record founder instructions in the database as they arrive.')
    return ' '.join(notes) or None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    event = 'PreToolUse'
    try:
        guard = argv[0] if argv else ''
        if os.environ.get('COORDINATOR_KIT_GUARDS', '').strip().lower() in ('off', '0', 'false', 'disabled'):
            return 0
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get('agent_id'):
            return 0
        event = data.get('hook_event_name') or event
        cwd = data.get('cwd')
        root = find_root(cwd) if isinstance(cwd, str) and os.path.isdir(cwd) else None
        if root is None:
            return 0
        config = load_config(root)
        section = {'agent': 'agent_brief', 'bash': 'coordinator_bash', 'context': 'context'}.get(guard)
        if section is None:
            raise ValueError('unknown guard ' + repr(guard))
        mode = config[section].get('mode')
        if mode not in ('deny', 'warn'):
            return 0
        if guard == 'context':
            message = check_context(data, config[section], root)
            if message:
                emit(event, context='coordinator-kit: ' + message)
            return 0
        message = check_agent(data, config[section]) if guard == 'agent' else check_bash(data, config[section])
        if message:
            verdict(mode, event, message)
    except Exception as exc:
        # Fail open: report the guard's own fault, never block the tool call because of it.
        print(json.dumps({'systemMessage': 'coordinator-kit guard error (call allowed): ' + str(exc)[:300]}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
