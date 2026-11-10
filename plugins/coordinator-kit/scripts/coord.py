#!/usr/bin/env python3
"""Bundled coordinator CLI. Run with --help. JSON inputs are merged transactionally."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

from storage import KINDS, Store, atomic_write, digest, dumps, inside, now
from migrate import ensure
from operations import status_view, sweep
import discipline
import idle


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.', help='Coordinator workspace root (not necessarily a Git repo)')
    p.add_argument('--actor', choices=('coordinator', 'agent'), default='coordinator')
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('ensure', help='Migrate legacy coordination on first run; retry interrupted cutover')
    init.add_argument('--init', action='store_true', help='Explicitly initialize a new/nonstandard coordinator workspace')
    for kind in KINDS:
        group = sub.add_parser(kind).add_subparsers(dest='operation', required=True)
        put = group.add_parser('put', help='Create/merge JSON record; source and status are preserved unless supplied')
        put.add_argument('id')
        data = put.add_mutually_exclusive_group(required=True)
        data.add_argument('--json', help='JSON object; use --data for longer/quoted text')
        data.add_argument('--data', help='JSON file inside workspace, or - for stdin')
        put.add_argument('--if-version', type=int)
        get = group.add_parser('show'); get.add_argument('id')
        listing = group.add_parser('list'); listing.add_argument('--status'); listing.add_argument('--open', action='store_true')
        if kind == 'decision':
            supersede = group.add_parser('supersede')
            supersede.add_argument('old_id'); supersede.add_argument('new_id')
            supersede.add_argument('--data', required=True, help='New sourced decision as JSON file or -')
    event = sub.add_parser('event').add_subparsers(dest='operation', required=True)
    add = event.add_parser('add'); add.add_argument('text'); add.add_argument('--kind', default='note')
    add.add_argument('--record'); add.add_argument('--ref'); add.add_argument('--source'); add.add_argument('--key')
    listing = event.add_parser('list'); listing.add_argument('--record'); listing.add_argument('--limit', type=int, default=30)
    sub.add_parser('summary'); sub.add_parser('check')
    status = sub.add_parser('status', help='Compact operational view; does not send a notification')
    status.add_argument('--limit', type=int, default=3, help='Maximum tasks per displayed group (1-20)')
    scan = sub.add_parser('sweep', help='Read-only reminders for missed questions, releases and stale work')
    scan.add_argument('--stale-hours', type=float, default=6)
    scan.add_argument('--available-slots', type=slots_value,
                      help="Freshly checked worker capacity, or 'auto' for the idle-lane picks and FREE-SLOTS of `idle`; omit if unknown")
    scan.add_argument('--now', help='Timezone-aware ISO timestamp for offline replay; defaults to the real clock')
    scan.add_argument('--check-idle', action='store_true', help='Exit 2 when recorded follow-up actions remain; still emit JSON')
    lanes = sub.add_parser('idle', help='Idle work lanes, one ranked pick each, and FREE-SLOTS; block/unblock a lane with its reason')
    lanes.add_argument('operation', nargs='?', choices=('show', 'block', 'unblock'), default='show')
    lanes.add_argument('lane', nargs='?', help="Work lane name, 'unassigned', or '*' for every lane (block/unblock)")
    lanes.add_argument('--reason', help='Concrete blocker: dependency, user decision, access, hold or capacity')
    lanes.add_argument('--hours', type=float, help='Blocker lifetime (default: profile capacity.blocker_hours or 4)')
    lanes.add_argument('--max-agents', type=int, help='Override profile capacity.max_agents')
    lanes.add_argument('--mem-free-pct', type=int, help='Use this free-memory reading instead of the host (replay/tests)')
    lanes.add_argument('--now', help='Timezone-aware ISO timestamp for offline replay; defaults to the real clock')
    lanes.add_argument('--lines', action='store_true', help='Print only the IDLE-LANES lines, and only when action is required (watch checks)')
    lanes.add_argument('--check', action='store_true', help='Exit 2 when a pick should be dispatched now or the lane hook is failing')
    search = sub.add_parser('search'); search.add_argument('query'); search.add_argument('--limit', type=int, default=30)
    review = sub.add_parser('review').add_subparsers(dest='operation', required=True)
    review.add_parser('list')
    show = review.add_parser('show'); show.add_argument('id')
    resolve = review.add_parser('resolve'); resolve.add_argument('id'); resolve.add_argument('--note', required=True)
    mode = resolve.add_mutually_exclusive_group(required=True)
    mode.add_argument('--refs', nargs='+', help='Canonical record ids that preserve actionable content')
    mode.add_argument('--historical', action='store_true', help='Explicitly reviewed as history/no remaining action')
    verify = sub.add_parser('verify', help='Count verify cycles per task; refuse a cycle past the cap without an answered escalation'
                            ).add_subparsers(dest='operation', required=True)
    for name in ('status', 'start', 'fail', 'pass', 'clear'):
        item = verify.add_parser(name); item.add_argument('task')
        if name in ('fail', 'pass'):
            item.add_argument('--note', required=True); item.add_argument('--ref', help='Report/evidence path')
        if name == 'pass':
            item.add_argument('--target', required=True, help='Environment the verdict covers, e.g. staging or release')
        if name == 'clear':
            item.add_argument('--question', required=True, help='Answered verify_escalation question id')
    promise = sub.add_parser('commitment', help='Commitments the coordinator stated to the user; shown until closed'
                             ).add_subparsers(dest='operation', required=True)
    promise.add_parser('list')
    item = promise.add_parser('add'); item.add_argument('id'); item.add_argument('--text', required=True)
    item.add_argument('--channel', required=True); item.add_argument('--source', required=True, help='Id/time of the message that stated it')
    item = promise.add_parser('withdraw'); item.add_argument('id'); item.add_argument('--channel', required=True)
    item.add_argument('--source', required=True, help='Id/time of the withdrawing message'); item.add_argument('--reason', required=True)
    item = promise.add_parser('fulfil'); item.add_argument('id'); item.add_argument('--evidence', required=True)
    slots = sub.add_parser('slot', help='Assign shared sequential numbers (migration slots, ports) at dispatch'
                           ).add_subparsers(dest='operation', required=True)
    item = slots.add_parser('claim'); item.add_argument('series'); item.add_argument('--task', required=True)
    item.add_argument('--first', type=int, help='First free value (required for the first claim; raises the floor later)')
    item.add_argument('--another', action='store_true', help='Claim an additional slot for a task that already holds one')
    item = slots.add_parser('list'); item.add_argument('series')
    contract = sub.add_parser('brief-contract', help='Print the execution contract to paste into every agent brief')
    contract.add_argument('--scratch', required=True, help='Task-owned directory under .coordinator-scratch/')
    contract.add_argument('--task', help='Task id: adds the `Task:` marker line the autolane hook links by')
    contract.add_argument('--lane', help='Work lane: adds the `Lane:` marker line')
    contract.add_argument('--checkout', help='Workspace-relative checkout the agent works in: adds `Checkout:`')
    contract.add_argument('--steps', type=int, default=80); contract.add_argument('--context', type=int, default=200, help='Thousand tokens')
    source = sub.add_parser('source').add_subparsers(dest='operation', required=True)
    source.add_parser('list')
    show = source.add_parser('show'); show.add_argument('id'); show.add_argument('--output')
    backup = sub.add_parser('backup'); backup.add_argument('output')
    render = sub.add_parser('render'); render.add_argument('--output')
    return p


def slots_value(value):
    if value == 'auto':
        return value
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a number of slots or 'auto'")


def read_data(st, filename):
    raw = sys.stdin.read() if filename == '-' else inside(st.root, filename).read_text(encoding='utf-8')
    return json.loads(raw)


def render(st):
    status = st.summary()
    lines = ['# Coordinator database view', '', 'Generated ' + now() + '; read-only view of .coordinator/coord.db.',
             '', 'Migration review sections: ' + str(status['migration_review_sections']),
             'Unresolved records: ' + str(status['unresolved_records']), '']
    for kind in KINDS:
        rows = st.con.execute('SELECT id,title,status FROM records WHERE kind=? ORDER BY updated_at DESC,id', (kind,)).fetchall()
        if rows:
            lines += ['## ' + kind.title(), '']
            lines += ['- ' + r['id'] + ' [' + r['status'] + '] ' + ' '.join(r['title'].split()) for r in rows]
            lines.append('')
    return '\n'.join(lines) + '\n'


def execute(st, a):
    cmd, op = a.command, getattr(a, 'operation', None)
    if a.actor == 'agent' and not (cmd in ('summary', 'status', 'sweep', 'check', 'search') or
            (cmd == 'idle' and op == 'show') or
            (cmd in KINDS and op in ('show', 'list')) or (cmd in ('review', 'source') and op in ('show', 'list')) or cmd == 'event' or
            (cmd == 'verify' and op == 'status') or (cmd in ('commitment', 'slot') and op == 'list')):
        raise ValueError('Agent mode permits reads and append-only events, not coordination transitions')
    if cmd in KINDS:
        if op == 'put':
            data = json.loads(a.json) if a.json is not None else read_data(st, a.data)
            with st.transaction():
                return st.put(cmd, a.id, data, a.if_version)
        if op == 'show':
            result = st.get(a.id)
            if result['kind'] != cmd:
                raise ValueError('Record belongs to another kind')
            return result
        if op == 'supersede':
            data = read_data(st, a.data)
            with st.transaction():
                old = st.get(a.old_id)
                if old['kind'] != 'decision' or old['status'] == 'superseded' or a.new_id == a.old_id:
                    raise ValueError('Decision is not available to supersede')
                if st.con.execute('SELECT 1 FROM records WHERE id=?', (a.new_id,)).fetchone():
                    raise ValueError('Superseding decision id already exists')
                data['supersedes'] = a.old_id
                result = st.put('decision', a.new_id, data)
                st.put('decision', a.old_id, {'status': 'superseded', 'superseded_by': a.new_id})
                return result
        sql, params = 'SELECT id FROM records WHERE kind=?', [cmd]
        if a.status: sql += ' AND status=?'; params.append(a.status)
        if a.open: sql += " AND status NOT IN ('done','dropped','superseded','answered','parked','released','resolved')"
        return [st.get(r[0]) for r in st.con.execute(sql + ' ORDER BY updated_at DESC,id', params)]
    if cmd == 'event':
        if op == 'add':
            if a.actor == 'agent' and (not a.record or st.get(a.record)['kind'] != 'task'):
                raise ValueError('Agent event must reference an assigned task')
            with st.transaction():
                return {'id': st.event(a.kind, a.text, a.record, a.actor, a.ref, a.source, a.key)}
        sql, params = 'SELECT * FROM events', []
        if a.record: sql += ' WHERE record_id=?'; params.append(a.record)
        params.append(max(1, min(a.limit, 1000)))
        return [dict(r) for r in st.con.execute(sql + ' ORDER BY id DESC LIMIT ?', params)]
    if cmd in ('verify', 'commitment', 'slot'):
        handler = getattr(discipline, cmd)
        if op in ('status', 'start', 'list'):
            return handler(st, a)
        with st.transaction():
            return handler(st, a)
    if cmd == 'summary':
        return st.summary()
    if cmd == 'idle' and op != 'show':
        if not a.lane:
            raise ValueError('idle ' + op + ' needs the lane name')
        with st.transaction():
            return idle.block(st, a.lane, a.reason, a.hours, a.actor, clear=op == 'unblock')
    if cmd in ('status', 'sweep', 'idle'):
        st.con.execute('BEGIN')
        try:
            if cmd == 'status':
                return status_view(st, a.limit)
            if cmd == 'idle':
                return idle.idle_view(st, a.now, a.max_agents, False if a.mem_free_pct is None else a.mem_free_pct)
            if a.available_slots == 'auto':
                view = idle.idle_view(st, a.now)
                return sweep(st, a.now, a.stale_hours, view['free_slots'], capacity=view)
            return sweep(st, a.now, a.stale_hours, a.available_slots)
        finally:
            st.con.rollback()
    if cmd == 'search':
        term = '%' + a.query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        limit = max(1, min(a.limit, 1000))
        found = []
        for table, column in (('records', 'data'), ('sections', 'body'), ('events', 'text')):
            for r in st.con.execute('SELECT * FROM ' + table + ' WHERE ' + column + " LIKE ? ESCAPE '\\' LIMIT ?", (term, limit)):
                found.append({'table': table, 'id': r['id'], 'excerpt': r[column][:500]})
        return found
    if cmd == 'review':
        if op == 'list':
            return [dict(r) for r in st.con.execute('''SELECT sections.id,path,heading,line FROM sections
                JOIN sources ON source_id=sources.id WHERE needs_review=1 ORDER BY path,line''')]
        row = st.con.execute('SELECT * FROM sections WHERE id=?', (a.id,)).fetchone()
        if not row: raise ValueError('Unknown migration review section')
        if op == 'show': return dict(row)
        with st.transaction():
            for ref in a.refs or []: st.get(ref)
            if not a.note.strip(): raise ValueError('Review resolution must explain how content was reconciled')
            st.con.execute('UPDATE sections SET needs_review=0,resolution=?,refs=?,reviewed_at=? WHERE id=?',
                           (a.note, dumps(a.refs or []), now(), a.id))
            st.event('migration_review', a.note, source=a.id)
        return {'resolved': a.id}
    if cmd == 'source':
        if op == 'list':
            return [dict(r) for r in st.con.execute('SELECT id,path,sha256,format,archive_path,retired FROM sources ORDER BY imported_at,path')]
        row = st.con.execute('SELECT * FROM sources WHERE id=?', (a.id,)).fetchone()
        if not row: raise ValueError('Unknown source')
        if a.output:
            out = inside(st.root, a.output)
            if out.exists(): raise ValueError('Source extraction refuses to overwrite an existing path')
            atomic_write(out, row['content'])
            return {'output': str(out), 'sha256': row['sha256']}
        if row['format'] != 'markdown':
            raise ValueError('Use --output NEW_PATH to extract a binary source snapshot')
        return {'path': row['path'], 'content': row['content'].decode('utf-8-sig')}
    if cmd == 'check':
        errors = []
        if st.con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': errors.append('integrity_check')
        if st.con.execute('PRAGMA foreign_key_check').fetchall(): errors.append('foreign_key_check')
        for r in st.con.execute('SELECT id,content,sha256,archive_path FROM sources'):
            archive = inside(st.root, r['archive_path'])
            if digest(r['content']) != r['sha256'] or not archive.is_file() or digest(archive.read_bytes()) != r['sha256']:
                errors.append(r['id'])
        if errors: raise ValueError('Integrity failures: ' + ', '.join(errors))
        return {'ok': True}
    if cmd == 'backup': return {'backup': st.backup(a.output)}
    if cmd == 'render':
        st.con.execute('BEGIN')
        try: body = render(st)
        finally: st.con.rollback()
        if a.output:
            out = inside(st.root, a.output)
            # Views cannot overwrite source files, storage, or instruction files.
            if not out.is_relative_to(st.root / '.coordinator/reports'):
                raise ValueError('Rendered files belong under .coordinator/reports/')
            atomic_write(out, body.encode())
            return {'output': str(out)}
        return body
    raise ValueError('Unsupported command')


def main(argv=None):
    a = parser().parse_args(argv)
    st = None
    try:
        if a.command == 'ensure':
            if a.actor != 'coordinator': raise ValueError('Only coordinator mode may migrate')
            result = ensure(a.root, a.init)
        elif a.command == 'brief-contract':
            result = discipline.brief_contract(a.scratch, a.steps, a.context, a.task, a.lane, a.checkout)
        else:
            op = getattr(a, 'operation', None)
            writes_db = ((a.command in KINDS and op in ('put', 'supersede')) or
                         (a.command == 'event' and op == 'add') or
                         (a.command == 'review' and op == 'resolve') or
                         (a.command == 'verify' and op in ('fail', 'pass', 'clear')) or
                         (a.command == 'commitment' and op in ('add', 'withdraw', 'fulfil')) or
                         (a.command == 'slot' and op == 'claim') or
                         (a.command == 'idle' and op in ('block', 'unblock')))
            st = Store(a.root, read_only=not writes_db)
            result = execute(st, a)
        if a.command == 'idle' and getattr(a, 'lines', False) and isinstance(result, dict) and 'lines' in result:
            if result['action_required']:
                print('\n'.join(result['lines']))
        else:
            print(result if isinstance(result, str) else dumps(result))
        if a.command == 'sweep' and a.check_idle and not result['idle_ready']:
            return 2
        if a.command == 'idle' and a.check and isinstance(result, dict) and result.get('action_required'):
            return 2
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        print('coord: ' + str(exc), file=sys.stderr)
        return 1
    finally:
        if st: st.close()


if __name__ == '__main__':
    sys.exit(main())
