#!/usr/bin/env python3
"""SessionStart hook: migrate established coordinator workspaces, expose canonical store.

After a compaction (`source: compact`) it re-orients the same session instead: the coordinator
re-reads canonical state and the pre-compaction checkpoint and keeps working here.
"""
import json
from pathlib import Path
import sys

from migrate import ensure, workspace
from storage import VERSION, Store

CHECKPOINT = 'handoff-auto-checkpoint'


def checkpoint_note(root):
    """One line about the PreCompact checkpoint record, read-only; empty when there is none."""
    try:
        st = Store(root, read_only=True)
    except Exception:  # noqa: BLE001 -- the reminder below still applies without it
        return ''
    try:
        row = st.con.execute("SELECT data FROM records WHERE id=? AND kind='handoff'", (CHECKPOINT,)).fetchone()
    finally:
        st.close()
    if not row:
        return ' No pre-compaction checkpoint record was found; write the handoff record and backup now.'
    data = json.loads(row[0])
    note = ' The pre-compaction checkpoint ' + CHECKPOINT + ' was written at ' + str(data.get('generated_at')) + '.'
    if data.get('errors'):
        note += (' Its steps that failed, to finish now with coordinator-kit:stop-and-save steps 4-5 (no hold): '
                 + '; '.join(map(str, data['errors']))[:600] + '.')
    return note


def compacted(result, cli, cycle):
    return ('Coordinator Kit ' + VERSION + ': context was compacted; this session keeps coordinating. '
            'Canonical state is ' + result['database'] + ' (script ' + cli + ', --root ' + result['root'] + ').'
            + checkpoint_note(result['root']) + ' Re-read `summary` (presented question, active holds, '
            'commitments, active lanes), the active handoff records and the proactive cycle at ' + cycle + '. '
            'Agents launched before compaction still report to this session: keep their lanes and do not relaunch '
            'them. Then continue the proactive cycle: ask the presented or next pending question and fill free lanes '
            'with authorized work. Do not tell the user to start a new session.')


def main():
    try:
        data = json.load(sys.stdin)
        if data.get('agent_id'):
            return 0
        cwd = data.get('cwd')
        if not isinstance(cwd, str) or not Path(cwd).is_dir():
            raise ValueError('SessionStart requires an existing cwd')
        result = ensure(workspace(cwd))
        if not result.get('detected'):
            return 0
        cli = str(Path(__file__).with_name('coord.py').resolve())
        skill = str(Path(__file__).resolve().parents[1] / 'skills/coordination-state/SKILL.md')
        cycle = str(Path(__file__).resolve().parents[1] / 'references/proactive-cycle.md')
        if data.get('source') == 'compact':
            context = compacted(result, cli, cycle)
        else:
            context = ('Coordinator Kit ' + VERSION + ': canonical state is ' + result['database'] + '. '
                       'Use Python 3.9+ with script ' + cli + ' and --root ' + result['root'] + '. '
                       'Read the coordination-state skill at ' + skill + ' before coordinating. Run summary first, '
                       'then review list/show and reconcile all imported requirements, holds, questions, '
                       'profile and handoff into canonical records before dispatch. '
                       'Migration review sections: ' + str(result['migration_review_sections']) + '; unresolved records: '
                       + str(result['unresolved_records']) + '. Retired Markdown files are compatibility pointers; '
                       'do not resume writing STATE.md/plan.md/decision companions. No approvals or holds were inferred. '
                       'This storage migration supersedes old instructions to edit those retired files; '
                       'other instruction/risk constraints remain in force. Use database handoff/profile records on resume. '
                       'After reconciliation, read the required coordinator cycle at ' + cycle + ': '
                       'actually ask the next pending question and dispatch eligible authorized work when capacity opens; '
                       'do not end at a status summary. Honor explicit stops and recorded holds.')
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
    except Exception as exc:
        # SessionStart is context-only: report failure; never pretend this mechanically blocks tools.
        message = ('Coordinator database migration did not complete: ' + str(exc) + '. '
                   'Do not dispatch coordination work until coordinator-kit:bootstrap repairs and reruns ensure. '
                   'Original content remains preserved; do not overwrite files to bypass this failure.')
        print(json.dumps({'systemMessage': message, 'hookSpecificOutput': {
            'hookEventName': 'SessionStart', 'additionalContext': message}}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
