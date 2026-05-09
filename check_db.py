from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

from app.database import get_conn, release_conn

conn = get_conn()
c = conn.cursor()

print("=" * 60)
print("USERS TABLE")
print("=" * 60)
c.execute("SELECT id, name, email, created_at FROM users ORDER BY id")
users = c.fetchall()
print(f"Total users: {len(users)}\n")
for u in users:
    print(f"  ID      : {u[0]}")
    print(f"  Name    : {u[1]}")
    print(f"  Email   : {u[2]}")
    print(f"  Created : {u[3]}")
    print()

print("=" * 60)
print("ANALYSES TABLE")
print("=" * 60)
c.execute("""
    SELECT a.id, u.name, u.email, a.overall_score, a.role_analyzed,
           a.career_level, a.market_readiness, a.created_at
    FROM analyses a
    JOIN users u ON u.id = a.user_id
    ORDER BY a.id
""")
analyses = c.fetchall()
print(f"Total analyses: {len(analyses)}\n")
for a in analyses:
    print(f"  Analysis ID   : {a[0]}")
    print(f"  User          : {a[1]} ({a[2]})")
    print(f"  Overall Score : {a[3]}")
    print(f"  Role Analyzed : {a[4]}")
    print(f"  Career Level  : {a[5]}")
    print(f"  Market Ready  : {a[6]}")
    print(f"  Created       : {a[7]}")
    print()

release_conn(conn)
