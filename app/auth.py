from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import jwt
import bcrypt
import os
from typing import Optional
from app.database import get_conn, release_conn

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    # Development fallback: don't crash the app on import — use a dev secret.
    # In production you should set JWT_SECRET in the environment.
    print("WARNING: JWT_SECRET not set, using development secret")
    SECRET_KEY = "dev-secret"

def create_token(user_id: int, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        raise HTTPException(401, "Invalid or expired token")

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    return verify_token(authorization.split(" ")[1])

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
async def signup(req: SignupRequest):
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email = %s", (req.email,))
        if c.fetchone():
            raise HTTPException(400, "Email already registered")

        password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
        c.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
            (req.name, req.email, password_hash)
        )
        conn.commit()
        user_id = c.fetchone()[0]
        token = create_token(user_id, req.email)
        return {"token": token, "user": {"id": user_id, "name": req.name, "email": req.email}}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Signup failed: {str(e)}")
    finally:
        release_conn(conn)

@router.post("/login")
async def login(req: LoginRequest):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id, name, email, password_hash FROM users WHERE email = %s", (req.email,))
        user = c.fetchone()

        if not user or not bcrypt.checkpw(req.password.encode(), user[3].encode()):
            raise HTTPException(401, "Invalid email or password")

        token = create_token(user[0], user[2])
        return {"token": token, "user": {"id": user[0], "name": user[1], "email": user[2]}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Login failed: {str(e)}")
    finally:
        release_conn(conn)

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("SELECT id, name, email FROM users WHERE id = %s", (user["user_id"],))
        u = c.fetchone()
        if not u:
            raise HTTPException(404, "User not found")
        return {"id": u[0], "name": u[1], "email": u[2]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch user: {str(e)}")
    finally:
        release_conn(conn)
