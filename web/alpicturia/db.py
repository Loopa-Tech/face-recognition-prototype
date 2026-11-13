import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('attendee','photographer','admin')),verified INTEGER NOT NULL DEFAULT 0,disabled INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,last_seen REAL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tokens(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS api_keys(id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,scopes TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,slug TEXT UNIQUE NOT NULL,title TEXT NOT NULL,location TEXT NOT NULL,date TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',published INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS assignments(event_id TEXT REFERENCES events(id) ON DELETE CASCADE,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,PRIMARY KEY(event_id,user_id));
CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY,event_id TEXT REFERENCES events(id) ON DELETE CASCADE,owner_id TEXT REFERENCES users(id) ON DELETE CASCADE,filename TEXT NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,path TEXT NOT NULL,preview TEXT,status TEXT NOT NULL DEFAULT 'queued',error TEXT,face_count INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL,UNIQUE(event_id,owner_id,sha256));
CREATE TABLE IF NOT EXISTS faces(id INTEGER PRIMARY KEY,photo_id TEXT REFERENCES photos(id) ON DELETE CASCADE,encoding TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS searches(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,event_id TEXT REFERENCES events(id) ON DELETE CASCADE,consent_version TEXT NOT NULL,consented REAL NOT NULL,status TEXT NOT NULL DEFAULT 'queued',path TEXT,error TEXT,expires REAL NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS matches(search_id TEXT REFERENCES searches(id) ON DELETE CASCADE,photo_id TEXT REFERENCES photos(id) ON DELETE CASCADE,distance REAL NOT NULL,PRIMARY KEY(search_id,photo_id));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,ref_id TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,available REAL NOT NULL,lease_until REAL,error TEXT,created REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(kind,ref_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS mail(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id) ON DELETE CASCADE,recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,available REAL NOT NULL,error TEXT,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor_id TEXT,action TEXT NOT NULL,target TEXT,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS metrics(id INTEGER PRIMARY KEY,event TEXT NOT NULL,path TEXT,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rate_limits(key TEXT PRIMARY KEY,hits INTEGER NOT NULL,expires REAL NOT NULL);
CREATE INDEX IF NOT EXISTS photo_event ON photos(event_id,status,created);
CREATE INDEX IF NOT EXISTS search_user ON searches(user_id,created);
CREATE INDEX IF NOT EXISTS job_queue ON jobs(status,available);
CREATE INDEX IF NOT EXISTS mail_queue ON mail(status,available);
CREATE INDEX IF NOT EXISTS metrics_date ON metrics(created);
"""


class Database:
    def __init__(self, root=None):
        self.root = Path(
            root or os.getenv("ALPICTURIA_DATA", "./var/alpicturia")
        ).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        for directory in ("photos", "previews", "selfies", "incoming"):
            (self.root / directory).mkdir(exist_ok=True, mode=0o700)
        self.path = self.root / "app.sqlite3"
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def all(self, sql, args=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def run(self, sql, args=()):
        with self.connect() as conn:
            return conn.execute(sql, args).rowcount
