"""Portable coordinator storage. Python 3.9+ standard library; no product DB access."""
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

VERSION = '0.5.0'
SCHEMA = 1
KINDS = ('task', 'decision', 'question', 'lane', 'profile', 'handoff', 'guideline')
STATUSES = {
    'task': {'pending', 'in_progress', 'verifying', 'on_test', 'on_prod', 'blocked', 'done', 'dropped', 'needs_review'},
    'decision': {'active', 'superseded', 'needs_review'},
    'question': {'queued', 'presented', 'answered', 'parked', 'needs_review'},
    'lane': {'active', 'released', 'needs_review'},
    'profile': {'active'}, 'handoff': {'active', 'resolved'}, 'guideline': {'active', 'superseded'},
}
DEFAULT_STATUS = {k: ('pending' if k == 'task' else 'queued' if k == 'question' else 'active') for k in KINDS}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def actual_path(path):
    """Keep real directory spelling on case-insensitive POSIX filesystems as well as Windows."""
    path = Path(path).resolve()
    if path.parent == path:
        return path
    parent = actual_path(path.parent)
    candidate = parent / path.name
    if candidate.exists():
        for entry in parent.iterdir():
            if entry.name == path.name:
                return entry
        for entry in parent.iterdir():
            if entry.name.casefold() == path.name.casefold() and entry.samefile(candidate):
                return entry
    return candidate


def inside(root, path):
    """Reject symlinks and traversal, including a symlinked .coordinator directory."""
    root = Path(root).resolve()
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        relative = p.relative_to(root)
    except ValueError:
        raise ValueError('Path is outside the coordinator workspace')
    if '..' in relative.parts:
        raise ValueError('Parent traversal is not supported')
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlinked coordination sources/outputs are not supported: ' + str(relative))
    return p


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def workspace_lock(root, timeout=15):
    path = inside(root, '.coordinator/migrate.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Another coordinator migration holds the workspace lock; retry')
                time.sleep(0.1)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Store:
    def __init__(self, root, create=False):
        self.root = Path(root).resolve()
        self.path = inside(self.root, '.coordinator/coord.db')
        if not create and not self.path.is_file():
            raise ValueError('Coordinator database missing; run coord.py --root PATH ensure first')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=15)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA foreign_keys=ON')
        self.con.execute('PRAGMA busy_timeout=15000')
        version = self.con.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, SCHEMA):
            self.con.close()
            raise ValueError('Unsupported coordinator schema version; use a compatible plugin')
        existing = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if version == 0 and existing:
            self.con.close()
            raise ValueError('Unrecognized database at .coordinator/coord.db; refusing to overwrite')
        if version == 0:
            schema = Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
            self.con.executescript('BEGIN IMMEDIATE;\n' + schema + '\nPRAGMA user_version=1;\nCOMMIT;')
            self.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('plugin_version', VERSION))
            self.con.commit()
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    def close(self):
        self.con.close()

    @contextlib.contextmanager
    def transaction(self):
        self.con.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.con.commit()
        except BaseException:
            self.con.rollback()
            raise

    def event(self, kind, text, record_id=None, actor='coordinator', ref=None, source=None, key=None):
        if key:
            old = self.con.execute('SELECT * FROM events WHERE dedupe_key=?', (key,)).fetchone()
            if old:
                expected = (kind, text, record_id, actor, ref, source)
                actual = tuple(old[n] for n in ('kind', 'text', 'record_id', 'actor', 'ref', 'source'))
                if actual != expected:
                    raise ValueError('Event idempotency key already used for different content')
                return old['id']
        cur = self.con.execute('INSERT INTO events(at,kind,record_id,actor,text,ref,source,dedupe_key) VALUES (?,?,?,?,?,?,?,?)',
                               (now(), kind, record_id, actor, text, ref, source, key))
        return cur.lastrowid

    def get(self, key):
        r = self.con.execute('SELECT * FROM records WHERE id=?', (key,)).fetchone()
        if not r:
            raise ValueError('Unknown record: ' + key)
        item = dict(r)
        item['data'] = json.loads(item['data'])
        return item

    def put(self, kind, key, data, expected_version=None, imported=False):
        if kind not in KINDS or not isinstance(data, dict):
            raise ValueError('Invalid record kind or JSON object')
        old = self.con.execute('SELECT * FROM records WHERE id=?', (key,)).fetchone()
        if old and old['kind'] != kind:
            raise ValueError('Record id belongs to another kind')
        if expected_version is not None and (old['version'] if old else 0) != expected_version:
            raise ValueError('Record changed since read; refresh before updating')
        merged = json.loads(old['data']) if old else {}
        merged.update(data)
        title = merged.get('title')
        status = merged.setdefault('status', DEFAULT_STATUS[kind])
        if not isinstance(title, str) or not title.strip() or status not in STATUSES[kind]:
            raise ValueError('Record needs a nonempty title and valid status')
        if not imported and kind in ('task', 'decision', 'question') and not merged.get('source'):
            raise ValueError('Record requires original source/provenance')
        if not imported and kind == 'task' and status in ('in_progress', 'verifying', 'on_test', 'on_prod', 'done'):
            if not merged.get('acceptance'):
                raise ValueError('Active/completed task requires acceptance criteria')
        if kind == 'question' and status == 'presented' and not merged.get('options'):
            raise ValueError('Presented question requires the exact options/question contract')
        if not imported and kind == 'question' and status == 'answered' and not (merged.get('answer') and merged.get('answer_source')):
            raise ValueError('Answered question requires answer and answer_source')
        resource = None
        if kind == 'lane' and status == 'active':
            if not all(merged.get(n) for n in ('checkout', 'task', 'agent')):
                raise ValueError('Active lane requires checkout, task and agent')
            if self.get(merged['task'])['kind'] != 'task':
                raise ValueError('Lane task must reference a task')
            checkout = actual_path(self.root / merged['checkout'])
            if not checkout.is_dir():
                raise ValueError('Active lane checkout must be an existing directory')
            resource = os.path.normcase(str(checkout))
        self.con.execute('''INSERT INTO records(id,kind,title,status,data,resource,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,
          status=excluded.status,data=excluded.data,resource=excluded.resource,
          version=records.version+1,updated_at=excluded.updated_at''',
                         (key, kind, title, status, dumps(merged), resource, now(), now()))
        self.event('record_import' if imported else 'record_update', dumps(merged), key,
                   source=merged.get('source'))
        return self.get(key)

    def review_pending(self):
        return self.con.execute('SELECT count(*) FROM sections WHERE needs_review=1').fetchone()[0]

    def summary(self):
        pending = self.review_pending()
        files_pending = self.con.execute('SELECT count(*) FROM sources WHERE retired=0').fetchone()[0]
        unresolved = self.con.execute("SELECT count(*) FROM records WHERE status='needs_review'").fetchone()[0]
        counts = {r[0]: r[1] for r in self.con.execute("SELECT status,count(*) FROM records WHERE kind='task' GROUP BY status")}
        return {'database': str(self.path), 'schema_version': SCHEMA, 'plugin_version': VERSION,
                'migration_review_sections': pending, 'unretired_sources': files_pending,
                'unresolved_records': unresolved,
                'ready_for_dispatch': pending == 0 and files_pending == 0 and unresolved == 0,
                'task_counts': counts,
                'active_holds': [self.get(r[0]) for r in self.con.execute("SELECT id FROM records WHERE kind='decision' AND status='active'") if self.get(r[0])['data'].get('type') == 'hold'],
                'presented_question': [self.get(r[0]) for r in self.con.execute("SELECT id FROM records WHERE kind='question' AND status='presented'")],
                'active_lanes': [self.get(r[0]) for r in self.con.execute("SELECT id FROM records WHERE kind='lane' AND status='active'")]}

    def backup(self, target):
        target = inside(self.root, target)
        if target == self.path or target.exists():
            raise ValueError('Backup needs a new workspace-local path')
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(str(target))
        try:
            self.con.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed')
        finally:
            dest.close()
        if os.name != 'nt':
            os.chmod(target, 0o600)
        return str(target)
