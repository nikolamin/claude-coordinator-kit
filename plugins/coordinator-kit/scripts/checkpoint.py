#!/usr/bin/env python3
"""PreCompact hook: checkpoint the coordinator from canonical state before the host compacts.

Usage (hook command, JSON on stdin): checkpoint.py

Compaction replaces the conversation with a summary; the coordinator keeps working in the same
session. Nothing the coordinator needs afterwards may live only in the transcript, so before every
compaction this hook, working only from the canonical database:

1. Refreshes the handoff record `handoff-auto-checkpoint` (status active, type checkpoint): task
   counts, in-progress tasks, active holds and commitments, the presented and queued questions,
   active lanes with their agent ids, the other active handoff ids, and ordered resume actions.
   Coordinator-written handoffs stay authoritative for intent; this record is a mechanical snapshot.
2. Takes a consistent SQLite backup to `.coordinator/backups/precompact-<UTC stamp>.db` (the newest
   KEEP_LOCAL of these are kept; older ones this hook wrote are removed).
3. When the active profile names a snapshot under `persistence.snapshot`
   (`{"path": ..., "repository": ..., "push": false}`, both paths workspace-relative), replaces that
   snapshot with a consistent copy and commits only that file in its repository. With `"push": true`
   it pushes, but only when every outgoing commit touches nothing but the snapshot file.
4. Clears this session's context-warning throttle, so the guard counts again from the compacted size.
5. Prints instructions for the compaction summary (the host feeds PreCompact stdout to the summarizer).

Scope: the main session (no agent_id) of an established coordinator workspace. Never blocks
compaction: every step fails open, and failures are listed in the record (`errors`) and in the
printed instructions so the coordinator finishes them after compaction.
Disable per workspace with {"checkpoint": {"mode": "off"}} in .coordinator/guards.json, or
COORDINATOR_KIT_CHECKPOINT=off.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from guard import find_root
from storage import Store, atomic_write, inside

RECORD = 'handoff-auto-checkpoint'
BACKUPS = '.coordinator/backups'
PREFIX = 'precompact-'
KEEP_LOCAL = 10
GIT_TIMEOUT = 60
CLOSED_TASKS = ('done', 'dropped', 'needs_review')


def stamp():
    """(ISO time for the record, compact UTC stamp for file names and commit messages)."""
    moment = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return moment.isoformat(), moment.strftime('%Y%m%dT%H%M%SZ')


def enabled(root):
    if os.environ.get('COORDINATOR_KIT_CHECKPOINT', '').strip().lower() in ('off', '0', 'false', 'disabled'):
        return False
    path = root / '.coordinator' / 'guards.json'
    try:
        config = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except (OSError, ValueError):
        return True
    section = config.get('checkpoint') if isinstance(config, dict) else None
    return not (isinstance(section, dict) and section.get('mode') == 'off')


def brief(record, *fields):
    data = record['data']
    out = {'id': record['id'], 'title': record['title']}
    for name in fields:
        if data.get(name) not in (None, '', [], {}):
            out[name] = data[name]
    return out


def records(st, kind, status=None):
    sql, params = 'SELECT id FROM records WHERE kind=?', [kind]
    if status:
        sql += ' AND status=?'
        params.append(status)
    return [st.get(r[0]) for r in st.con.execute(sql + ' ORDER BY updated_at DESC,id', params)]


def state(st):
    summary = st.summary()
    tasks = [r for r in records(st, 'task') if r['status'] not in CLOSED_TASKS and r['status'] != 'pending']
    queued = records(st, 'question', 'queued')
    handoffs = [r['id'] for r in records(st, 'handoff', 'active') if r['id'] != RECORD]
    return {
        'task_counts': summary['task_counts'],
        'open_tasks': [dict(brief(r, 'lane', 'queue_pos'), status=r['status']) for r in tasks[:25]],
        'active_holds': [brief(r, 'scope', 'source') for r in summary['active_holds']],
        'active_commitments': summary['active_commitments'],
        'presented_question': [brief(r, 'options', 'source') for r in summary['presented_question']],
        'queued_questions': [brief(r) for r in queued[:10]],
        'active_lanes': [brief(r, 'task', 'agent_id', 'lane', 'checkout') for r in summary['active_lanes']],
        'active_handoffs': handoffs,
    }


def profile_snapshot(st):
    for profile in records(st, 'profile', 'active'):
        persistence = profile['data'].get('persistence')
        snapshot = persistence.get('snapshot') if isinstance(persistence, dict) else None
        if isinstance(snapshot, dict) and snapshot.get('path') and snapshot.get('repository'):
            return snapshot
    return None


def git(repo, *args):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True,
                          timeout=GIT_TIMEOUT, env=env, stdin=subprocess.DEVNULL)


def checked(result, what):
    if result.returncode != 0:
        raise RuntimeError(what + ' failed: ' + (result.stderr or result.stdout).strip()[:200])
    return result.stdout.strip()


def local_backup(st, root, at):
    folder = inside(root, BACKUPS)
    target = st.backup(str(folder / (PREFIX + at + '.db')))
    ours = sorted(p for p in folder.glob(PREFIX + '*.db') if p.is_file() and not p.is_symlink())
    for old in ours[:-KEEP_LOCAL]:
        old.unlink()
    return target


def commit_snapshot(st, root, snapshot, at):
    """Replace the designated snapshot with a consistent copy and commit only that file."""
    repo = inside(root, snapshot['repository'])
    target = inside(root, snapshot['path'])
    top = Path(checked(git(repo, 'rev-parse', '--show-toplevel'), 'locating the snapshot repository')).resolve()
    if top != repo.resolve():
        raise RuntimeError('persistence.snapshot.repository is not the top of a git repository')
    try:
        relative = target.relative_to(top).as_posix()
    except ValueError:
        raise RuntimeError('persistence.snapshot.path is outside its repository')
    temporary = target.with_name('.' + target.name + '.precompact-tmp')
    if temporary.exists() and not temporary.is_symlink():
        temporary.unlink()
    st.backup(str(temporary))
    os.replace(temporary, target)
    result = {'path': relative, 'repository': snapshot['repository']}
    checked(git(repo, 'add', '--', relative), 'git add')
    if git(repo, 'diff', '--cached', '--quiet', '--', relative).returncode == 0:
        result['commit'] = 'unchanged'
    else:
        checked(git(repo, 'commit', '--only', '-m', 'coordinator snapshot before compaction ' + at, '--', relative),
                'git commit')
        result['commit'] = checked(git(repo, 'rev-parse', '--short', 'HEAD'), 'reading the commit')
    if snapshot.get('push') is True:
        upstream = git(repo, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}')
        if upstream.returncode != 0:
            raise RuntimeError('snapshot committed but not pushed: the branch has no upstream')
        outgoing = checked(git(repo, 'rev-list', '@{u}..HEAD'), 'listing outgoing commits').split()
        for sha in outgoing:
            files = checked(git(repo, 'diff-tree', '--no-commit-id', '--name-only', '-r', '--root', sha), 'reading ' + sha)
            if files.split() != [relative]:
                raise RuntimeError('snapshot committed but not pushed: outgoing commit ' + sha[:10]
                                   + ' touches more than the snapshot')
        if outgoing:
            checked(git(repo, 'push'), 'git push')
            result['pushed'] = len(outgoing)
        else:
            result['pushed'] = 0
    return result


def reset_throttle(root, session):
    path = root / '.coordinator' / 'guard-state.json'
    try:
        current = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if isinstance(current, dict) and session in current:
        current.pop(session)
        atomic_write(path, json.dumps(current).encode())


def resume_actions(snapshot):
    lanes = snapshot['active_lanes']
    actions = ['Re-read `coord.py summary` and the active handoff records ('
               + (', '.join(snapshot['active_handoffs']) or 'none besides this one') + ').']
    if lanes:
        actions.append('Active lanes keep their agents: ' + '; '.join(
            r['id'] + (' (agent ' + str(r['agent_id']) + ')' if r.get('agent_id') else '') for r in lanes)
            + '. They still report to this session; do not relaunch them.')
    if snapshot['presented_question']:
        actions.append('The presented question is still open: ' + ', '.join(r['id'] for r in snapshot['presented_question'])
                       + '. Correlate the next answer to its exact options.')
    if snapshot['active_holds']:
        actions.append('Honor active holds: ' + ', '.join(r['id'] for r in snapshot['active_holds']) + '.')
    actions.append('Continue the proactive cycle in this session. Never ask the user to open a new session.')
    return actions


def checkpoint(root, data):
    when, at = stamp()
    errors, done = [], {}
    st = Store(root)
    try:
        snapshot = state(st)
        record = {'title': 'Automatic pre-compaction checkpoint', 'status': 'active', 'type': 'checkpoint',
                  'generated_at': when, 'trigger': str(data.get('trigger') or 'unknown'),
                  'session_id': str(data.get('session_id') or ''),
                  'note': ('Written by the PreCompact hook from canonical state. Coordinator-written handoffs stay '
                           'authoritative for intent and resume steps; this is the mechanical snapshot.'),
                  **snapshot, 'resume': resume_actions(snapshot)}
        try:
            with st.transaction():
                st.put('handoff', RECORD, record)
                st.event('checkpoint', 'Pre-compaction checkpoint (' + record['trigger'] + ')', RECORD)
            done['handoff'] = RECORD
        except Exception as exc:  # noqa: BLE001 -- keep going: the backup is still worth taking
            errors.append('handoff: ' + str(exc)[:200])
        try:
            done['backup'] = local_backup(st, root, at)
        except Exception as exc:  # noqa: BLE001
            errors.append('local backup: ' + str(exc)[:200])
        try:
            target = profile_snapshot(st)
            if target:
                done['snapshot'] = commit_snapshot(st, root, target, at)
        except Exception as exc:  # noqa: BLE001
            errors.append('snapshot: ' + str(exc)[:200])
        try:
            # The record lands in the snapshot as written in step 1; outcomes are added afterwards.
            with st.transaction():
                st.put('handoff', RECORD, {'errors': list(errors), 'backup': done.get('backup'),
                                           'snapshot': done.get('snapshot')})
        except Exception as exc:  # noqa: BLE001
            errors.append('recording results: ' + str(exc)[:200])
    finally:
        st.close()
    try:
        reset_throttle(root, str(data.get('session_id') or 'session'))
    except Exception as exc:  # noqa: BLE001
        errors.append('guard throttle: ' + str(exc)[:200])
    return snapshot, done, errors


def instructions(root, snapshot, done, errors):
    lines = ['Coordinator checkpoint before compaction (coordinator-kit). This session is the coordinator and keeps '
             'working here after compaction; it never asks the user to open a new session. Canonical state is '
             + str(root / '.coordinator/coord.db') + '; handoff record ' + RECORD
             + (' was refreshed' if done.get('handoff') else ' could NOT be refreshed') + '.',
             'Keep in the summary:',
             '- the coordinator role and that work continues in this session through the proactive cycle;']
    if snapshot['active_handoffs']:
        lines.append('- active handoff records: ' + ', '.join(snapshot['active_handoffs']) + ';')
    for question in snapshot['presented_question']:
        lines.append('- presented question ' + question['id'] + ': ' + question['title'] + ';')
    if snapshot['active_lanes']:
        lines.append('- active lanes and their agents (they still report to this session): ' + '; '.join(
            r['id'] + ('=' + str(r['agent_id']) if r.get('agent_id') else '') for r in snapshot['active_lanes']) + ';')
    if snapshot['active_holds']:
        lines.append('- active holds: ' + ', '.join(r['id'] for r in snapshot['active_holds']) + ';')
    lines.append('- every founder instruction, answer or decision from this conversation that is not yet recorded in '
                 'the database, verbatim with its source, and agent results not yet reconciled into task records.')
    if done.get('snapshot'):
        lines.append('Snapshot ' + done['snapshot']['repository'] + '/' + done['snapshot']['path'] + ': commit ' + str(done['snapshot'].get('commit')) + '.')
    if errors:
        lines.append('Checkpoint steps that FAILED (finish them after compaction with coordinator-kit:stop-and-save '
                     'steps 4-5, no hold): ' + '; '.join(errors))
    return '\n'.join(lines)[:9500]


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get('agent_id'):
            return 0
        cwd = data.get('cwd')
        root = find_root(cwd) if isinstance(cwd, str) and os.path.isdir(cwd) else None
        if root is None or not enabled(root):
            return 0
        snapshot, done, errors = checkpoint(root, data)
        print(instructions(root, snapshot, done, errors))
    except Exception as exc:  # noqa: BLE001 -- never block compaction
        print('Coordinator checkpoint before compaction failed (' + type(exc).__name__ + ': ' + str(exc)[:200] + '). '
              'Keep in the summary that this session is the coordinator and continues here, and after compaction '
              'write the handoff record and backup with coordinator-kit:stop-and-save steps 4-5 (no hold).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
