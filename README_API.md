# Backend - AI Resume Analyzer API

FastAPI backend with NLP analysis and OpenAI integration.

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Set environment variables
echo "OPENAI_API_KEY=your_key_here" > .env

# Run FastAPI server
uvicorn app.main:app --reload --port 8000
```

Server runs on `http://localhost:8000`

## API Endpoints

### POST /api/analyze-resume
Upload resume (PDF/DOCX) + job details → Get ATS score, skill gaps, AI suggestions

**Request:**
- `resume`: File (PDF/DOCX)
- `job_title`: String
- `job_description`: String

**Response:**
```json
{
  "ats_score": 87,
  "skill_gaps": [...],
  "suggestions": [...],
  "keywords": [...],
  "experience_match": 90
}
```

## Features

- PDF/DOCX text extraction
- NLP skill extraction
- ATS score calculation
- Keyword matching
- OpenAI-powered suggestions
