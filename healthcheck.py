from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os, asyncio, psycopg2, httpx, importlib, sys

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"

results = []

def check(label, ok, detail=""):
    tag = PASS if ok else FAIL
    msg = f"{tag} {label}" + (f" — {detail}" if detail else "")
    print(msg)
    results.append(ok)

print("=" * 60)
print("SYSTEM HEALTH CHECK")
print("=" * 60)

# ── 1. ENV VARS ──────────────────────────────────────────────
print("\n[ENV VARIABLES]")
check("GROQ_API_KEY",    bool(os.getenv("GROQ_API_KEY")))
check("DATABASE_URL",    bool(os.getenv("DATABASE_URL")))
check("JWT_SECRET",      bool(os.getenv("JWT_SECRET")))
check("ALLOWED_ORIGINS", bool(os.getenv("ALLOWED_ORIGINS")), os.getenv("ALLOWED_ORIGINS"))
check("ENV",             bool(os.getenv("ENV")), os.getenv("ENV"))

# ── 2. PYTHON PACKAGES ───────────────────────────────────────
print("\n[PYTHON PACKAGES]")
packages = ["fastapi", "uvicorn", "psycopg2", "httpx", "jwt", "bcrypt",
            "dotenv", "slowapi", "pydantic", "reportlab", "fitz"]
for pkg in packages:
    try:
        importlib.import_module(pkg if pkg != "dotenv" else "dotenv")
        check(pkg, True)
    except ImportError:
        check(pkg, False, "not installed")

# ── 3. POSTGRESQL ─────────────────────────────────────────────
print("\n[POSTGRESQL]")
try:
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    c = conn.cursor()

    c.execute("SELECT version()")
    ver = c.fetchone()[0][:55]
    check("Connection", True, ver)

    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    check("users table", True, f"{users} users")

    c.execute("SELECT COUNT(*) FROM analyses")
    analyses = c.fetchone()[0]
    check("analyses table", True, f"{analyses} analyses")

    c.execute("SELECT COUNT(*) FROM assessment_violations")
    violations = c.fetchone()[0]
    check("assessment_violations table", True, f"{violations} records")

    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='analyses' ORDER BY ordinal_position")
    cols = [r[0] for r in c.fetchall()]
    expected = ["id","user_id","overall_score","completeness_score","impact_score",
                "professional_score","role_match_score","career_level","market_readiness",
                "role_analyzed","skills_found","strengths","weaknesses","suggestions",
                "keywords","ai_insights","created_at"]
    missing_cols = [c2 for c2 in expected if c2 not in cols]
    check("analyses schema", not missing_cols,
          "all columns present" if not missing_cols else f"missing: {missing_cols}")

    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='assessment_violations' ORDER BY ordinal_position")
    violation_cols = [r[0] for r in c.fetchall()]
    violation_expected = ["id", "user_id", "assessment_role", "reason", "violation_count", "metadata", "created_at"]
    missing_violation_cols = [c2 for c2 in violation_expected if c2 not in violation_cols]
    check(
        "assessment_violations schema",
        not missing_violation_cols,
        "all columns present" if not missing_violation_cols else f"missing: {missing_violation_cols}"
    )

    c.execute("SELECT indexname FROM pg_indexes WHERE tablename IN ('users','analyses','assessment_violations') ORDER BY indexname")
    indexes = [r[0] for r in c.fetchall()]
    needed = [
        "users_pkey", "users_email_key", "analyses_pkey", "idx_analyses_user_id", "idx_analyses_created_at",
        "assessment_violations_pkey", "idx_assessment_violations_user_id", "idx_assessment_violations_created_at"
    ]
    missing_idx = [i for i in needed if i not in indexes]
    check("indexes", not missing_idx,
          str(indexes) if not missing_idx else f"missing: {missing_idx}")

    c.execute("""SELECT tc.constraint_name FROM information_schema.table_constraints tc
                 WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_name='analyses'""")
    fk = c.fetchone()
    check("foreign key analyses->users", bool(fk))

    conn.close()
except Exception as e:
    check("PostgreSQL", False, str(e))

# ── 4. GROQ API ───────────────────────────────────────────────
print("\n[GROQ API]")
async def test_groq():
    try:
        api_key = os.getenv("GROQ_API_KEY")
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": "Reply with just the word: OK"}],
                      "max_tokens": 5}
            )
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()
                check("Groq API key valid", True, f"model responded: '{reply}'")
            elif r.status_code == 401:
                check("Groq API key valid", False, "Invalid API key (401)")
            elif r.status_code == 429:
                check("Groq API key valid", True, "Rate limited (429) — key is valid but quota hit")
            else:
                check("Groq API key valid", False, f"HTTP {r.status_code}: {r.text[:100]}")
    except httpx.TimeoutException:
        check("Groq API key valid", False, "Request timed out")
    except Exception as e:
        check("Groq API key valid", False, str(e))

asyncio.run(test_groq())

# ── 5. BACKEND MODULES ────────────────────────────────────────
print("\n[BACKEND MODULES]")
modules = [
    ("app.main",             "FastAPI app"),
    ("app.database",         "database pool"),
    ("app.auth",             "auth router"),
    ("app.routes.analysis",  "analysis router"),
    ("app.groq_analyzer",    "Groq analyzer"),
    ("app.nlp_processor",    "NLP processor"),
    ("app.advanced_analyzer","advanced analyzer"),
]
sys.path.insert(0, str(Path(__file__).parent))
for mod, label in modules:
    try:
        importlib.import_module(mod)
        check(label, True)
    except Exception as e:
        check(label, False, str(e)[:80])

# ── 6. FRONTEND FILES ─────────────────────────────────────────
print("\n[FRONTEND FILES]")
frontend = Path(__file__).parent.parent / "frontend"
critical_files = [
    "src/App.jsx",
    "src/pages/Home.jsx",
    "src/pages/ResumeAnalyzer.jsx",
    "src/pages/CoverLetter.jsx",
    "src/pages/Login.jsx",
    "src/pages/Signup.jsx",
    "src/api/analysis.js",
    "src/components/Header.jsx",
    "src/components/ResumeAnalyzer/UploadZone.jsx",
    "package.json",
    "vite.config.js",
    "tailwind.config.js",
]
for f in critical_files:
    p = frontend / f
    check(f, p.exists())

# ── SUMMARY ───────────────────────────────────────────────────
print("\n" + "=" * 60)
passed = sum(results)
total  = len(results)
print(f"RESULT: {passed}/{total} checks passed")
if passed == total:
    print("All systems operational.")
else:
    print(f"{total - passed} issue(s) need attention.")
print("=" * 60)
