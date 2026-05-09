from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body, Depends, Header, BackgroundTasks
from datetime import datetime
from typing import Optional, List, Dict, Any
import re
import os
import json
import smtplib
import logging
from email.message import EmailMessage
from pydantic import BaseModel, Field
from app.nlp_processor import NLPProcessor
from app.database import get_conn, release_conn
from app.auth import verify_token, get_current_user

async def get_optional_user(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        try:
            return verify_token(authorization.split(" ")[1])
        except Exception:
            pass
    return None

router = APIRouter()
nlp = NLPProcessor()
logger = logging.getLogger(__name__)


class AssessmentViolationPayload(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)
    violation_count: int = Field(..., ge=1, le=10)
    assessment_role: Optional[str] = Field(None, max_length=120)
    timestamp: Optional[str] = Field(None, max_length=60)


class HRAnswerPayload(BaseModel):
    question: str = Field(..., min_length=6, max_length=600)
    answer: str = Field(default="", max_length=4000)
    time_spent_sec: int = Field(default=0, ge=0, le=600)


class AssessmentSubmitPayload(BaseModel):
    candidate_name: Optional[str] = Field(default="Candidate", max_length=120)
    candidate_email: Optional[str] = Field(default=None, max_length=255)
    role: Optional[str] = Field(default="General", max_length=120)
    mcq_questions: List[Dict[str, Any]] = Field(default_factory=list)
    mcq_answers: Dict[str, int] = Field(default_factory=dict)
    hr_answers: List[HRAnswerPayload] = Field(default_factory=list)
    violation_count: int = Field(default=0, ge=0, le=10)


def _score_hr_answer(answer: str) -> int:
    text = (answer or "").strip()
    if not text:
        return 0

    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)
    if word_count >= 90:
        score = 5
    elif word_count >= 65:
        score = 4
    elif word_count >= 40:
        score = 3
    elif word_count >= 20:
        score = 2
    else:
        score = 1

    star_signals = ["situation", "task", "action", "result", "impact", "outcome", "led", "improved"]
    if sum(1 for token in star_signals if token in text.lower()) >= 2:
        score = min(5, score + 1)

    return score


def _build_assessment_email_body(payload: dict) -> str:
    hr_lines = []
    for item in payload.get("hr_feedback", []):
        hr_lines.append(
            f"Q{item.get('id')}: {item.get('score')}/5\\n"
            f"Strength: {item.get('strength')}\\n"
            f"Improve: {item.get('improvement')}"
        )

    improvements = "\\n".join(f"- {tip}" for tip in payload.get("top_improvements", [])) or "- Keep practicing role-based scenarios and concise communication."

    return (
        f"Hi {payload.get('candidate_name', 'Candidate')},\\n\\n"
        f"Your virtual assessment is complete.\\n\\n"
        f"Role: {payload.get('role', 'General')}\\n"
        f"MCQ Score (25 x 1): {payload.get('mcq_score', 0)}/25\\n"
        f"HR Written Score (5 x 5): {payload.get('hr_score', 0)}/25\\n"
        f"Total Score: {payload.get('total_score', 0)}/50\\n"
        f"Violations Recorded: {payload.get('violation_count', 0)}\\n\\n"
        f"HR Feedback Snapshot:\\n{chr(10).join(hr_lines) if hr_lines else 'No HR feedback available.'}\\n\\n"
        f"Top Improvements:\\n{improvements}\\n\\n"
        f"Thank you for completing the assessment.\\n"
        f"ResumeIQ Assessment Team"
    )


def _send_result_email(recipient: str, subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user or "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not smtp_host or not smtp_from:
        logger.warning("Assessment email skipped: SMTP_HOST/SMTP_FROM_EMAIL not configured")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)

    return True


def _persist_assessment_result(user_id: Optional[int], result_payload: dict, emailed: bool) -> Optional[int]:
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO assessment_results (
                user_id, candidate_name, candidate_email, role,
                mcq_score, hr_score, total_score, max_score,
                violation_count, summary, emailed, emailed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                result_payload.get("candidate_name"),
                result_payload.get("candidate_email"),
                result_payload.get("role"),
                result_payload.get("mcq_score", 0),
                result_payload.get("hr_score", 0),
                result_payload.get("total_score", 0),
                50,
                result_payload.get("violation_count", 0),
                json.dumps(result_payload),
                emailed,
                datetime.now() if emailed else None,
            ),
        )
        row = c.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception:
        conn.rollback()
        return None
    finally:
        release_conn(conn)


def _dispatch_result_email(result_payload: dict):
    recipient = result_payload.get("candidate_email")
    if not recipient:
        logger.warning("Assessment email skipped: candidate_email missing")
        return
    subject = f"Assessment Result - {result_payload.get('role', 'Role Assessment')}"
    body = _build_assessment_email_body(result_payload)
    try:
        sent = _send_result_email(recipient, subject, body)
        if not sent:
            logger.warning("Assessment email not sent for recipient=%s (config missing)", recipient)
    except Exception as e:
        # Email is best-effort so it should not block the API response.
        logger.exception("Assessment email send failed for recipient=%s: %s", recipient, str(e))

@router.post("/analyze-resume")
async def analyze_resume(
    resume: UploadFile = File(...),
    job_title: str = Form(...),
    job_description: str = Form(...),
    user: Optional[dict] = Depends(get_optional_user)
):
    try:
        from app.groq_analyzer import analyze_resume_with_jd
        file_bytes = await resume.read()
        if resume.filename.endswith('.pdf'):
            resume_text = nlp.extract_text_from_pdf(file_bytes)
        elif resume.filename.endswith('.docx'):
            resume_text = nlp.extract_text_from_docx(file_bytes)
        else:
            raise HTTPException(400, "Only PDF and DOCX files supported")
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Resume text is too short or empty")
        result = await analyze_resume_with_jd(resume_text, job_title, job_description)
        result["created_at"] = datetime.now().isoformat()
        if user:
            save_analysis(user["user_id"], result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@router.post("/analyze-resume-detailed")
async def analyze_resume_detailed(
    resume: UploadFile = File(...)
):
    """Enhanced resume analysis endpoint - analyzes ONLY uploaded file content"""
    try:
        # Validate file type
        if not resume.filename:
            raise HTTPException(400, "No filename provided")
        
        file_ext = resume.filename.lower().split('.')[-1]
        if file_ext not in ['pdf', 'docx']:
            raise HTTPException(400, "Only PDF and DOCX files are supported")
        
        # Read and extract text
        file_bytes = await resume.read()
        
        if not file_bytes or len(file_bytes) == 0:
            raise HTTPException(400, "Empty file uploaded")
        
        try:
            if file_ext == 'pdf':
                resume_text = nlp.extract_text_from_pdf(file_bytes)
            else:
                resume_text = nlp.extract_text_from_docx(file_bytes)
        except Exception as e:
            raise HTTPException(400, f"Failed to extract text from file: {str(e)}")
        
        # Validate extracted text
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Resume text is too short or empty. Please upload a valid resume.")
        
        # Normalize text (limit to 50000 chars for safety)
        resume_text = resume_text[:50000]
        resume_text = re.sub(r'\s+', ' ', resume_text).strip()
        
        # Perform comprehensive analysis
        skills_found = nlp.extract_skills(resume_text)
        completeness = nlp.analyze_completeness(resume_text)
        strengths = nlp.analyze_strengths(resume_text)
        weaknesses = nlp.analyze_weaknesses(resume_text)
        section_feedback = nlp.analyze_section_feedback(resume_text)
        readability = nlp.analyze_readability(resume_text)
        tips = nlp.generate_actionable_tips(resume_text, completeness)
        
        # Calculate ATS score based on resume only
        has_bullets = bool(re.search(r'[•\-\*]\s', resume_text))
        has_sections = sum(completeness['sections_found'].values())
        action_count = sum(1 for verb in nlp.action_verbs if verb in resume_text.lower())
        metrics_count = len(re.findall(r'\d+[%+]', resume_text))
        
        ats_score = int(
            (len(skills_found) / 10 * 25) +
            (has_sections / 6 * 30) +
            (min(action_count, 10) / 10 * 25) +
            (min(metrics_count, 5) / 5 * 20)
        )
        ats_score = min(100, max(20, ats_score))
        
        return {
            "ats_score": ats_score,
            "completeness_score": completeness['score'],
            "skills_found": skills_found,
            "missing_skills": [],
            "strengths": strengths,
            "weaknesses": weaknesses,
            "section_feedback": section_feedback,
            "readability": readability,
            "suggestions": tips,
            "sections_detected": completeness['sections_found'],
            "created_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@router.post("/analyze-resume-pro")
async def analyze_resume_pro(
    resume: UploadFile = File(...),
    target_role: Optional[str] = Form(None)
):
    """Advanced role-aware resume analysis with impact scoring"""
    try:
        from app.advanced_analyzer import AdvancedAnalyzer
        
        # Validate file
        if not resume.filename:
            raise HTTPException(400, "No filename provided")
        
        file_ext = resume.filename.lower().split('.')[-1]
        if file_ext not in ['pdf', 'docx']:
            raise HTTPException(400, "Only PDF and DOCX files supported")
        
        # Extract text
        file_bytes = await resume.read()
        if not file_bytes:
            raise HTTPException(400, "Empty file uploaded")
        
        try:
            if file_ext == 'pdf':
                resume_text = nlp.extract_text_from_pdf(file_bytes)
            else:
                resume_text = nlp.extract_text_from_docx(file_bytes)
        except Exception as e:
            raise HTTPException(400, f"Failed to extract text: {str(e)}")
        
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Resume text too short or empty")
        
        # Normalize and truncate
        resume_text = resume_text[:50000]
        resume_text = re.sub(r'\s+', ' ', resume_text).strip()
        
        # Initialize analyzers
        advanced = AdvancedAnalyzer()
        
        # Run all analysis modules
        skills_found = nlp.extract_skills(resume_text)
        completeness = nlp.analyze_completeness(resume_text)
        role_match = advanced.role_based_skill_matching(resume_text, target_role)
        impact = advanced.bullet_impact_analysis(resume_text)
        professional = advanced.professional_presence_analysis(resume_text)
        career_insights = advanced.career_intelligence_insights(resume_text, len(skills_found), impact)
        
        # Calculate scores
        overall_score = advanced.enhanced_ats_engine(
            resume_text, completeness, impact, professional, role_match
        )
        
        # Generate feedback
        strengths = nlp.analyze_strengths(resume_text)
        weaknesses = nlp.analyze_weaknesses(resume_text)
        section_feedback = nlp.analyze_section_feedback(resume_text)
        suggestions = nlp.generate_actionable_tips(resume_text, completeness)
        
        # Add role-specific suggestions
        if role_match['missing_role_skills']:
            suggestions.insert(0, f"Add missing skills for {target_role}: {', '.join(role_match['missing_role_skills'][:3])}")
        
        return {
            "overall_score": overall_score,
            "ats_score": completeness['score'],
            "role_match_score": role_match['role_match_score'],
            "impact_score": impact['impact_score'],
            "professional_score": professional['professional_score'],
            "completeness_score": completeness['score'],
            "skills_found": skills_found,
            "matched_skills": role_match['matched_skills'],
            "missing_role_skills": role_match['missing_role_skills'],
            "strengths": strengths,
            "weaknesses": weaknesses,
            "section_feedback": section_feedback,
            "career_level_estimation": career_insights['career_level_estimation'],
            "market_readiness": career_insights['market_readiness'],
            "improvement_priority": career_insights['improvement_priority'],
            "suggestions": suggestions,
            "impact_analysis": {
                "strong_bullets": impact['strong_bullets'],
                "weak_bullets": impact['weak_bullets'],
                "strong_verbs": impact['strong_verbs_count'],
                "weak_verbs": impact['weak_verbs_count']
            },
            "professional_presence": {
                "contact_info": professional['contact_info'],
                "missing_items": professional['missing_items']
            },
            "role_analyzed": role_match['role_analyzed'],
            "created_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@router.post("/analyze-resume-intelligent")
async def analyze_resume_intelligent_endpoint(
    resume: UploadFile = File(...),
    target_role: Optional[str] = Form(None),
    user: Optional[dict] = Depends(get_optional_user)
):
    """Intelligent AI-powered resume analysis using Groq"""
    try:
        from app.groq_analyzer import analyze_resume_intelligent
        if not resume.filename:
            raise HTTPException(400, "No filename provided")
        file_ext = resume.filename.lower().split('.')[-1]
        if file_ext != 'pdf':
            raise HTTPException(400, "Only PDF files are supported. Please upload a PDF resume.")
        file_bytes = await resume.read()
        if not file_bytes:
            raise HTTPException(400, "Empty file")
        try:
            resume_text = nlp.extract_text_from_pdf(file_bytes)
        except Exception as e:
            raise HTTPException(400, f"Failed to read PDF file: {str(e)}")
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Resume text too short or empty")
        is_valid, message = nlp.is_valid_resume(resume_text)
        if not is_valid:
            raise HTTPException(400, message)
        result = await analyze_resume_intelligent(resume_text)
        result["created_at"] = datetime.now().isoformat()
        if user:
            save_analysis(user["user_id"], result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@router.get("/history")
async def get_history(user: dict = Depends(get_current_user)):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT id, overall_score, completeness_score, impact_score, role_analyzed,
                   career_level, market_readiness, created_at
            FROM analyses WHERE user_id = %s ORDER BY created_at DESC LIMIT 20
        """, (user["user_id"],))
        rows = c.fetchall()
        items = [
            {
                "id": r[0], "overall_score": r[1], "completeness_score": r[2],
                "impact_score": r[3], "role_analyzed": r[4], "career_level": r[5],
                "market_readiness": r[6], "created_at": r[7].isoformat() if r[7] else None,
                "score_delta": None
            } for r in rows
        ]
        # calculate score delta between consecutive analyses (newest first)
        for i in range(len(items) - 1):
            curr = items[i]["overall_score"]
            prev = items[i + 1]["overall_score"]
            if curr is not None and prev is not None:
                items[i]["score_delta"] = curr - prev
        return items
    finally:
        release_conn(conn)


@router.get("/score-tracker")
async def get_score_tracker(user: dict = Depends(get_current_user)):
    """Return score progression stats for the logged-in user"""
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT overall_score, created_at FROM analyses
            WHERE user_id = %s ORDER BY created_at ASC
        """, (user["user_id"],))
        rows = c.fetchall()
        if not rows:
            return {"scores": [], "best_score": None, "latest_score": None, "total_analyses": 0, "weekly_change": None}
        scores = [{"score": r[0], "date": r[1].isoformat()} for r in rows]
        latest = scores[-1]["score"]
        best = max(r[0] for r in rows if r[0] is not None)
        # weekly change: compare latest vs score from 7 days ago
        from datetime import timedelta, timezone
        week_ago = rows[-1][1] - timedelta(days=7)
        older = [r[0] for r in rows if r[1] <= week_ago and r[0] is not None]
        weekly_change = (latest - older[-1]) if older else None
        return {
            "scores": scores,
            "best_score": best,
            "latest_score": latest,
            "total_analyses": len(rows),
            "weekly_change": weekly_change
        }
    finally:
        release_conn(conn)


@router.post("/generate-assessment")
async def generate_assessment_endpoint(
    resume: UploadFile = File(...),
    user: Optional[dict] = Depends(get_optional_user)
):
    """Generate personalized MCQ assessment from resume using Groq AI"""
    try:
        from app.groq_analyzer import generate_assessment
        if not resume.filename:
            raise HTTPException(400, "No filename provided")
        file_ext = resume.filename.lower().split('.')[-1]
        if file_ext not in ['pdf', 'docx']:
            raise HTTPException(400, "Only PDF and DOCX files supported")
        file_bytes = await resume.read()
        if not file_bytes:
            raise HTTPException(400, "Empty file")
        if file_ext == 'pdf':
            resume_text = nlp.extract_text_from_pdf(file_bytes)
        else:
            resume_text = nlp.extract_text_from_docx(file_bytes)
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Could not extract text from resume")
        is_valid, message = nlp.is_valid_resume(resume_text)
        if not is_valid:
            raise HTTPException(400, message)
        result = await generate_assessment(resume_text)
        result["created_at"] = datetime.now().isoformat()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Assessment generation failed: {str(e)}")


@router.post("/submit-assessment")
async def submit_assessment(
    payload: AssessmentSubmitPayload,
    background_tasks: BackgroundTasks,
    request_user: Optional[dict] = Depends(get_optional_user),
):
    """Submit completed assessment, evaluate MCQ + HR round, and trigger result email."""
    mcq_questions = (payload.mcq_questions or [])[:25]
    if not mcq_questions:
        raise HTTPException(400, "MCQ questions are required for submission")

    mcq_score = 0
    for idx, q in enumerate(mcq_questions):
        expected = q.get("correct")
        selected = payload.mcq_answers.get(str(idx))
        if isinstance(expected, int) and isinstance(selected, int) and selected == expected:
            mcq_score += 1

    hr_items = (payload.hr_answers or [])[:5]
    while len(hr_items) < 5:
        hr_items.append(HRAnswerPayload(question=f"HR Question {len(hr_items)+1}", answer="", time_spent_sec=0))

    hr_feedback = []
    hr_score = 0
    for idx, item in enumerate(hr_items, start=1):
        score = _score_hr_answer(item.answer)
        hr_score += score
        hr_feedback.append(
            {
                "id": idx,
                "question": item.question,
                "score": score,
                "strength": "Structured and relevant response" if score >= 4 else "Attempted response with partial clarity",
                "improvement": "Use concise STAR format with measurable impact." if score < 5 else "Add one quantified business impact example.",
                "time_spent_sec": item.time_spent_sec,
            }
        )

    total_score = mcq_score + hr_score
    top_improvements = [
        "Use STAR format (Situation, Task, Action, Result) in HR answers.",
        "Add quantified impact (percent, revenue, time saved) wherever possible.",
        "Keep answers concise, role-aligned, and outcome-focused.",
    ]

    candidate_email = payload.candidate_email or (request_user.get("email") if request_user else None)
    smtp_configured = bool(os.getenv("SMTP_HOST") and (os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME")))
    result_payload = {
        "candidate_name": payload.candidate_name or "Candidate",
        "candidate_email": candidate_email,
        "role": payload.role or "General",
        "mcq_score": mcq_score,
        "hr_score": hr_score,
        "total_score": total_score,
        "max_score": 50,
        "violation_count": payload.violation_count,
        "mcq_total": len(mcq_questions),
        "hr_feedback": hr_feedback,
        "top_improvements": top_improvements,
        "submitted_at": datetime.now().isoformat(),
    }

    email_requested = bool(candidate_email)
    background_tasks.add_task(_dispatch_result_email, result_payload)
    result_id = _persist_assessment_result(
        request_user.get("user_id") if request_user else None,
        result_payload,
        emailed=False,
    )

    return {
        "ok": True,
        "assessment_result_id": result_id,
        "message": "Assessment completed successfully. Results are being processed and will be shared via email shortly.",
        "email_requested": email_requested,
        "email_configured": smtp_configured,
        "email_warning": None if (email_requested and smtp_configured) else "Email was not dispatched because candidate email or SMTP configuration is missing.",
        "evaluation": result_payload,
    }


@router.post("/cover-letter")
async def cover_letter(
    resume: UploadFile = File(...),
    job_title: str = Form(...),
    company_name: str = Form(...),
    job_description: str = Form(...),
    tone: str = Form("Professional"),
    length: str = Form("Medium"),
    hiring_manager: str = Form(""),
    user: Optional[dict] = Depends(get_optional_user)
):
    """Generate AI cover letter from resume + job details"""
    try:
        from app.groq_analyzer import generate_cover_letter
        if not resume.filename or not resume.filename.lower().endswith('.pdf'):
            raise HTTPException(400, "Only PDF files supported")
        file_bytes = await resume.read()
        if not file_bytes:
            raise HTTPException(400, "Empty file")
        resume_text = nlp.extract_text_from_pdf(file_bytes)
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(400, "Could not extract text from resume")
        result = await generate_cover_letter(resume_text, job_title, company_name, job_description, tone, length, hiring_manager)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Cover letter generation failed: {str(e)}")


def save_analysis(user_id: int, result: dict):
    """Save analysis result to PostgreSQL"""
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO analyses (
                user_id, overall_score, completeness_score, impact_score,
                professional_score, role_match_score, career_level, market_readiness,
                role_analyzed, skills_found, strengths, weaknesses, suggestions, keywords, ai_insights
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_id,
            result.get("overall_score"), result.get("completeness_score"),
            result.get("impact_score"), result.get("professional_score"),
            result.get("role_match_score"), result.get("career_level_estimation"),
            result.get("market_readiness"), result.get("role_analyzed"),
            json.dumps(result.get("skills_found", [])),
            json.dumps(result.get("strengths", [])),
            json.dumps(result.get("weaknesses", [])),
            json.dumps(result.get("suggestions", [])),
            json.dumps(result.get("keywords", {})),
            json.dumps(result.get("ai_insights", {}))
        ))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_conn(conn)


@router.post("/assessment-violation")
async def log_assessment_violation(
    payload: AssessmentViolationPayload,
    request_user: Optional[dict] = Depends(get_optional_user),
):
    """Persist online-test violation signals for proctoring and auditing."""
    conn = get_conn()
    try:
        c = conn.cursor()
        metadata = {
            "reported_at": payload.timestamp or datetime.now().isoformat(),
        }
        c.execute(
            """
            INSERT INTO assessment_violations (user_id, assessment_role, reason, violation_count, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (
                request_user.get("user_id") if request_user else None,
                payload.assessment_role,
                payload.reason.strip(),
                payload.violation_count,
                json.dumps(metadata),
            ),
        )
        row = c.fetchone()
        conn.commit()
        return {
            "ok": True,
            "violation_id": row[0],
            "created_at": row[1].isoformat() if row and row[1] else None,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"Failed to save violation: {str(e)}")
    finally:
        release_conn(conn)


@router.post("/download-report")
async def download_report(analysis_data: dict = Body(...)):
    """Generate PDF report from analysis data"""
    try:
        from fastapi.responses import Response
        from datetime import datetime
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from io import BytesIO
        
        if not analysis_data:
            raise HTTPException(400, "Invalid analysis data")
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1e40af'), spaceAfter=6)
        story.append(Paragraph("AI Resume Analysis Report", title_style))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Scores Table
        score_data = [['Metric', 'Score']]
        if 'overall_score' in analysis_data:
            score_data.append(['Overall Score', f"{analysis_data['overall_score']}%"])
        if 'completeness_score' in analysis_data:
            score_data.append(['Completeness', f"{analysis_data['completeness_score']}%"])
        if 'impact_score' in analysis_data:
            score_data.append(['Impact', f"{analysis_data['impact_score']}%"])
        if 'professional_score' in analysis_data:
            score_data.append(['Professional', f"{analysis_data['professional_score']}%"])
        
        if len(score_data) > 1:
            score_table = Table(score_data, colWidths=[3*inch, 2*inch])
            score_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            story.append(score_table)
            story.append(Spacer(1, 0.3*inch))
        
        # Strengths
        if 'strengths' in analysis_data and analysis_data['strengths']:
            story.append(Paragraph("Strengths", styles['Heading2']))
            for strength in analysis_data['strengths']:
                story.append(Paragraph(f"• {strength}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Weaknesses
        if 'weaknesses' in analysis_data and analysis_data['weaknesses']:
            story.append(Paragraph("Areas for Improvement", styles['Heading2']))
            for weakness in analysis_data['weaknesses']:
                story.append(Paragraph(f"• {weakness}", styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Skills
        if 'skills_found' in analysis_data and analysis_data['skills_found']:
            story.append(Paragraph("Skills Identified", styles['Heading2']))
            story.append(Paragraph(", ".join(analysis_data['skills_found']), styles['Normal']))
            story.append(Spacer(1, 0.2*inch))
        
        # Priority Actions
        if 'improvement_priority' in analysis_data and analysis_data['improvement_priority']:
            story.append(Paragraph("Top Priority Actions", styles['Heading2']))
            for idx, priority in enumerate(analysis_data['improvement_priority'], 1):
                story.append(Paragraph(f"{idx}. {priority}", styles['Normal']))
        
        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=AI_Resume_Analysis_Report.pdf"}
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"PDF generation failed: {str(e)}")
