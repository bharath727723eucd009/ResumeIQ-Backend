from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.database import init_db
from app.routes.analysis import router as analysis_router
from app.auth import router as auth_router

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="AI Resume Analyzer API",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url=None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(analysis_router, prefix="/api", tags=["analysis"])

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def read_root():
    return {"message": "AI Resume Analyzer API", "version": "1.0.0", "status": "ok"}

@app.get("/health")
def health():
    return {"status": "healthy"}
