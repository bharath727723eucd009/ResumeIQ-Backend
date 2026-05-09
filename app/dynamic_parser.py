import re
from typing import List, Dict, Tuple
from collections import Counter

class DynamicResumeParser:
    def __init__(self):
        self.strong_verbs = [
            'led', 'developed', 'engineered', 'architected', 'designed', 'implemented',
            'launched', 'delivered', 'optimized', 'improved', 'increased', 'reduced',
            'achieved', 'spearheaded', 'established', 'built', 'created', 'managed',
            'directed', 'coordinated', 'executed', 'streamlined', 'accelerated'
        ]
        
        self.weak_verbs = [
            'worked', 'responsible', 'helped', 'assisted', 'involved', 'participated',
            'contributed', 'supported', 'handled', 'dealt', 'tried', 'attempted'
        ]
        
        self.section_headers = {
            'contact': r'(contact|personal\s+information)',
            'summary': r'(summary|objective|profile|about\s+me)',
            'experience': r'(experience|employment|work\s+history|professional\s+experience)',
            'education': r'(education|academic|qualifications)',
            'skills': r'(skills|technical\s+skills|technologies|competencies)',
            'projects': r'(projects|portfolio|personal\s+projects)'
        }
        
        self.tech_skills = [
            'python', 'javascript', 'java', 'c++', 'c#', 'typescript', 'react', 'angular', 'vue',
            'node.js', 'express', 'django', 'flask', 'spring boot', 'fastapi', '.net',
            'sql', 'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch', 'cassandra',
            'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'jenkins', 'terraform', 'ansible',
            'git', 'ci/cd', 'rest api', 'graphql', 'microservices', 'agile', 'scrum',
            'machine learning', 'ai', 'deep learning', 'data science', 'tensorflow', 'pytorch',
            'html', 'css', 'sass', 'tailwind', 'bootstrap', 'webpack', 'babel'
        ]
    
    def parse_resume(self, resume_text: str) -> Dict:
        """Parse resume into structured sections"""
        sections = self._extract_sections(resume_text)
        bullets = self._extract_bullets(resume_text)
        metrics = self._extract_metrics(resume_text)
        skills = self._extract_skills(resume_text)
        verb_analysis = self._analyze_verbs(resume_text)
        
        return {
            'sections': sections,
            'bullets': bullets,
            'metrics_count': len(metrics),
            'metrics': metrics,
            'strong_verbs_count': verb_analysis['strong_count'],
            'weak_verbs_count': verb_analysis['weak_count'],
            'skills_found': skills,
            'total_words': len(resume_text.split()),
            'has_contact': sections['contact']['found'],
            'has_summary': sections['summary']['found'],
            'has_experience': sections['experience']['found'],
            'has_education': sections['education']['found'],
            'has_skills': sections['skills']['found'],
            'has_projects': sections['projects']['found']
        }
    
    def _extract_sections(self, text: str) -> Dict:
        """Detect which sections are present in resume"""
        sections = {}
        text_lower = text.lower()
        
        for section_name, pattern in self.section_headers.items():
            match = re.search(pattern, text_lower)
            sections[section_name] = {
                'found': bool(match),
                'position': match.start() if match else -1
            }
        
        return sections
    
    def _extract_bullets(self, text: str) -> List[str]:
        """Extract bullet points and action-oriented sentences from resume"""
        lines = text.split('\n')
        bullets = []
        
        # Section headers to skip
        section_keywords = ['skills', 'education', 'experience', 'projects', 'certifications', 
                          'summary', 'objective', 'contact', 'profile', 'about']
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if len(line) < 25:
                continue
            
            # Skip section headers
            line_lower = line.lower()
            if any(line_lower.startswith(keyword) or line_lower == keyword for keyword in section_keywords):
                continue
            
            # Extract bullets with symbols
            if re.match(r'^[•\-\*\u2022\u2023\u25E6\u2043\u2219]\s+', line):
                bullet_text = re.sub(r'^[•\-\*\u2022\u2023\u25E6\u2043\u2219]\s+', '', line)
                if len(bullet_text) > 20:
                    bullets.append(bullet_text)
            # Extract lines starting with strong action verbs (even without bullet symbols)
            elif any(line_lower.startswith(verb) for verb in self.strong_verbs):
                bullets.append(line)
            # Extract sentences that look like accomplishments
            elif re.search(r'\d+[%+xKMB]|\$\d+', line) and len(line.split()) >= 5:
                bullets.append(line)
        
        return bullets
    
    def _extract_metrics(self, text: str) -> List[str]:
        """Extract measurable metrics from text"""
        # Patterns for metrics: percentages, numbers with units, dollar amounts
        patterns = [
            r'\d+%',  # 50%
            r'\d+\+',  # 10+
            r'\d+x',  # 5x
            r'\$\d+[KMB]?',  # $50K, $1M
            r'\d+[KMB]\+?',  # 10K, 5M+
            r'\d+\s*(?:million|thousand|billion)',  # 5 million
            r'(?:increased|decreased|improved|reduced|grew)\s+(?:by\s+)?\d+%?'  # increased by 30%
        ]
        
        metrics = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            metrics.extend(matches)
        
        return list(set(metrics))
    
    def _extract_skills(self, text: str) -> List[str]:
        """Extract technical skills from resume"""
        text_lower = text.lower()
        found_skills = []
        
        for skill in self.tech_skills:
            if skill.lower() in text_lower:
                found_skills.append(skill)
        
        return list(set(found_skills))
    
    def _analyze_verbs(self, text: str) -> Dict:
        """Count strong vs weak action verbs"""
        text_lower = text.lower()
        
        strong_count = sum(1 for verb in self.strong_verbs if re.search(r'\b' + verb + r'\b', text_lower))
        weak_count = sum(1 for verb in self.weak_verbs if re.search(r'\b' + verb + r'\b', text_lower))
        
        return {
            'strong_count': strong_count,
            'weak_count': weak_count,
            'strong_verbs': [v for v in self.strong_verbs if re.search(r'\b' + v + r'\b', text_lower)],
            'weak_verbs': [v for v in self.weak_verbs if re.search(r'\b' + v + r'\b', text_lower)]
        }
    
    def analyze_bullets(self, bullets: List[str]) -> List[Dict]:
        """Analyze each bullet point for quality"""
        analyzed = []
        
        for bullet in bullets:
            bullet_lower = bullet.lower()
            
            # Check for metrics
            has_metric = bool(re.search(r'\d+[%+xKMB]|\$\d+', bullet))
            
            # Check if starts with strong verb
            starts_with_strong = any(bullet_lower.startswith(verb) for verb in self.strong_verbs)
            starts_with_weak = any(bullet_lower.startswith(verb) for verb in self.weak_verbs)
            
            # Detect issues
            issues = []
            tips = []
            
            if not has_metric:
                issues.append('No quantifiable metrics')
                tips.append('Add specific numbers or percentages to show impact')
            
            if starts_with_weak:
                issues.append('Starts with weak verb')
                tips.append('Replace with stronger action verb (led, developed, engineered)')
            elif not starts_with_strong:
                issues.append('Does not start with action verb')
                tips.append('Begin with strong action verb')
            
            if len(bullet.split()) < 5:
                issues.append('Too brief')
                tips.append('Add more context and impact details')
            
            analyzed.append({
                'original': bullet,
                'has_metric': has_metric,
                'starts_with_strong_verb': starts_with_strong,
                'starts_with_weak_verb': starts_with_weak,
                'issues': issues,
                'improvement_tips': tips,
                'word_count': len(bullet.split())
            })
        
        return analyzed
    
    def calculate_dynamic_scores(self, parsed_data: Dict, bullet_analysis: List[Dict]) -> Dict:
        """Calculate scores based on actual resume content"""
        
        # Completeness score (0-100)
        sections_present = sum([
            parsed_data['has_contact'],
            parsed_data['has_summary'],
            parsed_data['has_experience'],
            parsed_data['has_education'],
            parsed_data['has_skills'],
            parsed_data['has_projects']
        ])
        completeness_score = int((sections_present / 6) * 100)
        
        # Impact score (0-100)
        total_bullets = len(bullet_analysis)
        if total_bullets > 0:
            bullets_with_metrics = sum(1 for b in bullet_analysis if b['has_metric'])
            bullets_with_strong_verbs = sum(1 for b in bullet_analysis if b['starts_with_strong_verb'])
            
            impact_score = int(
                (bullets_with_metrics / total_bullets * 50) +
                (bullets_with_strong_verbs / total_bullets * 50)
            )
        else:
            impact_score = 0
        
        # Professional score (0-100)
        has_email = bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', parsed_data.get('raw_text', '')))
        has_phone = bool(re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', parsed_data.get('raw_text', '')))
        
        professional_score = int(
            (parsed_data['has_contact'] * 30) +
            (has_email * 35) +
            (has_phone * 35)
        )
        
        # Overall score (weighted average)
        overall_score = int(
            completeness_score * 0.30 +
            impact_score * 0.40 +
            professional_score * 0.30
        )
        
        return {
            'overall_score': overall_score,
            'completeness_score': completeness_score,
            'impact_score': impact_score,
            'professional_score': professional_score
        }
    
    def estimate_career_level(self, resume_text: str, parsed_data: Dict) -> str:
        """Estimate career level from resume content"""
        text_lower = resume_text.lower()
        
        # Look for years of experience
        years_patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'experience[:\s]+(\d+)\+?\s*years?'
        ]
        
        years = 0
        for pattern in years_patterns:
            match = re.search(pattern, text_lower)
            if match:
                years = int(match.group(1))
                break
        
        # Check for leadership indicators
        leadership_terms = ['senior', 'lead', 'principal', 'architect', 'manager', 'director', 'head of']
        has_leadership = any(term in text_lower for term in leadership_terms)
        
        # Determine level
        if years >= 7 or has_leadership:
            return 'Senior'
        elif years >= 3:
            return 'Mid-Level'
        elif years >= 1:
            return 'Junior'
        else:
            return 'Fresher'
    
    def get_improvement_priorities(self, bullet_analysis: List[Dict], parsed_data: Dict) -> List[str]:
        """Generate priority improvements based on actual resume analysis - NO TEMPLATES"""
        priorities = []
        
        # Check bullet quality
        if bullet_analysis:
            bullets_without_metrics = sum(1 for b in bullet_analysis if not b['has_metric'])
            if bullets_without_metrics > len(bullet_analysis) * 0.5:
                priorities.append('Add quantifiable metrics to at least 50% of bullet points')
            
            bullets_with_weak_verbs = sum(1 for b in bullet_analysis if b['starts_with_weak_verb'])
            if bullets_with_weak_verbs > 0:
                priorities.append(f'Replace {bullets_with_weak_verbs} weak action verbs with stronger alternatives')
        
        # Check sections
        if not parsed_data['has_summary']:
            priorities.append('Add professional summary section at the top')
        
        if not parsed_data['has_projects']:
            priorities.append('Include projects section to showcase practical work')
        
        if parsed_data['metrics_count'] < 3:
            priorities.append('Increase use of numbers and metrics throughout resume')
        
        if len(parsed_data['skills_found']) < 5:
            priorities.append('Expand technical skills section with more relevant technologies')
        
        # Return only real priorities, empty list if none
        return priorities[:3]
