# FastAPI Backend - Deployment Guide

## Local Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with local values
uvicorn app.main:app --reload
```

Server runs on `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Production Deployment on Render.com

### 1. Create Render Web Service
- Connect your GitHub repository
- Select the `backend/` folder as root directory
- Set build command: `pip install -r requirements.txt`
- Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 2. Environment Variables (add in Render dashboard)
- `ENV=production`
- `GROQ_API_KEY=your-key`
- `JWT_SECRET=your-secret` (use a strong random string)
- `OPENAI_API_KEY=your-key`
- `ALLOWED_ORIGINS=https://your-vercel-frontend.vercel.app`
- `DATABASE_URL=your-postgresql-connection-string`

### 3. PostgreSQL Database
- Create a free PostgreSQL database on Render
- Render will auto-inject `DATABASE_URL` into the web service

### 4. Health Check
After deployment, verify: `https://your-render-backend.onrender.com/health`

## Production Readiness Checklist

✅ FastAPI configured with production settings
✅ CORS properly configured via env vars
✅ Docs disabled in production (ENV=production)
✅ Rate limiting enabled (slowapi)
✅ JWT authentication in place
✅ Uvicorn production command ready
✅ PostgreSQL database configured
✅ Groq API integration verified
✅ All secrets in environment variables (never committed)

## Key Production Settings

- **Docs disabled**: Set `ENV=production` to disable `/docs` endpoint
- **CORS**: Configured dynamically via `ALLOWED_ORIGINS` env var
- **Uvicorn host**: Bind to `0.0.0.0` for production
- **Port**: Set via `PORT` env var (Render uses `$PORT`)
- **Rate limiting**: Enabled with slowapi
