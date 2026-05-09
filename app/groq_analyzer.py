import os
import json
import re
import logging
import asyncio
import time
from typing import Dict, Optional, List, Any
import httpx
from fastapi import HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Rate limiting configuration
_GROQ_REQUEST_QUEUE = asyncio.Queue(maxsize=10)
_GROQ_LAST_REQUEST_TIME = 0
_GROQ_MIN_REQUEST_INTERVAL = 0.5  # Minimum 500ms between requests
_REQUEST_LOCK = asyncio.Lock()

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # Start with 2 second delay

def get_groq_api_key() -> str:
    """Get Groq API key from environment"""
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY environment variable not set"
        )
    return api_key


async def _rate_limited_request(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict,
    json_data: Dict,
    timeout: float
) -> httpx.Response:
    """Make a rate-limited API request with exponential backoff retry logic"""
    global _GROQ_LAST_REQUEST_TIME
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Rate limiting: enforce minimum interval between requests
            async with _REQUEST_LOCK:
                elapsed = time.time() - _GROQ_LAST_REQUEST_TIME
                if elapsed < _GROQ_MIN_REQUEST_INTERVAL:
                    await asyncio.sleep(_GROQ_MIN_REQUEST_INTERVAL - elapsed)
                _GROQ_LAST_REQUEST_TIME = time.time()
            
            # Make the request
            response = await client.post(
                url,
                headers=headers,
                json=json_data,
                timeout=timeout
            )
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                if attempt < MAX_RETRIES:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Rate limited (429). Retrying after {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Rate limited (429) - max retries exceeded")
                    raise HTTPException(
                        status_code=429,
                        detail="Groq API rate limit exceeded. Please try again in a few minutes."
                    )
            
            return response
            
        except asyncio.TimeoutError:
            if attempt < MAX_RETRIES:
                logger.warning(f"Timeout. Retrying (attempt {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            raise
    
    raise HTTPException(
        status_code=500,
        detail="Failed to complete request after multiple retries"
    )

def safe_json_parse(content: str) -> Optional[Dict]:
    """Safely parse JSON with multiple fallback strategies"""
    # Strategy 1: Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # Strategy 2: Strip markdown backticks
    try:
        cleaned = content.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        pass
    
    # Strategy 3: Extract JSON object using regex
    try:
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            return json.loads(match.group(0))
    except json.JSONDecodeError:
        pass
    
    logger.error(f"Failed to parse JSON from content: {content[:200]}")
    return None

def sanitize_response(data: Dict) -> Dict:
    """Ensure all required fields exist with safe fallback values"""
    defaults = {
        "overall_score": 50,
        "completeness_score": 50,
        "impact_score": 50,
        "professional_score": 50,
        "strong_verbs_used": 0,
        "career_level_estimation": "Entry Level",
        "market_readiness": "Needs Improvement",
        "strengths": ["Resume uploaded successfully"],
        "weaknesses": ["Add more details"],
        "skills_found": [],
        "missing_role_skills": [],
        "improvement_priority": ["Add quantified achievements", "Expand skills section", "Include projects"],
        "keywords": {"found": [], "missing": []},
        "suggestions": ["Add metrics to achievements"],
        "role_analyzed": None,
        "role_match_score": 0,
        "ai_insights": {
            "quick_verdict": "Resume analysis complete",
            "key_strengths": ["Resume structure present"],
            "skill_gaps": [],
            "top_actions": ["Add quantified achievements"],
            "keywords_found": [],
            "keywords_missing": []
        }
    }
    
    # Merge with defaults
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
    
    # Ensure keywords structure
    if "keywords" not in data or not isinstance(data["keywords"], dict):
        data["keywords"] = {"found": [], "missing": []}
    if "found" not in data["keywords"]:
        data["keywords"]["found"] = []
    if "missing" not in data["keywords"]:
        data["keywords"]["missing"] = []
    
    return data


# Words that appear in skill phrases / section headings — never a person's name
_SKIP_WORDS = {
    'education', 'experience', 'skills', 'projects', 'summary', 'objective',
    'certifications', 'achievements', 'awards', 'languages', 'interests',
    'references', 'profile', 'contact', 'work', 'employment', 'career',
    'technical', 'professional', 'personal', 'details', 'information',
    'solving', 'development', 'engineering', 'management', 'design',
    'control', 'version', 'system', 'analysis', 'testing', 'programming',
    'framework', 'database', 'network', 'security', 'cloud', 'web', 'mobile',
    'full', 'stack', 'front', 'back', 'end', 'data', 'machine', 'learning',
    'artificial', 'intelligence', 'software', 'hardware', 'computer', 'science',
    'git', 'agile', 'scrum', 'devops', 'api', 'rest', 'sql', 'nosql',
}

# Strict pattern: 2-4 words, each starting with uppercase then lowercase letters only
_NAME_RE = re.compile(r'^[A-Z][a-z]+(?: [A-Z][a-z]+){1,3}$')

def _extract_candidate_info(resume_text: str) -> dict:
    """Extract name, email, phone from resume text."""
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', resume_text)
    # Handles +91 Indian numbers and standard formats
    phone_match = re.search(
        r'(?:\+91[\s-]?)?[6-9]\d{9}|(?:\+?\d[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}',
        resume_text
    )

    name = ''
    for raw in resume_text.splitlines()[:25]:
        line = re.sub(r'^[^\w]+', '', raw.strip()).strip()  # strip leading bullets
        if not line or re.search(r'[\d@|/\\]', line):
            continue
        if not _NAME_RE.match(line):   # must be strict Title Case words
            continue
        lower_words = {w.lower() for w in line.split()}
        if lower_words & _SKIP_WORDS:
            continue
        name = line
        break

    return {
        'candidate_name': name,
        'candidate_email': email_match.group(0) if email_match else '',
        'candidate_phone': phone_match.group(0).strip() if phone_match else ''
    }


def _extract_cover_letter_text(content: str, salutation: str) -> str:
    """Extract plain-text letter content when the model does not return valid JSON."""
    cleaned = content.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return f"{salutation}\n\nI am excited to apply for this opportunity. My background aligns well with the role requirements, and I would welcome the chance to contribute.\n\nSincerely,\n[Your Name]"

    if not cleaned.startswith(salutation):
        cleaned = f"{salutation}\n\n{cleaned}"

    if "Sincerely," not in cleaned:
        cleaned = f"{cleaned.rstrip()}\n\nSincerely,\n[Your Name]"

    return cleaned


def sanitize_cover_letter_response(data: Optional[Dict], fallback_content: str, job_title: str, company_name: str, tone: str, salutation: str) -> Dict:
    """Normalize cover letter output and fall back to plain text extraction when needed."""
    parsed = data.copy() if isinstance(data, dict) else {}
    cover_letter = parsed.get("cover_letter")

    if not isinstance(cover_letter, str) or len(cover_letter.strip()) < 60:
        cover_letter = _extract_cover_letter_text(fallback_content, salutation)

    parsed["cover_letter"] = cover_letter.strip()
    # candidate info is injected by the caller
    parsed["subject_line"] = parsed.get("subject_line") or f"Application for {job_title} at {company_name}"
    parsed["key_points"] = parsed.get("key_points") if isinstance(parsed.get("key_points"), list) else []
    parsed["ats_keywords"] = parsed.get("ats_keywords") if isinstance(parsed.get("ats_keywords"), list) else []
    parsed["missing_keywords"] = parsed.get("missing_keywords") if isinstance(parsed.get("missing_keywords"), list) else []
    parsed["tone"] = parsed.get("tone") or tone
    parsed["word_count"] = parsed.get("word_count") if isinstance(parsed.get("word_count"), int) else len(parsed["cover_letter"].split())
    parsed["match_score"] = parsed.get("match_score") if isinstance(parsed.get("match_score"), int) else 65
    return parsed

async def analyze_resume_intelligent(resume_text: str) -> Dict:
    """Analyze resume without job description using Groq AI"""
    api_key = get_groq_api_key()
    
    system_prompt = """You are an expert ATS resume reviewer with 15 years of hiring experience. 
CRITICAL INSTRUCTIONS:
- Analyze ONLY the actual content provided. DO NOT use templates or generic responses.
- Each resume is UNIQUE. Vary your scores significantly based on actual observed quality.
- Return ONLY raw valid JSON, no markdown, no explanation.
- Scores MUST differ meaningfully between different resumes."""
    
    user_prompt = f"""Analyze THIS SPECIFIC RESUME and return scores that accurately reflect its actual quality.

SCORING GUIDANCE:
- overall_score: Entry (20-45), Junior (45-60), Mid (60-75), Senior (75-90), Expert (90-100)
- completeness_score: Measure % of typical resume sections present
- impact_score: Score quantified achievements/metrics (0-20 if none, 80+ if many)
- professional_score: Score formatting, clarity, structure (0-40 poor, 40-70 good, 70+ excellent)

Return EXACTLY this JSON (fill in each field based on ACTUAL resume content, not defaults):
{{
  "overall_score": CALCULATE based on level, skills, experience (must vary 20-90),
  "completeness_score": Percentage of sections found (0, 16, 33, 50, 66, 83, 100),
  "impact_score": Quality/quantity of metrics (low=20, medium=60, high=85),
  "professional_score": Presentation quality (0-100 scale),
  "strong_verbs_used": COUNT of verbs like led, developed, designed, built, etc,
  "career_level_estimation": Determine from years exp and achievement level,
  "market_readiness": "Needs Improvement" if score<40 OR "Job Ready" if 40-70 OR "Strong Candidate" if 70+,
  "strengths": [4 SPECIFIC strengths ONLY from THIS resume],
  "weaknesses": [3 SPECIFIC weaknesses ONLY from THIS resume],
  "skills_found": [all tech skills extracted],
  "missing_role_skills": [],
  "improvement_priority": [3 specific action items for THIS resume],
  "keywords": {{"found": [keywords in THIS resume], "missing": [keywords not in THIS resume]}},
  "suggestions": [4 specific suggestions],
  "role_analyzed": null,
  "role_match_score": 0,
  "ai_insights": {{
    "quick_verdict": "Honest 1-sentence verdict about THIS candidate",
    "key_strengths": [4 actual strengths],
    "skill_gaps": [6 missing skills],
    "top_actions": [3 improvements],
    "keywords_found": [8 keywords found],
    "keywords_missing": [8 keywords missing]
  }}
}}

RESUME TO ANALYZE:
{resume_text}"""
    
    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client,
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json_data={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 3000,
                    "top_p": 0.95
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Groq API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Groq API request failed: {response.status_code}"
                )
            
            try:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("Empty content in API response")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse Groq API response: {str(e)}")
                raise HTTPException(
                    status_code=502,
                    detail="Invalid response format from Groq API"
                )
            
            parsed_data = safe_json_parse(content)
            if not parsed_data:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse JSON response from Groq API"
                )
            
            return sanitize_response(parsed_data)

    except httpx.TimeoutException:
        logger.error("Groq API timeout")
        raise HTTPException(status_code=504, detail="AI analysis timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Groq analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


async def generate_cover_letter(
    resume_text: str,
    job_title: str,
    company_name: str,
    job_description: str,
    tone: str = "Professional",
    length: str = "Medium",
    hiring_manager: str = ""
) -> Dict:
    """Generate a tailored cover letter using Groq AI"""
    api_key = get_groq_api_key()

    length_map = {
        "Short": "2 body paragraphs, ~150 words total",
        "Medium": "3 body paragraphs, ~250 words total",
        "Long": "4 body paragraphs, ~350 words total"
    }
    length_instruction = length_map.get(length, length_map["Medium"])
    salutation = f"Dear {hiring_manager}," if hiring_manager.strip() else "Dear Hiring Manager,"

    tone_guide = {
        "Professional": "formal, polished, business-appropriate language",
        "Enthusiastic": "energetic, passionate, show genuine excitement for the role",
        "Confident": "assertive, results-driven, highlight achievements boldly",
        "Creative": "engaging, storytelling approach, memorable opening"
    }.get(tone, "professional")

    system_prompt = """You are an expert career coach and ATS-optimized cover letter writer with 15+ years experience. Return ONLY raw valid JSON, no markdown, no explanation."""

    user_prompt = f"""Write a {tone.lower()} cover letter ({length_instruction}) for this candidate applying to {job_title} at {company_name}.

Tone guide: {tone_guide}
Use keywords from the job description naturally. Make it ATS-friendly. Be specific — reference actual skills and experience from the resume.

Return EXACTLY this JSON (no markdown, no extra text):
{{
  "cover_letter": "Full letter text. Start with '{salutation}\\n\\n'. Opening paragraph hooks the reader. Body paragraphs highlight 2-3 specific achievements with metrics if available. Closing paragraph with call to action. End with 'Sincerely,\\n[Your Name]'. Paragraphs separated by \\n\\n.",
  "subject_line": "Compelling email subject line, e.g. 'Application for {job_title} — [Candidate Name]'",
  "key_points": ["4 specific selling points actually used in the letter, each under 10 words"],
  "ats_keywords": ["8-10 keywords from JD that appear in the letter"],
  "missing_keywords": ["3-5 important JD keywords NOT in resume — candidate should add these"],
  "tone": "{tone}",
  "word_count": <integer word count of cover_letter>,
  "match_score": <0-100 integer: how well resume matches this specific job>
}}

Job Title: {job_title}
Company: {company_name}
Job Description:\n{job_description[:2500]}

Resume:\n{resume_text[:3500]}"""

    candidate_info = _extract_candidate_info(resume_text)

    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client,
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json_data={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.45,
                    "max_tokens": 2500
                },
                timeout=45.0
            )

            if response.status_code != 200:
                logger.error(f"Groq cover letter error: {response.status_code} - {response.text}")
                raise HTTPException(500, f"Groq API error: {response.status_code}")

            try:
                response_data = response.json()
                content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("Empty content in API response")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse Groq cover letter response: {str(e)}")
                raise HTTPException(500, f"Invalid response format from Groq API")
            
            parsed = safe_json_parse(content)
            result = sanitize_cover_letter_response(parsed, content, job_title, company_name, tone, salutation)
            result.update(candidate_info)
            return result
    except httpx.TimeoutException:
        logger.error("Groq cover letter timeout")
        raise HTTPException(status_code=504, detail="Cover letter generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cover letter generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {str(e)}")


def _normalize_option(option: Any, index: int) -> str:
    if isinstance(option, str) and option.strip():
        cleaned = option.strip()
        cleaned = re.sub(r'^[A-Da-d][\)\.:\-]\s*', '', cleaned)
        cleaned = re.sub(r'^Option\s+[A-Da-d][\)\.:\-]?\s*', '', cleaned, flags=re.IGNORECASE)
        return cleaned or f"Option {index + 1}"
    labels = ["A", "B", "C", "D"]
    return f"Option {labels[index]}"


def _normalize_question(raw_question: Dict[str, Any], qid: int, section_id: str) -> Dict[str, Any]:
    options = raw_question.get("options", []) if isinstance(raw_question, dict) else []
    if not isinstance(options, list):
        options = []
    options = options[:4] + [""] * (4 - len(options))
    options = [_normalize_option(opt, i) for i, opt in enumerate(options)]

    difficulty = str(raw_question.get("difficulty", "Medium")).strip().title()
    if difficulty not in {"Easy", "Medium", "Hard"}:
        difficulty = "Medium"

    points_map = {"Easy": 5, "Medium": 8, "Hard": 10}
    points = raw_question.get("points", points_map[difficulty])
    if not isinstance(points, int) or points <= 0:
        points = points_map[difficulty]

    correct = raw_question.get("correct", 0)
    if not isinstance(correct, int) or correct < 0 or correct > 3:
        correct = 0

    text = str(raw_question.get("question", "")).strip() or "Question unavailable"
    topic = str(raw_question.get("topic", "General")).strip() or "General"
    explanation = str(raw_question.get("explanation", "")).strip()
    hr_context = str(raw_question.get("hr_context", "")).strip()

    return {
      "id": qid,
      "section": section_id,
      "question": text,
      "options": options,
      "correct": correct,
      "difficulty": difficulty,
      "points": points,
      "topic": topic,
      "explanation": explanation,
      "hr_context": hr_context
    }


def _fallback_assessment(candidate_name: str, role: str) -> Dict:
    fallback_questions = [
        {
            "id": 1, "section": "technical",
            "question": "Which practice best improves maintainability of a growing codebase?",
            "options": ["Add tests with clear naming", "Avoid comments completely", "Use only single-letter variables", "Skip code reviews"],
            "correct": 0, "difficulty": "Easy", "points": 5, "topic": "Software Engineering",
            "explanation": "Tests with clear naming serve as living documentation and catch regressions early.",
            "hr_context": "Assesses engineering discipline and long-term thinking."
        },
        {
            "id": 2, "section": "behavioral",
            "question": "Tell me about a time you had to meet a tight deadline. What was your approach?",
            "options": ["Prioritized tasks, communicated blockers early, and delivered core features first", "Worked overtime without telling anyone", "Asked to extend the deadline immediately", "Delegated everything to teammates"],
            "correct": 0, "difficulty": "Medium", "points": 8, "topic": "Time Management",
            "explanation": "Proactive communication and prioritization are hallmarks of a reliable professional.",
            "hr_context": "Evaluates time management, ownership, and communication under pressure."
        },
        {
            "id": 3, "section": "situational",
            "question": "A critical bug is found 1 hour before a product release. What do you do first?",
            "options": ["Assess severity, notify stakeholders, and decide whether to delay or hotfix", "Release anyway and fix later", "Blame the QA team", "Ignore it and hope no one notices"],
            "correct": 0, "difficulty": "Medium", "points": 8, "topic": "Crisis Management",
            "explanation": "Assessing impact and communicating immediately is the professional standard.",
            "hr_context": "Tests judgment, accountability, and stakeholder management."
        },
        {
            "id": 4, "section": "aptitude",
            "question": "If a process takes 20% less time after optimization, the new time is:",
            "options": ["80% of original", "120% of original", "20% of original", "100% of original"],
            "correct": 0, "difficulty": "Easy", "points": 5, "topic": "Quantitative Reasoning",
            "explanation": "Reducing by 20% means 100% - 20% = 80% of the original time remains.",
            "hr_context": "Assesses basic quantitative reasoning used in performance analysis."
        }
    ]
    return {
        "candidate_name": candidate_name or "Candidate",
        "role": role or "General",
        "candidate_email": None,
        "estimated_duration_min": 20,
        "total_questions": len(fallback_questions),
        "total_points": sum(q["points"] for q in fallback_questions),
        "sections": [
            {"id": "technical", "name": "Technical Skills", "count": 1},
            {"id": "behavioral", "name": "Behavioral (HR)", "count": 1},
            {"id": "situational", "name": "Situational Judgment", "count": 1},
            {"id": "aptitude", "name": "Aptitude", "count": 1}
        ],
        "questions": fallback_questions,
        "hr_questions": [
            {"id": 1, "question": "Describe a challenging deadline you faced and how you prioritized work.", "time_limit_sec": 120, "max_marks": 5},
            {"id": 2, "question": "Share an example where you handled conflict within a team professionally.", "time_limit_sec": 120, "max_marks": 5},
            {"id": 3, "question": "Tell us about a mistake you made at work and what you learned from it.", "time_limit_sec": 120, "max_marks": 5},
            {"id": 4, "question": "How do you communicate technical blockers to non-technical stakeholders?", "time_limit_sec": 120, "max_marks": 5},
            {"id": 5, "question": "Why are you a good fit for this role, based on your experience?", "time_limit_sec": 120, "max_marks": 5},
        ],
    }


def _default_hr_questions(role: str) -> List[Dict[str, Any]]:
    role_label = role or "this role"
    return [
        {"id": 1, "question": f"Describe a high-pressure situation you handled while working in {role_label}.", "time_limit_sec": 120, "max_marks": 5},
        {"id": 2, "question": "Give an example of how you resolved disagreement in a team and kept delivery on track.", "time_limit_sec": 120, "max_marks": 5},
        {"id": 3, "question": "Tell us about one decision you made with incomplete information and why.", "time_limit_sec": 120, "max_marks": 5},
        {"id": 4, "question": "Explain how you communicate complex updates to managers or clients.", "time_limit_sec": 120, "max_marks": 5},
        {"id": 5, "question": f"What are your top growth areas to become stronger in {role_label}?", "time_limit_sec": 120, "max_marks": 5},
    ]


def _normalize_hr_questions(data: Dict[str, Any], normalized_questions: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
    raw_hr = data.get("hr_written_questions", []) if isinstance(data, dict) else []
    parsed: List[Dict[str, Any]] = []

    if isinstance(raw_hr, list):
        for idx, item in enumerate(raw_hr[:5], start=1):
            if isinstance(item, dict):
                q_text = str(item.get("question", "")).strip()
                time_limit = item.get("time_limit_sec", 120)
            else:
                q_text = str(item).strip()
                time_limit = 120

            if not q_text:
                continue

            try:
                time_limit = int(time_limit)
            except Exception:
                time_limit = 120

            parsed.append(
                {
                    "id": idx,
                    "question": q_text,
                    "time_limit_sec": min(300, max(60, time_limit)),
                    "max_marks": 5,
                }
            )

    if len(parsed) < 5:
        behavioral_pool = [q for q in normalized_questions if q.get("section") == "behavioral"]
        for q in behavioral_pool:
            if len(parsed) >= 5:
                break
            q_text = str(q.get("question", "")).strip()
            if not q_text:
                continue
            if any(existing["question"].lower() == q_text.lower() for existing in parsed):
                continue
            parsed.append({
                "id": len(parsed) + 1,
                "question": q_text,
                "time_limit_sec": 120,
                "max_marks": 5,
            })

    if len(parsed) < 5:
        defaults = _default_hr_questions(role)
        for item in defaults:
            if len(parsed) >= 5:
                break
            if any(existing["question"].lower() == item["question"].lower() for existing in parsed):
                continue
            parsed.append(item)

    return parsed[:5]


def _extract_resume_anchor_terms(resume_text: str) -> set:
    """Extract candidate-specific terms to verify question personalization."""
    text = resume_text.lower()
    anchors = set()

    tech_patterns = [
        r'\bpython\b', r'\bjavascript\b', r'\btypescript\b', r'\bjava\b', r'\breact\b',
        r'\bnode(?:\.js)?\b', r'\bfastapi\b', r'\bdjango\b', r'\bflask\b', r'\bsql\b',
        r'\bpostgresql\b', r'\bmysql\b', r'\bmongodb\b', r'\bdocker\b', r'\bkubernetes\b',
        r'\baws\b', r'\bazure\b', r'\bgcp\b', r'\bmachine learning\b', r'\bdata science\b',
        r'\brest api\b', r'\bgraphql\b', r'\bmicroservices\b', r'\bexcel\b', r'\bpower\s*bi\b',
        r'\btableau\b', r'\btensorflow\b', r'\bpytorch\b', r'\bscikit[-\s]?learn\b',
        r'\bterraform\b', r'\bansible\b', r'\bjenkins\b', r'\bgitlab\b', r'\bprometheus\b',
        r'\bgrafana\b', r'\bsalesforce\b', r'\bsap\b', r'\boracle\b'
    ]
    for pattern in tech_patterns:
        for match in re.finditer(pattern, text):
            anchors.add(match.group(0).strip())

    # Extract comma-separated skills from likely skills lines.
    for raw_line in resume_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if "skills" in lower_line or line.count(",") >= 3:
            candidate_text = re.sub(r'^\s*(technical\s+)?skills?\s*[:\-]\s*', '', line, flags=re.IGNORECASE)
            for part in re.split(r'[,|/•]+', candidate_text):
                skill = part.strip().lower()
                skill = re.sub(r'\s+', ' ', skill)
                if len(skill) < 2 or len(skill) > 40:
                    continue
                if skill in _SKIP_WORDS:
                    continue
                if re.search(r'[a-z0-9]', skill):
                    anchors.add(skill)

    # Capture short acronyms/tools commonly present in resumes (e.g., AWS, SQL, CRM).
    for token in re.findall(r'\b[A-Z]{2,8}\b', resume_text):
        anchors.add(token.lower())

    return anchors


def _is_assessment_personalized(questions: List[Dict[str, Any]], resume_text: str) -> bool:
    """Ensure generated questions reference candidate resume content (not generic set)."""
    if not questions:
        return False

    resume_anchors = _extract_resume_anchor_terms(resume_text)
    if not resume_anchors:
        # For non-technical resumes, rely on count/quality checks only.
        return len(questions) >= 10

    matched_questions = 0
    matched_anchor_terms = set()
    for q in questions:
        q_text = f"{q.get('question', '')} {q.get('topic', '')}".lower()
        found_in_question = [anchor for anchor in resume_anchors if anchor in q_text]
        if found_in_question:
            matched_questions += 1
            matched_anchor_terms.update(found_in_question)

    # Primary check: at least a few questions should clearly reference resume anchors.
    minimum_question_matches = max(2, len(questions) // 10)
    if matched_questions >= minimum_question_matches and len(matched_anchor_terms) >= 2:
        return True

    # Secondary soft check: accept well-structured assessments with enough depth to avoid false negatives.
    technical_count = sum(1 for q in questions if str(q.get("section", "")).lower() == "technical")
    unique_topics = {
        str(q.get("topic", "")).strip().lower()
        for q in questions
        if str(q.get("topic", "")).strip()
    }
    if len(questions) >= 20 and technical_count >= 8 and len(unique_topics) >= 8:
        logger.info(
            "Assessment passed personalization soft-check (question matches=%s, anchor matches=%s, technical=%s, topics=%s)",
            matched_questions,
            len(matched_anchor_terms),
            technical_count,
            len(unique_topics),
        )
        return True

    logger.warning(
        "Assessment failed personalization check (question matches=%s, anchor matches=%s, total questions=%s)",
        matched_questions,
        len(matched_anchor_terms),
        len(questions),
    )
    return False


def sanitize_assessment_response(data: Optional[Dict], resume_text: str, allow_fallback: bool = True) -> Dict:
    candidate_info = _extract_candidate_info(resume_text)
    candidate_name = (data or {}).get("candidate_name") or candidate_info.get("candidate_name") or "Candidate"
    role = (data or {}).get("role") or "General"

    if not isinstance(data, dict):
        if not allow_fallback:
            raise HTTPException(status_code=502, detail="AI returned an invalid assessment payload. Please retry.")
        return _fallback_assessment(candidate_name, role)

    sections = data.get("sections", [])
    if not isinstance(sections, list):
        if not allow_fallback:
            raise HTTPException(status_code=502, detail="AI returned malformed assessment sections. Please retry.")
        return _fallback_assessment(candidate_name, role)

    normalized_questions: List[Dict[str, Any]] = []
    section_meta = []
    qid = 1

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        sec_id = str(sec.get("id", "general")).strip().lower() or "general"
        sec_name = str(sec.get("name", sec_id.title())).strip() or sec_id.title()
        sec_questions = sec.get("questions", [])
        if not isinstance(sec_questions, list):
            sec_questions = []

        count_before = len(normalized_questions)
        for raw_q in sec_questions:
            if isinstance(raw_q, dict):
                normalized_questions.append(_normalize_question(raw_q, qid, sec_id))
                qid += 1
        section_meta.append({
            "id": sec_id,
            "name": sec_name,
            "count": len(normalized_questions) - count_before
        })

    if not normalized_questions:
        if not allow_fallback:
            raise HTTPException(status_code=502, detail="AI did not generate any valid assessment questions. Please retry.")
        return _fallback_assessment(candidate_name, role)

    if not _is_assessment_personalized(normalized_questions, resume_text):
        if not allow_fallback:
            raise HTTPException(
                status_code=502,
                detail="Assessment generation was not sufficiently personalized to the uploaded resume. Please retry with a clearer resume."
            )
        return _fallback_assessment(candidate_name, role)

    hr_questions = _normalize_hr_questions(data, normalized_questions, role)

    return {
        "candidate_name": candidate_name,
        "role": role,
        "candidate_email": candidate_info.get("candidate_email") or None,
        "estimated_duration_min": max(15, round(len(normalized_questions) * 1.5)),
        "total_questions": len(normalized_questions),
        "total_points": sum(q["points"] for q in normalized_questions),
        "sections": section_meta,
        "questions": normalized_questions,
        "hr_questions": hr_questions,
    }


async def generate_assessment(resume_text: str) -> Dict:
    """Generate a resume-tailored virtual assessment using Groq AI."""
    api_key = get_groq_api_key()

    system_prompt = """You are a panel of senior HR interviewers and technical leads conducting a structured hiring assessment. Every question must feel like it was personally crafted after reading this specific candidate's resume — referencing their actual skills, projects, tools, and experience. Questions must be professional, realistic, and interview-panel quality. Return only valid raw JSON with no markdown or commentary."""

    user_prompt = f"""Create a personalized hiring assessment from this resume. Return EXACTLY this JSON schema:
{{
  "candidate_name": "name from resume or Candidate",
  "role": "detected primary role from resume",
  "sections": [
    {{
      "id": "technical",
      "name": "Technical Skills",
      "questions": [
        {{
          "question": "HR-style question referencing a specific skill or project from the resume",
          "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
          "correct": 0,
          "difficulty": "Easy",
          "points": 5,
          "topic": "specific skill/tool from resume",
          "explanation": "Why this answer is correct and what it tests",
          "hr_context": "What an HR interviewer is evaluating with this question"
        }}
      ]
    }},
    {{ "id": "behavioral", "name": "Behavioral (HR)", "questions": [] }},
    {{ "id": "situational", "name": "Situational Judgment", "questions": [] }},
    {{ "id": "aptitude", "name": "Aptitude", "questions": [] }}
  ],
    "hr_written_questions": [
        {{ "question": "Open-ended HR question tied to this candidate resume", "time_limit_sec": 120 }},
        {{ "question": "Open-ended HR question tied to this candidate resume", "time_limit_sec": 120 }},
        {{ "question": "Open-ended HR question tied to this candidate resume", "time_limit_sec": 120 }},
        {{ "question": "Open-ended HR question tied to this candidate resume", "time_limit_sec": 120 }},
        {{ "question": "Open-ended HR question tied to this candidate resume", "time_limit_sec": 120 }}
    ]
}}
CRITICAL RULES — follow exactly:
- Total: exactly 25 questions across all sections.
- Technical (10 questions): Must reference actual skills, tools, frameworks, or projects listed in this resume. Ask about real-world application, not definitions. E.g. "You used React in your project — which hook would you use to avoid re-fetching data on every render?"
- Behavioral (6 questions): STAR-format HR questions tied to the candidate's experience. E.g. "Your resume shows you led a team project — describe how you handled a conflict within the team." Options should be realistic behavioral responses.
- Situational (5 questions): Workplace scenario questions relevant to the detected role. E.g. "A client escalates a bug 2 hours before deployment. What is your first action?"
- Aptitude (4 questions): Logical reasoning, data interpretation, or quantitative problems relevant to the role.
- Every question must feel personally written for THIS candidate — no generic trivia.
- Exactly 4 options per question labeled A, B, C, D.
- `correct` is integer 0-3 (0=A, 1=B, 2=C, 3=D).
- Difficulty mix: 25% Easy (5 pts), 45% Medium (8 pts), 30% Hard (10 pts).
- `explanation` must explain why the correct answer is right (1-2 sentences).
- `hr_context` must state what competency or trait the HR panel is assessing (1 sentence).
- Also create exactly 5 open-ended HR written questions in `hr_written_questions`, each specific to the resume and role.

Resume:
{resume_text[:5000]}"""

    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client,
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json_data={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.4,
                    "max_tokens": 6000
                },
                timeout=60.0
            )

            if response.status_code != 200:
                logger.error(f"Groq assessment error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=500, detail=f"Groq API error: {response.status_code}")

            try:
                response_data = response.json()
                content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("Empty content in API response")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse Groq assessment response: {str(e)}")
                raise HTTPException(status_code=502, detail="Invalid response format from Groq API")

            parsed = safe_json_parse(content)
            return sanitize_assessment_response(parsed, resume_text, allow_fallback=False)

    except httpx.TimeoutException:
        logger.error("Groq assessment timeout")
        raise HTTPException(status_code=504, detail="Assessment generation timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assessment generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Assessment generation failed: {str(e)}")


async def analyze_resume_with_jd(resume_text: str, job_title: str, job_description: str) -> Dict:
    """Analyze resume with a job description for role matching using Groq AI."""
    api_key = get_groq_api_key()

    system_prompt = """You are an expert ATS resume reviewer with 15 years of hiring experience. Return ONLY raw valid JSON, no markdown, no explanation."""

    user_prompt = f"""Analyze this resume against the job description and return EXACTLY this JSON structure:
{{
  "overall_score": 0-100 honest score,
  "completeness_score": 0-100,
  "impact_score": 0-100,
  "professional_score": 0-100,
  "role_match_score": 0-100 match against job description,
  "strong_verbs_used": count of action verbs found,
  "career_level_estimation": "Entry Level" or "Mid Level" or "Senior",
  "market_readiness": "Job Ready" or "Needs Improvement" or "Strong Candidate",
  "strengths": [4 specific unique strengths],
  "weaknesses": [3 specific unique weaknesses],
  "skills_found": [all tech skills found up to 15],
  "missing_role_skills": [skills in JD missing from resume],
  "improvement_priority": [3 completely different specific actions],
  "keywords": {{
    "found": [up to 10 keywords from JD present in resume],
    "missing": [up to 10 keywords from JD missing in resume]
  }},
  "suggestions": [4 specific actionable suggestions],
  "role_analyzed": "{job_title}",
  "ai_insights": {{
    "quick_verdict": "One sentence: [Level] candidate, [Readiness] for {job_title}",
    "key_strengths": [4 specific strengths],
    "skill_gaps": [6 missing skills from JD],
    "top_actions": [3 specific improvement actions],
    "keywords_found": [8 keywords from JD found in resume],
    "keywords_missing": [8 keywords from JD missing in resume]
  }}
}}

Job Title: {job_title}

Job Description:
{job_description[:2000]}

Resume:
{resume_text[:5000]}"""

    try:
        async with httpx.AsyncClient() as client:
            response = await _rate_limited_request(
                client,
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json_data={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 3000
                },
                timeout=30.0
            )

            if response.status_code != 200:
                logger.error(f"Groq API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Groq API request failed: {response.status_code}"
                )

            try:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    raise ValueError("Empty content in API response")
            except (KeyError, IndexError, ValueError) as e:
                logger.error(f"Failed to parse Groq API response: {str(e)}")
                raise HTTPException(
                    status_code=502,
                    detail="Invalid response format from Groq API"
                )

            parsed_data = safe_json_parse(content)
            if not parsed_data:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to parse JSON response from Groq API"
                )

            return sanitize_response(parsed_data)

    except httpx.TimeoutException:
        logger.error("Groq API timeout")
        raise HTTPException(status_code=504, detail="AI analysis timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Groq analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
