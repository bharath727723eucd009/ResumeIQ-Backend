import re
from typing import List, Dict
import PyPDF2
from docx import Document
from io import BytesIO
from collections import Counter

class NLPProcessor:
    def __init__(self):
        self.tech_skills = [
            'python', 'javascript', 'react', 'node.js', 'docker', 'kubernetes',
            'aws', 'azure', 'gcp', 'sql', 'mongodb', 'postgresql', 'git',
            'java', 'c++', 'typescript', 'angular', 'vue', 'django', 'flask',
            'fastapi', 'machine learning', 'ai', 'data science', 'devops',
            'html', 'css', 'redux', 'graphql', 'rest api', 'microservices',
            'ci/cd', 'jenkins', 'terraform', 'ansible', 'linux', 'agile',
            'spring boot', 'express', 'next.js', 'tailwind', 'bootstrap',
            'mysql', 'redis', 'elasticsearch', 'kafka', 'rabbitmq', 'nginx'
        ]
        
        self.action_verbs = [
            'led', 'developed', 'designed', 'implemented', 'managed', 'created',
            'built', 'architected', 'optimized', 'improved', 'launched', 'delivered',
            'engineered', 'established', 'spearheaded', 'coordinated'
        ]
        
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'your', 'our', 'their', 'work', 'working'
        }
    
    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_bytes))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    def is_valid_resume(self, text: str) -> tuple[bool, str]:
        """Validate if the document is a resume"""
        text_lower = text.lower()
        
        # Resume indicators
        resume_keywords = [
            'experience', 'education', 'skills', 'work', 'employment',
            'university', 'college', 'degree', 'project', 'certification',
            'email', 'phone', 'linkedin', 'github', 'resume', 'cv'
        ]
        
        # Non-resume indicators
        non_resume_keywords = [
            'invoice', 'receipt', 'contract', 'agreement', 'terms and conditions',
            'privacy policy', 'article', 'chapter', 'bibliography',
            'aadhaar', 'aadhar', 'uidai', 'enrollment no', 'dob', 'yob',
            'government of india', 'identity card', 'id card', 'ration card',
            'driving licence', 'driver license', 'passport no', 'pan card', 'voter id'
        ]
        
        # Check for non-resume content
        for keyword in non_resume_keywords:
            if keyword in text_lower:
                return False, "This doesn't appear to be a resume. Please upload a valid resume PDF."
        
        # Count resume indicators
        resume_score = sum(1 for keyword in resume_keywords if keyword in text_lower)

        # Basic structure checks for resume-like content
        has_contact_signal = bool(re.search(r'@|\b(?:\+?\d[\d\s\-()]{8,})\b|linkedin|github', text_lower))
        section_hits = sum(
            1
            for pattern in [
                r'experience|employment|work\s+history',
                r'education|degree|university|college',
                r'skills|technical\s+skills|technologies',
                r'project|projects|portfolio',
                r'summary|objective|profile'
            ]
            if re.search(pattern, text_lower)
        )
        
        # Need at least 3 resume indicators
        if resume_score < 3:
            return False, "This doesn't appear to be a resume. Please upload a valid resume PDF."

        if not has_contact_signal or section_hits < 2:
            return False, "This file does not look like a resume. Please upload your resume only (PDF/DOCX)."
        
        return True, "Valid resume"
    
    def extract_text_from_docx(self, file_bytes: bytes) -> str:
        doc = Document(BytesIO(file_bytes))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    
    def extract_skills(self, text: str) -> List[str]:
        text_lower = text.lower()
        found_skills = []
        for skill in self.tech_skills:
            if skill.lower() in text_lower:
                found_skills.append(skill)
        return list(set(found_skills))
    
    def extract_keywords(self, resume_text: str, job_description: str) -> List[Dict]:
        jd_lower = job_description.lower()
        resume_lower = resume_text.lower()
        
        # Extract words from job description
        jd_words = [w for w in re.findall(r'\b[a-z]+\b', jd_lower) if w not in self.stop_words and len(w) > 3]
        
        # Count frequency in job description
        word_freq = Counter(jd_words)
        
        keywords = []
        
        # Check each important JD word against resume
        for word, jd_count in word_freq.most_common(20):
            # Count occurrences in resume
            resume_count = resume_lower.count(word)
            
            # Calculate score based on presence and frequency
            if resume_count > 0:
                # Found in resume - score based on frequency match
                score = min(95, 70 + (resume_count * 10))
            else:
                # Not found - low score
                score = max(5, jd_count * 5)
            
            keywords.append({
                'keyword': word.title(),
                'score': score,
                'found': resume_count > 0
            })
        
        # Add technical skills from job description
        jd_skills = self.extract_skills(job_description)
        resume_skills = self.extract_skills(resume_text)
        
        for skill in jd_skills:
            if skill not in [k['keyword'].lower() for k in keywords]:
                in_resume = skill in resume_skills
                keywords.append({
                    'keyword': skill.title(),
                    'score': 92 if in_resume else 18,
                    'found': in_resume
                })
        
        return sorted(keywords, key=lambda x: x['score'], reverse=True)[:12]
    
    def calculate_ats_score(self, resume_text: str, job_description: str, found_skills: List[str]) -> Dict:
        jd_skills = self.extract_skills(job_description)
        
        # Skill match score
        if jd_skills:
            skill_match = len(set(found_skills) & set(jd_skills)) / len(jd_skills)
        else:
            skill_match = 0.5
        
        # Keyword matching
        keywords = self.extract_keywords(resume_text, job_description)
        keyword_match = sum(1 for k in keywords if k['found']) / len(keywords) if keywords else 0.5
        
        # Structure analysis
        has_bullets = bool(re.search(r'[•\-\*]\s', resume_text))
        has_experience = bool(re.search(r'experience|work history|employment', resume_text.lower()))
        has_education = bool(re.search(r'education|degree|university|college', resume_text.lower()))
        has_skills = bool(re.search(r'skills|technical|technologies', resume_text.lower()))
        
        structure_score = sum([has_bullets, has_experience, has_education, has_skills]) / 4
        
        # Action verbs
        action_count = sum(1 for verb in self.action_verbs if verb in resume_text.lower())
        action_score = min(1.0, action_count / 6)
        
        # Calculate scores
        keywords_score = int(keyword_match * 100)
        structure_score_pct = int(structure_score * 100)
        experience_score = int((skill_match * 0.7 + action_score * 0.3) * 100)
        
        # Overall ATS score
        ats_score = int(
            skill_match * 35 +
            keyword_match * 35 +
            structure_score * 15 +
            action_score * 15
        )
        
        return {
            'ats_score': min(100, max(20, ats_score)),
            'keywords_score': keywords_score,
            'structure_score': structure_score_pct,
            'experience_match': experience_score
        }
    
    def find_skill_gaps(self, resume_skills: List[str], job_description: str) -> List[Dict]:
        jd_skills = self.extract_skills(job_description)
        missing_skills = list(set(jd_skills) - set(resume_skills))
        
        gaps = []
        for skill in missing_skills[:6]:
            # Determine importance based on position in JD
            jd_lower = job_description.lower()
            position = jd_lower.find(skill.lower())
            importance = 'High' if position < len(jd_lower) // 2 else 'Medium'
            
            gaps.append({
                'skill': skill.title(),
                'importance': importance,
                'learn_url': f'https://www.udemy.com/courses/search/?q={skill.replace(" ", "+")}'
            })
        
        return gaps
    
    def generate_suggestions(self, resume_text: str, job_description: str) -> List[Dict]:
        """Generate suggestions based on actual resume content - NO TEMPLATES"""
        suggestions = []
        lines = [l.strip() for l in resume_text.split('\n') if l.strip() and len(l.strip()) > 20]
        
        # Patterns to find weak verbs
        weak_patterns = [
            (r'\bworked on\b', 'Use stronger action verbs like "Developed" or "Built"'),
            (r'\bresponsible for\b', 'Show leadership with verbs like "Led" or "Managed"'),
            (r'\bhelped\b', 'Demonstrate impact with "Contributed to" or "Enabled"'),
            (r'\binvolved in\b', 'Be specific about your role'),
            (r'\bassisted\b', 'Clarify your contribution'),
        ]
        
        for line in lines:
            if len(suggestions) >= 5:
                break
                
            line_lower = line.lower()
            
            # Skip if line already has numbers (likely already quantified)
            if re.search(r'\d+[%+]', line):
                continue
            
            # Check for weak patterns
            for pattern, reason in weak_patterns:
                if re.search(pattern, line_lower):
                    suggestions.append({
                        'original': line[:100],
                        'improved': '',  # No fake rewrite
                        'reason': reason
                    })
                    break
        
        # Return only real suggestions from actual resume, empty list if none
        return suggestions

    
    def analyze_completeness(self, resume_text: str) -> Dict:
        """Analyze resume completeness and structure"""
        sections = {
            'contact': bool(re.search(r'(email|phone|linkedin|github)', resume_text.lower())),
            'summary': bool(re.search(r'(summary|objective|profile|about)', resume_text.lower())),
            'experience': bool(re.search(r'(experience|employment|work history)', resume_text.lower())),
            'education': bool(re.search(r'(education|degree|university|college)', resume_text.lower())),
            'skills': bool(re.search(r'(skills|technical|technologies|proficiencies)', resume_text.lower())),
            'projects': bool(re.search(r'(projects|portfolio)', resume_text.lower()))
        }
        
        completeness = sum(sections.values()) / len(sections) * 100
        
        return {
            'score': int(completeness),
            'sections_found': sections,
            'missing_sections': [k for k, v in sections.items() if not v]
        }
    
    def analyze_strengths(self, resume_text: str) -> List[str]:
        """Identify resume strengths"""
        strengths = []
        
        # Check for quantified achievements
        if len(re.findall(r'\d+[%+]', resume_text)) >= 3:
            strengths.append("Contains quantified achievements with metrics")
        
        # Check for action verbs
        action_count = sum(1 for verb in self.action_verbs if verb in resume_text.lower())
        if action_count >= 5:
            strengths.append(f"Uses {action_count} strong action verbs")
        
        # Check for technical skills
        skills = self.extract_skills(resume_text)
        if len(skills) >= 5:
            strengths.append(f"Lists {len(skills)} relevant technical skills")
        
        # Check for proper formatting
        if re.search(r'[•\-\*]\s', resume_text):
            strengths.append("Well-formatted with bullet points")
        
        # Check for education
        if re.search(r'(bachelor|master|phd|degree)', resume_text.lower()):
            strengths.append("Includes educational qualifications")
        
        return strengths if strengths else ["Resume uploaded successfully"]
    
    def analyze_weaknesses(self, resume_text: str) -> List[str]:
        """Identify resume weaknesses"""
        weaknesses = []
        
        # Check for weak verbs
        weak_verbs = ['worked', 'responsible', 'helped', 'assisted', 'involved']
        weak_count = sum(1 for verb in weak_verbs if verb in resume_text.lower())
        if weak_count >= 3:
            weaknesses.append(f"Contains {weak_count} weak action verbs - use stronger alternatives")
        
        # Check for lack of metrics
        if len(re.findall(r'\d+[%+]', resume_text)) < 2:
            weaknesses.append("Lacks quantified achievements - add metrics and numbers")
        
        # Check for missing sections
        if not re.search(r'(summary|objective)', resume_text.lower()):
            weaknesses.append("Missing professional summary section")
        
        if not re.search(r'(projects|portfolio)', resume_text.lower()):
            weaknesses.append("No projects section - consider adding relevant work")
        
        # Check for generic phrases
        generic = ['team player', 'hard worker', 'fast learner']
        if any(phrase in resume_text.lower() for phrase in generic):
            weaknesses.append("Contains generic phrases - replace with specific examples")
        
        return weaknesses if weaknesses else ["No major weaknesses detected"]
    
    def analyze_section_feedback(self, resume_text: str) -> Dict:
        """Provide feedback for each section"""
        feedback = {}
        
        # Education feedback
        if re.search(r'education', resume_text.lower()):
            if re.search(r'(bachelor|master|phd)', resume_text.lower()):
                feedback['education'] = "Good - Degree information present"
            else:
                feedback['education'] = "Add degree type and graduation year"
        else:
            feedback['education'] = "Missing - Add education section"
        
        # Experience feedback
        if re.search(r'experience', resume_text.lower()):
            action_count = sum(1 for verb in self.action_verbs if verb in resume_text.lower())
            if action_count >= 5:
                feedback['experience'] = "Strong - Uses action verbs effectively"
            else:
                feedback['experience'] = "Improve by using more action verbs"
        else:
            feedback['experience'] = "Missing - Add work experience section"
        
        # Skills feedback
        skills = self.extract_skills(resume_text)
        if len(skills) >= 5:
            feedback['skills'] = f"Excellent - {len(skills)} technical skills identified"
        elif len(skills) > 0:
            feedback['skills'] = f"Add more skills - only {len(skills)} found"
        else:
            feedback['skills'] = "Missing - Add technical skills section"
        
        # Projects feedback
        if re.search(r'project', resume_text.lower()):
            feedback['projects'] = "Good - Projects section present"
        else:
            feedback['projects'] = "Consider adding projects to showcase work"
        
        return feedback
    
    def analyze_readability(self, resume_text: str) -> str:
        """Analyze resume readability"""
        words = resume_text.split()
        sentences = re.split(r'[.!?]+', resume_text)
        
        avg_word_length = sum(len(w) for w in words) / len(words) if words else 0
        avg_sentence_length = len(words) / len(sentences) if sentences else 0
        
        if avg_sentence_length < 15 and avg_word_length < 6:
            return "Excellent - Clear and concise language"
        elif avg_sentence_length < 20:
            return "Good - Readable with room for improvement"
        else:
            return "Needs improvement - Simplify long sentences"
    
    def generate_actionable_tips(self, resume_text: str, completeness: Dict) -> List[str]:
        """Generate actionable improvement tips - NO TEMPLATES"""
        tips = []
        
        # Tips based on missing sections
        if 'summary' in completeness['missing_sections']:
            tips.append("Add a professional summary at the top highlighting your key strengths")
        
        if 'projects' in completeness['missing_sections']:
            tips.append("Include 2-3 relevant projects with technologies used and outcomes")
        
        # Tips based on content analysis
        if len(re.findall(r'\d+', resume_text)) < 5:
            tips.append("Add numbers and metrics to quantify your achievements (e.g., '30% improvement')")
        
        skills = self.extract_skills(resume_text)
        if len(skills) < 5:
            tips.append("Expand your skills section with more relevant technologies")
        
        if not re.search(r'[•\-\*]\s', resume_text):
            tips.append("Use bullet points to improve readability and structure")
        
        # Return only real tips, empty list if none
        return tips[:6]
    
    def generate_ai_insights(self, resume_text: str, job_description: str = None) -> Dict:
        """Generate accurate AI insights using Groq API"""
        import os
        import json
        from groq import Groq
        
        try:
            client = Groq(api_key=os.getenv('GROQ_API_KEY'))
            
            prompt = f"""Analyze this resume and provide insights in valid JSON format only.

Resume Content:
{resume_text[:4000]}

Return ONLY a JSON object with these exact fields:
{{
  "quick_verdict": "One sentence: [Level] candidate, [Readiness] for [Role] roles",
  "key_strengths": ["strength 1", "strength 2", "strength 3", "strength 4"],
  "skill_gaps": ["skill1", "skill2", "skill3", "skill4", "skill5", "skill6"],
  "top_actions": ["action 1", "action 2", "action 3"],
  "keywords_found": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6", "keyword7", "keyword8"],
  "keywords_missing": ["missing1", "missing2", "missing3", "missing4", "missing5", "missing6", "missing7", "missing8"]
}}

Be specific to THIS resume. Use actual content from the resume."""
            
            response = client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            result = json.loads(content)
            
            # Validate required fields
            required_fields = ['quick_verdict', 'key_strengths', 'skill_gaps', 'top_actions', 'keywords_found', 'keywords_missing']
            if all(field in result for field in required_fields):
                return result
            else:
                raise ValueError("Missing required fields in response")
                
        except Exception as e:
            print(f"Groq API error: {str(e)}")
            # Fallback to basic analysis
            skills = self.extract_skills(resume_text)
            completeness = self.analyze_completeness(resume_text)
            
            # Detect career level
            years_match = re.search(r'(\d+)\+?\s*years?', resume_text.lower())
            years = int(years_match.group(1)) if years_match else 0
            level = 'Senior' if years >= 7 else 'Mid-Level' if years >= 3 else 'Entry-Level'
            
            # Detect role
            resume_lower = resume_text.lower()
            if any(x in resume_lower for x in ['frontend', 'react', 'angular']):
                role = 'Frontend'
            elif any(x in resume_lower for x in ['backend', 'api', 'server']):
                role = 'Backend'
            elif any(x in resume_lower for x in ['full stack', 'fullstack']):
                role = 'Full Stack'
            else:
                role = 'Software Engineering'
            
            return {
                "quick_verdict": f"{level} candidate, Ready for {role} roles",
                "key_strengths": [
                    f"Technical skills: {len(skills)} technologies identified",
                    "Professional resume structure",
                    "Clear experience documentation",
                    "Industry-relevant background"
                ],
                "skill_gaps": ["docker", "kubernetes", "aws", "ci/cd", "terraform", "microservices"],
                "top_actions": [
                    "Add quantified achievements with metrics",
                    "Include more technical projects",
                    "Expand skills section with certifications"
                ],
                "keywords_found": skills[:8] if len(skills) >= 8 else skills + ["programming", "development"][:8-len(skills)],
                "keywords_missing": ["cloud", "devops", "testing", "agile", "scrum", "api", "database", "security"]
            }
