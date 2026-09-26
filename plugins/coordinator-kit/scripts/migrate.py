"""Lossless first-run import with retryable filesystem cutover. Never infer approvals."""
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

from storage import Store, VERSION, actual_path, atomic_write, digest, dumps, inside, now, workspace_lock

MARKER = '<!-- coordinator-kit:database-pointer v1 -->'
NAMES = ('STATE.md', 'DECISIONS.md', 'DECISION-QUEUE.md', 'COORD.md',
         'operating-profile.md', 'repo-map.md', 'plan.md', 'objectives.md')


def pointer(source_id):
    return (MARKER + '\n# Coordination moved to SQLite\n\n'
            'The authoritative record is the workspace `.coordinator/coord.db`.\n'
            'Use the installed coordinator-kit `scripts/coord.py --root <workspace>` CLI.\n'
            'Start with `summary`; use `review list` before dispatch if migration needs review.\n'
            'Do not edit this retired file. Original bytes remain in the database and migration archive.\n'
            'Retrieve this source with `source show ' + source_id + '`.\n').encode('utf-8')


def roots(root):
    found = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if p.name.lower() == 'docs':
            found += [child for child in p.iterdir() if child.is_dir() and child.name.lower() == 'coordination']
        elif p.name.lower() in ('autopilot', 'coordination'):
            found.append(p)
    return found


def named_files(directory, names):
    """Enumerate actual spelling: Path('Docs') can exist as 'docs' on macOS/Windows."""
    if not directory.exists():
        return []
    wanted = {n.casefold() for n in names}
    return [p for p in directory.iterdir() if p.name.casefold() in wanted]


def detected(root):
    root = Path(root).resolve()
    # This repository's root STATE/CLAUDE files are distributable templates, not live state.
    if (root / 'plugins/coordinator-kit/.claude-plugin/plugin.json').is_file():
        return False
    if (root / '.coordinator/coord.db').is_file() or (root / '.coordinator/migration.json').is_file():
        return True
    if any(named_files(p, ('STATE.md', 'coord.db')) for p in roots(root)):
        return True
    claude = root / 'CLAUDE.md'
    if claude.is_file():
        text = claude.read_text(encoding='utf-8')
        return 'coordinator-kit' in text or ('Coordinator Instructions' in text and bool(named_files(root, ('STATE.md',))))
    return False


def workspace(cwd):
    """Use nearest established coordinator workspace when a session starts in a child repo."""
    p = Path(cwd).resolve()
    for candidate in (p, *p.parents):
        if detected(candidate):
            return candidate
        if candidate == Path.home():
            break
    return p


def discover(root, st):
    candidates = []
    for base in roots(root):
        candidates += named_files(base, (*NAMES, 'coord.db'))
        for archive in (p for p in base.iterdir() if p.is_dir() and p.name.casefold() == 'state-archive'):
            candidates += list(archive.rglob('*.md'))
    # Root files are considered only once this workspace is selected for coordination.
    candidates += named_files(root, NAMES)
    for docdir in (p for p in root.iterdir() if p.is_dir() and p.name.casefold() == 'docs'):
        candidates += named_files(docdir, ('plan.md', 'objectives.md'))
        for decision_dir in (p for p in docdir.iterdir() if p.is_dir() and p.name.casefold() == 'decisions'):
            candidates += list(decision_dir.rglob('*.md'))
    config = inside(root, '.coordinator/migration.json')
    if config.exists():
        data = json.loads(config.read_text(encoding='utf-8'))
        if not isinstance(data.get('sources', []), list):
            raise ValueError('migration.json sources must be a list of workspace-relative files')
        candidates += [inside(root, x) for x in data.get('sources', [])]
    seen, result = set(), []
    for candidate in sorted(set(candidates)):
        p = inside(root, candidate)
        if not p.exists():
            continue
        p = actual_path(p)
        if not p.is_file():
            raise ValueError('Migration source must be a regular file')
        stat = p.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        rel = p.relative_to(root).as_posix()
        if p.is_relative_to(actual_path(st.path.parent)):
            raise ValueError('Cannot import coordinator storage into itself')
        if p.suffix.lower() not in ('.md', '.db', '.sqlite', '.sqlite3'):
            raise ValueError('Only Markdown or SQLite coordination sources are supported')
        if p.suffix.lower() == '.md':
            content = p.read_bytes()
            prior = st.con.execute('SELECT id FROM sources WHERE path=?', (rel,)).fetchall()
            if any(content == pointer(r[0]) for r in prior):
                continue
        result.append(p)
    return result


def sections(text):
    """Partition every character, including preamble/comments, with no lossy summarization."""
    lines = text.splitlines(keepends=True)
    start, title = 0, 'Preamble'
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6} ', line):
            if i > start:
                yield title, start + 1, ''.join(lines[start:i])
            start, title = i, line.strip().lstrip('#').strip()
    if start < len(lines):
        yield title, start + 1, ''.join(lines[start:])


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def sqlite_snapshot(path, scratch):
    fd, temp = tempfile.mkstemp(prefix='legacy-', suffix='.db', dir=str(scratch))
    os.close(fd)
    source = dest = None
    try:
        source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)
        dest = sqlite3.connect(temp)
        source.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Legacy database integrity check failed')
        # A WAL source can copy its journal-mode header into the destination. Normalize the
        # snapshot so archiving this file does not require a discarded -wal/-shm companion.
        dest.execute('PRAGMA journal_mode=DELETE').fetchone()
        dest.close(); dest = None
        return Path(temp).read_bytes()
    finally:
        if source: source.close()
        if dest: dest.close()
        for suffix in ('', '-wal', '-shm', '-journal'):
            Path(temp + suffix).unlink(missing_ok=True)


def import_markdown(st, sid, path, content):
    text = content.decode('utf-8-sig')
    pieces = list(sections(text))
    if ''.join(x[2] for x in pieces) != text:
        raise ValueError('Markdown partition did not preserve content')
    historical = 'state-archive' in path.casefold() or Path(path).name.casefold() == 'coord.md'
    for index, (heading, line, body) in enumerate(pieces):
        # Preamble/comments are retained too. No free-form hold is silently interpreted as lifted.
        needs_review = int(bool(body.strip()) and not historical)
        section_id = sid + ':' + str(index)
        st.con.execute('INSERT INTO sections(id,source_id,heading,body,line,needs_review) VALUES (?,?,?,?,?,?)',
                       (section_id, sid, heading, body, line, needs_review))
        if historical:
            st.event('legacy_history', body, source=section_id, key='section:' + section_id)
    # Checklists are mechanically recognizable, but still need source reconciliation before work.
    if Path(path).name.lower() == 'plan.md':
        for i, line in enumerate(text.splitlines(), 1):
            m = re.match(r'^\s*[-*]\s+\[([ xX])\]\s+(.+)$', line)
            if m:
                key = 'legacy-' + sid + '-' + str(i)
                st.put('task', key, {'title': m[2], 'status': 'needs_review',
                       'legacy_checked': m[1].lower() == 'x', 'source': path + ':L' + str(i),
                       'source_id': sid, 'source_text': line}, imported=True)


def import_sqlite(st, sid, path, archive):
    """Preserve the entire DB and searchable tables; normalize supported legacy record kinds."""
    con = sqlite3.connect(archive.as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            # FTS shadow tables are backed by source content and already retained in the DB snapshot.
            if table == 'fts' or table.startswith('fts_'):
                continue
            rows = [dict(r) for r in con.execute('SELECT * FROM ' + quoted(table))]
            body = json.dumps(rows, ensure_ascii=False, default=lambda b: {'hex': b.hex()})
            section_id = sid + ':' + table
            st.con.execute('INSERT INTO sections(id,source_id,heading,body,line,needs_review) VALUES (?,?,?,?,0,1)',
                           (section_id, sid, table, body))
            kind = {'tasks': 'task', 'decisions': 'decision', 'questions': 'question', 'guidelines': 'guideline'}.get(table)
            if not kind:
                continue
            for n, row in enumerate(rows):
                key = 'legacy-' + sid + '-' + table + '-' + str(n)
                title = row.get('title') or row.get('text') or row.get('rule') or row.get('key') or key
                data = {'title': str(title), 'source': path + ':' + table + ':' + str(row.get('id', n)),
                        'source_id': sid, 'legacy': json.loads(json.dumps(row, default=lambda b: {'hex': b.hex()})),
                        'status': 'active' if kind == 'guideline' else 'needs_review'}
                st.put(kind, key, data, imported=True)
        st.con.execute('INSERT INTO sections(id,source_id,heading,body,line,needs_review) VALUES (?,?,?,?,0,1)',
                       (sid + ':integration', sid, 'Retire legacy database writers',
                        'Repoint existing coordinator/bridge integrations to the bundled CLI. The original '
                        'database is preserved untouched as a legacy snapshot source, not a live second backlog.'))
    finally:
        con.close()


def publish_pointer(path, content):
    """Publish without replacing a file recreated by an older writer after displacement."""
    fd, temp = tempfile.mkstemp(prefix='.coord-pointer-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def displaced_files(st, row):
    archive = inside(st.root, row['archive_path'])
    if not archive.parent.is_dir():
        return []
    return [inside(st.root, p) for p in archive.parent.iterdir()
            if p.name.startswith(archive.name + '.displaced-')]


def recover_displaced(st):
    """Keep old open file descriptors recoverable, even if they write after cutover."""
    recovered = []
    for row in st.con.execute("SELECT * FROM sources WHERE format='markdown'").fetchall():
        for p in displaced_files(st, row):
            content = p.read_bytes()
            sha = digest(content)
            rel = p.relative_to(st.root).as_posix()
            if sha == row['sha256'] or st.con.execute(
                    'SELECT 1 FROM sources WHERE path=? AND sha256=?', (rel, sha)).fetchone():
                continue
            recovered.append((rel, 'markdown', content, sha))
    import_batch(st, recovered, recovered=True)
    return len(recovered)


def retire(st):
    """DB import commits first. Each pointer replacement can then be retried after any crash."""
    for row in st.con.execute('SELECT * FROM sources WHERE retired=0 ORDER BY imported_at,id').fetchall():
        p = inside(st.root, row['path'])
        archive = inside(st.root, row['archive_path'])
        if not archive.is_file() or digest(archive.read_bytes()) != row['sha256']:
            raise ValueError('Migration archive missing/corrupt; source files were not retired')
        if digest(row['content']) != row['sha256']:
            raise ValueError('Database source verification failed; refusing cutover')
        if row['format'] == 'markdown':
            current = p.read_bytes() if p.exists() else None
            if current != pointer(row['id']):
                if current is not None and digest(current) != row['sha256']:
                    # A subsequent session can import that revision; do not discard a concurrent write.
                    raise ValueError('Legacy source changed during migration: ' + row['path'] + '; rerun ensure')
                if current is not None:
                    # Retain this inode permanently. A late write before the rename, or through
                    # an already open descriptor afterwards, remains recoverable. Never unlink
                    # it: atomic replacement of the original alone would lose those writes.
                    displaced = inside(st.root, str(archive) + '.displaced-' + uuid.uuid4().hex)
                    os.replace(p, displaced)
                elif not displaced_files(st, row):
                    raise ValueError('Legacy source missing before cutover: ' + row['path'])
                try:
                    publish_pointer(p, pointer(row['id']))
                except FileExistsError:
                    if p.read_bytes() != pointer(row['id']):
                        raise ValueError('Legacy source recreated during migration: ' + row['path'] + '; rerun ensure')
        else:
            # Never rename/delete a database that an external integration might still have open.
            atomic_write(inside(st.root, str(p) + '.MIGRATED.md'), pointer(row['id']))
        with st.transaction():
            st.con.execute('UPDATE sources SET retired=1 WHERE id=?', (row['id'],))
    with st.transaction():
        st.con.execute("UPDATE migrations SET state='complete',completed_at=? WHERE state='imported' AND NOT EXISTS (SELECT 1 FROM sources WHERE migration_id=migrations.id AND retired=0)", (now(),))


def import_batch(st, pending, recovered=False):
    if not pending:
        return
    mid = now().replace(':', '-') + '-' + uuid.uuid4().hex[:8]
    with st.transaction():
        st.con.execute("INSERT INTO migrations(id,started_at,state) VALUES (?,?,'imported')", (mid, now()))
        for rel, fmt, content, sha in pending:
            sid = digest((rel + '\n' + sha).encode())[:20]
            # Recovered inodes already live below a migration archive. Avoid recursively
            # nesting that path inside future archives; source.path retains the full origin.
            archive_rel = '.coordinator/migrations/' + mid + '/' + (sid + '.md' if recovered else rel)
            archive = inside(st.root, archive_rel)
            atomic_write(archive, content)
            if archive.read_bytes() != content:
                raise ValueError('Archive verification failed')
            st.con.execute('INSERT INTO sources(id,migration_id,path,sha256,format,content,archive_path,imported_at,retired) VALUES (?,?,?,?,?,?,?,?,?)',
                           (sid, mid, rel, sha, fmt, content, archive_rel, now(), int(recovered)))
            if fmt == 'markdown':
                import_markdown(st, sid, rel, content)
            else:
                import_sqlite(st, sid, rel, archive)
            # Older source revisions remain searchable; newest revision owns pointer cutover.
            st.con.execute('UPDATE sources SET retired=1 WHERE path=? AND id<>?', (rel, sid))
        st.event('migration_recovery' if recovered else 'migration_import',
                 'Preserved and imported ' + str(len(pending)) + ' sources', source=mid)


def ensure(root, initialize=False):
    root = Path(root).resolve()
    if not initialize and not detected(root):
        return {'detected': False, 'root': str(root)}
    with workspace_lock(root):
        st = Store(root, create=True)
        try:
            recovered = recover_displaced(st)
            pending = []
            for p in discover(root, st):
                rel = p.relative_to(root).as_posix()
                fmt = 'markdown' if p.suffix.lower() == '.md' else 'sqlite'
                content = p.read_bytes() if fmt == 'markdown' else sqlite_snapshot(p, st.path.parent)
                sha = digest(content)
                if st.con.execute('SELECT 1 FROM sources WHERE path=? AND sha256=?', (rel, sha)).fetchone():
                    continue
                pending.append((rel, fmt, content, sha))
            import_batch(st, pending)
            if st.con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Coordinator database failed integrity check')
            retire(st)
            recovered += recover_displaced(st)
            with st.transaction():
                st.con.execute("UPDATE migrations SET state='complete',completed_at=? WHERE state='imported' AND NOT EXISTS (SELECT 1 FROM sources WHERE migration_id=migrations.id AND retired=0)", (now(),))
                st.con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', ('plugin_version', VERSION))
            result = st.summary()
            result.update(detected=True, imported_sources=len(pending) + recovered, root=str(root))
            return result
        finally:
            st.close()
