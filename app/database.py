import os
from psycopg2 import pool

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=os.getenv("DATABASE_URL")
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
