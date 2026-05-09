from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import psycopg2
import os

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True
c = conn.cursor()

c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)")
print("Created index: idx_analyses_user_id")

c.execute("CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at)")
print("Created index: idx_analyses_created_at")

c.execute("SELECT indexname FROM pg_indexes WHERE tablename='analyses' ORDER BY indexname")
print("\nAll analyses indexes:", [r[0] for r in c.fetchall()])

conn.close()
print("\nDone.")
