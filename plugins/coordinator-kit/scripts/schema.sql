PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS migrations (
  id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
  state TEXT NOT NULL CHECK(state IN ('imported','complete'))
);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, migration_id TEXT NOT NULL REFERENCES migrations(id),
  path TEXT NOT NULL, sha256 TEXT NOT NULL, format TEXT NOT NULL,
  content BLOB NOT NULL, archive_path TEXT NOT NULL, imported_at TEXT NOT NULL,
  retired INTEGER NOT NULL DEFAULT 0, UNIQUE(path, sha256)
);
CREATE TABLE IF NOT EXISTS sections (
  id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
  heading TEXT NOT NULL, body TEXT NOT NULL, line INTEGER NOT NULL,
  needs_review INTEGER NOT NULL CHECK(needs_review IN (0,1)),
  resolution TEXT, refs TEXT, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN
    ('task','decision','question','lane','profile','handoff','guideline')),
  title TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
  resource TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_kind ON records(kind,status);
CREATE UNIQUE INDEX IF NOT EXISTS one_presented_question ON records(kind)
  WHERE kind='question' AND status='presented';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_lane ON records(resource)
  WHERE kind='lane' AND status='active';
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL,
  record_id TEXT REFERENCES records(id), actor TEXT NOT NULL, text TEXT NOT NULL,
  ref TEXT, source TEXT, dedupe_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS events_record ON events(record_id,id);
