#!/usr/bin/env python3
"""SessionStart hook: migrate established coordinator workspaces, expose canonical store."""
import json
from pathlib import Path
import sys

from migrate import ensure, workspace
from storage import VERSION


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
        context = ('Coordinator Kit ' + VERSION + ': canonical state is ' + result['database'] + '. '
                   'Use Python 3.9+ with script ' + cli + ' and --root ' + result['root'] + '. '
                   'Read the coordination-state skill at ' + skill + ' before coordinating. Run summary first, '
                   'then review list/show and reconcile all imported requirements, holds, questions, '
                   'profile and handoff into canonical records before dispatch. '
                   'Migration review sections: ' + str(result['migration_review_sections']) + '; unresolved records: '
                   + str(result['unresolved_records']) + '. Retired Markdown files are compatibility pointers; '
                   'do not resume writing STATE.md/plan.md/decision companions. No approvals or holds were inferred. '
                   'This storage migration supersedes old instructions to edit those retired files; '
                   'other instruction/risk constraints remain in force. Use database handoff/profile records on resume.')
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
