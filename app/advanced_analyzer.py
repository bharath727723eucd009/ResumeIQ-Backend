import re
from typing import List, Dict, Optional
from collections import Counter

class AdvancedAnalyzer:
    def __init__(self):
        self.role_skills_map = {
            'software engineer': ['python', 'java', 'javascript', 'git', 'sql', 'rest api', 'agile', 'docker', 'aws'],
            'data scientist': ['python', 'machine learning', 'sql', 'statistics', 'pandas', 'tensorflow', 'data analysis'],
            'frontend developer': ['javascript', 'react', 'html', 'css', 'typescript', 'vue', 'angular', 'redux'],
            'backend developer': ['python', 'java', 'node.js', 'sql', 'mongodb', 'rest api', 'microservices', 'docker'],
            'devops engineer': ['docker', 'kubernetes', 'aws', 'ci/cd', 'jenkins', 'terraform', 'linux', 'ansible'],
            'full stack developer': ['javascript', 'react', 'node.js', 'python', 'sql', 'mongodb', 'git', 'rest api'],
            'product manager': ['agile', 'product strategy', 'roadmap', 'stakeholder', 'analytics', 'user research'],
            'data engineer': ['python', 'sql', 'spark', 'kafka', 'airflow', 'aws', 'data pipeline', 'etl']
        }
        
        self.strong_verbs = [
            'led', 'developed', 'engineered', 'architected', 'designed', 'implemented',
            'launched', 'delivered', 'optimized', 'improved', 'increased', 'reduced',
            'achieved', 'spearheaded', 'established', 'built', 'created', 'managed'
        ]
        
        self.weak_verbs = [
            'worked', 'responsible', 'helped', 'assisted', 'involved', 'participated',
            'contributed', 'supported', 'handled', 'dealt'
        ]
        
        self.tech_skills = [
            'python', 'javascript', 'java', 'c++', 'typescript', 'react', 'angular', 'vue',
            'node.js', 'express', 'django', 'flask', 'spring boot', 'fastapi',
            'sql', 'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
            'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'jenkins', 'terraform',
            'git', 'ci/cd', 'rest api', 'graphql', 'microservices', 'agile',
            'machine learning', 'ai', 'data science', 'tensorflow', 'pytorch'
        ]
    
    def role_based_skill_matching(self, resume_text: str, target_role: Optional[str] = None) -> Dict:
        """Match resume skills against target role requirements"""
        resume_lower = resume_text.lower()
        found_skills = [skill for skill in self.tech_skills if skill in resume_lower]
        
        if not target_role or target_role.lower() not in self.role_skills_map:
            return {
                'role_match_score': 0,
                'matched_skills': found_skills,
                'missing_role_skills': [],
                'role_analyzed': None
            }
        
        role_key = target_role.lower()
        required_skills = self.role_skills_map[role_key]
        matched = [s for s in required_skills if s in resume_lower]
        missing = [s for s in required_skills if s not in resume_lower]
        
        role_match_score = int((len(matched) / len(required_skills)) * 100) if required_skills else 0
        
        return {
            'role_match_score': role_match_score,
            'matched_skills': matched,
            'missing_role_skills': missing,
            'role_analyzed': target_role
        }
    
    def bullet_impact_analysis(self, resume_text: str) -> Dict:
        """Analyze bullet points for impact and metrics"""
        lines = [l.strip() for l in resume_text.split('\n') if l.strip()]
        
        # Detect bullets
        bullet_lines = [l for l in lines if re.match(r'^[•\-\*]\s', l)]
        
        # Count metrics (numbers with %, +, K, M, etc.)
        metrics_pattern = r'\d+[%+]|\d+[KMB]|\d+\+|\d+x'
        strong_bullets = [l for l in bullet_lines if re.search(metrics_pattern, l)]
        
        # Count strong vs weak verbs
        strong_count = sum(1 for verb in self.strong_verbs if verb in resume_text.lower())
        weak_count = sum(1 for verb in self.weak_verbs if verb in resume_text.lower())
        
        # Calculate impact score
        metrics_score = min(50, len(strong_bullets) * 10)
        verb_score = min(50, strong_count * 5 - weak_count * 3)
        impact_score = max(0, min(100, metrics_score + verb_score))
        
        return {
            'impact_score': impact_score,
            'strong_bullets': len(strong_bullets),
            'weak_bullets': len(bullet_lines) - len(strong_bullets),
            'strong_verbs_count': strong_count,
            'weak_verbs_count': weak_count,
            'total_bullets': len(bullet_lines)
        }
    
    def professional_presence_analysis(self, resume_text: str) -> Dict:
        """Analyze professional presence and contact information"""
        resume_lower = resume_text.lower()
        
        checks = {
            'email': bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_text)),
            'phone': bool(re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|\+\d{1,3}\s?\d+', resume_text)),
            'linkedin': 'linkedin' in resume_lower,
            'github': 'github' in resume_lower or 'git' in resume_lower
        }
        
        # Check for informal language
        informal_words = ['gonna', 'wanna', 'yeah', 'cool', 'awesome', 'stuff']
        has_informal = any(word in resume_lower for word in informal_words)
        
        present_count = sum(checks.values())
        professional_score = int((present_count / len(checks)) * 100)
        
        if has_informal:
            professional_score = max(0, professional_score - 20)
        
        missing = [k for k, v in checks.items() if not v]
        
        return {
            'professional_score': professional_score,
            'contact_info': checks,
            'missing_items': missing,
            'has_informal_language': has_informal
        }
    
    def enhanced_ats_engine(self, resume_text: str, completeness: Dict, 
                           impact: Dict, professional: Dict, role_match: Dict) -> int:
        """Calculate weighted overall ATS score"""
        weights = {
            'completeness': 0.25,
            'impact': 0.25,
            'professional': 0.20,
            'role_match': 0.15,
            'structure': 0.15
        }
        
        # Structure score
        has_bullets = bool(re.search(r'[•\-\*]\s', resume_text))
        word_count = len(resume_text.split())
        optimal_length = 300 <= word_count <= 1000
        structure_score = (50 if has_bullets else 0) + (50 if optimal_length else 0)
        
        # Calculate weighted score
        overall = (
            completeness['score'] * weights['completeness'] +
            impact['impact_score'] * weights['impact'] +
            professional['professional_score'] * weights['professional'] +
            role_match['role_match_score'] * weights['role_match'] +
            structure_score * weights['structure']
        )
        
        return int(min(100, max(20, overall)))
    
    def career_intelligence_insights(self, resume_text: str, skills_count: int, 
                                    impact: Dict) -> Dict:
        """Estimate career level and provide insights"""
        resume_lower = resume_text.lower()
        
        # Estimate career level
        years_match = re.search(r'(\d+)\+?\s*years?', resume_lower)
        years = int(years_match.group(1)) if years_match else 0
        
        if years >= 7 or 'senior' in resume_lower or 'lead' in resume_lower:
            career_level = 'Senior'
        elif years >= 3 or 'mid' in resume_lower:
            career_level = 'Mid-Level'
        else:
            career_level = 'Fresher/Junior'
        
        # Market readiness
        has_metrics = impact['strong_bullets'] >= 3
        has_skills = skills_count >= 5
        has_projects = 'project' in resume_lower
        
        readiness_score = sum([has_metrics, has_skills, has_projects])
        
        if readiness_score >= 3:
            market_readiness = 'High - Ready for applications'
        elif readiness_score == 2:
            market_readiness = 'Medium - Needs minor improvements'
        else:
            market_readiness = 'Low - Requires significant updates'
        
        # Top 3 priorities
        priorities = []
        if impact['strong_bullets'] < 3:
            priorities.append('Add quantified achievements with metrics')
        if skills_count < 5:
            priorities.append('Expand technical skills section')
        if not has_projects:
            priorities.append('Include relevant projects')
        if impact['weak_verbs_count'] > 3:
            priorities.append('Replace weak verbs with strong action words')
        if not priorities:
            priorities = ['Tailor resume for specific roles', 'Add more recent achievements', 'Update skills section']
        
        return {
            'career_level_estimation': career_level,
            'market_readiness': market_readiness,
            'improvement_priority': priorities[:3]
        }
