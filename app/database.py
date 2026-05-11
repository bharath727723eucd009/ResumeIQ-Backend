import os
from pathlib import Path

# Support Postgres (psycopg2) when DATABASE_URL is set, otherwise fall back to SQLite
DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None

if DATABASE_URL:
    from psycopg2 import pool

    def get_pool():
        global _pool
        if _pool is None:
            _pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=DATABASE_URL
            )
        return _pool

    def get_conn():
        return get_pool().getconn()

    def release_conn(conn):
        get_pool().putconn(conn)

    def init_db():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    overall_score INTEGER,
                    completeness_score INTEGER,
                    impact_score INTEGER,
                    professional_score INTEGER,
                    role_match_score INTEGER,
                    career_level TEXT,
                    market_readiness TEXT,
                    role_analyzed TEXT,
                    skills_found JSONB,
                    strengths JSONB,
                    weaknesses JSONB,
                    suggestions JSONB,
                    keywords JSONB,
                    ai_insights JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS assessment_violations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    assessment_role TEXT,
                    reason TEXT NOT NULL,
                    violation_count INTEGER NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS assessment_results (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    candidate_name TEXT,
                    candidate_email TEXT,
                    role TEXT,
                    mcq_score INTEGER NOT NULL,
                    hr_score INTEGER NOT NULL,
                    total_score INTEGER NOT NULL,
                    max_score INTEGER NOT NULL,
                    violation_count INTEGER NOT NULL DEFAULT 0,
                    summary JSONB,
                    emailed BOOLEAN NOT NULL DEFAULT FALSE,
                    emailed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_violations_user_id ON assessment_violations(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_violations_created_at ON assessment_violations(created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_results_user_id ON assessment_results(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_results_created_at ON assessment_results(created_at)")
            conn.commit()
        finally:
            release_conn(conn)
else:
    import sqlite3

    DB_PATH = Path(__file__).resolve().parent.parent / "users.db"
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    class SQLiteCursor:
        def __init__(self, cur):
            self._cur = cur
            self._lastrow = None

        def execute(self, sql, params=None):
            if params is None:
                params = ()
            # translate psycopg2-style %s to sqlite ? placeholders
            if '%s' in sql:
                sql = sql.replace('%s', '?')
            # handle RETURNING id by removing it and capturing lastrowid
            if 'RETURNING id' in sql.upper():
                sql = sql.replace(' RETURNING id', '').replace(' returning id', '')
                res = self._cur.execute(sql, params)
                self._lastrow = (self._cur.lastrowid,)
                return res
            return self._cur.execute(sql, params)

        def fetchone(self):
            if self._lastrow is not None:
                tmp = self._lastrow
                self._lastrow = None
                return tmp
            return self._cur.fetchone()

        def fetchall(self):
            return self._cur.fetchall()

        def __getattr__(self, name):
            return getattr(self._cur, name)

    class SQLiteConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return SQLiteCursor(self._conn.cursor())

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

    def get_pool():
        return None

    def get_conn():
        # Return a fresh connection wrapper for sqlite
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return SQLiteConnWrapper(conn)

    def release_conn(conn):
        try:
            conn.close()
        except Exception:
            pass

    def init_db():
        conn = get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    overall_score INTEGER,
                    completeness_score INTEGER,
                    impact_score INTEGER,
                    professional_score INTEGER,
                    role_match_score INTEGER,
                    career_level TEXT,
                    market_readiness TEXT,
                    role_analyzed TEXT,
                    skills_found TEXT,
                    strengths TEXT,
                    weaknesses TEXT,
                    suggestions TEXT,
                    keywords TEXT,
                    ai_insights TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS assessment_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    assessment_role TEXT,
                    reason TEXT NOT NULL,
                    violation_count INTEGER NOT NULL,
                    metadata TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS assessment_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    candidate_name TEXT,
                    candidate_email TEXT,
                    role TEXT,
                    mcq_score INTEGER NOT NULL,
                    hr_score INTEGER NOT NULL,
                    total_score INTEGER NOT NULL,
                    max_score INTEGER NOT NULL,
                    violation_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT,
                    emailed INTEGER NOT NULL DEFAULT 0,
                    emailed_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_violations_user_id ON assessment_violations(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_violations_created_at ON assessment_violations(created_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_results_user_id ON assessment_results(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_assessment_results_created_at ON assessment_results(created_at)")
            conn.commit()
        finally:
            release_conn(conn)
