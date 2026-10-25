import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','member')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS device_groups (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, parent_id INTEGER REFERENCES device_groups(id),
    scope TEXT NOT NULL CHECK(scope IN ('internal','external'))
);
CREATE UNIQUE INDEX IF NOT EXISTS group_sibling_name
    ON device_groups(COALESCE(parent_id,0),name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    group_id INTEGER NOT NULL REFERENCES device_groups(id),
    asset_no TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    secret_hash TEXT NOT NULL, last_seen INTEGER
);
CREATE TABLE IF NOT EXISTS grants (
    user_id INTEGER NOT NULL REFERENCES users(id),
    group_id INTEGER NOT NULL REFERENCES device_groups(id),
    permissions TEXT NOT NULL, expires_at INTEGER,
    PRIMARY KEY(user_id,group_id)
);
CREATE TABLE IF NOT EXISTS device_shares (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id),
    grantor_id INTEGER NOT NULL REFERENCES users(id),
    recipient_id INTEGER NOT NULL REFERENCES users(id),
    permissions TEXT NOT NULL, expires_at INTEGER,
    UNIQUE(device_id,grantor_id,recipient_id)
);
CREATE INDEX IF NOT EXISTS device_share_recipient ON device_shares(recipient_id,device_id);
CREATE TABLE IF NOT EXISTS tickets (
    token_hash TEXT PRIMARY KEY, session_hash TEXT NOT NULL REFERENCES sessions(token_hash),
    device_id TEXT NOT NULL REFERENCES devices(id), controller_id TEXT NOT NULL,
    action TEXT NOT NULL, challenge TEXT NOT NULL, expires_at INTEGER NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS login_attempts (
    key TEXT NOT NULL, time INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS login_attempt_key_time ON login_attempts(key,time);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY, time INTEGER NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, target TEXT NOT NULL, detail TEXT NOT NULL
);
PRAGMA user_version=2;
"""


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("RDM_DATABASE", "data/management.sqlite3")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(f"Unsupported database schema {version}; restore a compatible release")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
