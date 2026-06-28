"""Job suitability analysis and semantic matching."""

import logging
import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from job_automation.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of job matching analysis."""
    overall_score: float
    education_score: float
    skills_score: float
    programming_score: float
    research_score: float
    experience_score: float
    reasoning: str
    missing_skills: List[str]
    strengths: List[str]
    status: str  # 'proceed', 'skip', 'review'


class JobMatcher:
    """Analyze job suitability against candidate profile."""

    # Keyword mappings for scoring
    SKILL_KEYWORDS = {
        'python': ['python', 'pandas', 'numpy', 'scipy', 'matplotlib', 'jupyter'],
        'hpc': ['hpc', 'high performance computing', 'parallel computing', 'mpi', 'openmp'],
        'quantum': ['quantum', 'qiskit', 'cirq', 'quantum computing'],
        'ml': ['machine learning', 'deep learning', 'pytorch', 'tensorflow', 'scikit-learn'],
        'cloud': ['cloud', 'aws', 'azure', 'gcp', 'kubernetes', 'docker'],
        'scientific_computing': ['scientific computing', 'numerical', 'simulation', 'computational'],
    }

    def __init__(self):
        self.minimum_score = load_config().matching.minimum_match_score
        self.profile = self._load_profile()
    
    def _load_profile(self) -> Dict[str, Any]:
        """Load candidate profile from JSON files."""
        from pathlib import Path

        profile_dir = Path(load_config().paths.profile_dir)
        profile = {}
        
        for file_name in ['master_resume.json', 'experience.json', 'skills.json', 'projects.json']:
            file_path = profile_dir / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    profile.update(data)
        
        return profile
    
    def analyze_job(self, job: Dict[str, Any]) -> MatchResult:
        """Analyze a single job against the candidate profile."""
        job_text = self._combine_job_text(job)
        
        # Calculate individual scores
        education_score = self._score_education(job, job_text)
        skills_score = self._score_skills(job, job_text)
        programming_score = self._score_programming(job, job_text)
        research_score = self._score_research(job, job_text)
        experience_score = self._score_experience(job, job_text)
        
        # Weighted overall score
        weights = {
            'education': 0.20,
            'skills': 0.40,
            'programming': 0.15,
            'research': 0.15,
            'experience': 0.10
        }
        
        overall = (
            education_score * weights['education'] +
            skills_score * weights['skills'] +
            programming_score * weights['programming'] +
            research_score * weights['research'] +
            experience_score * weights['experience']
        ) * 100  # Convert to percentage
        
        overall = min(overall, 100.0)
        
        # Determine status
        if overall >= self.minimum_score:
            status = 'proceed'
        elif overall >= self.minimum_score - 10:
            status = 'review'
        else:
            status = 'skip'
        
        missing = self._identify_missing_skills(job, job_text)
        strengths = self._identify_strengths(job, job_text)
        reasoning = self._generate_reasoning(overall, education_score, skills_score, 
                                              programming_score, research_score, 
                                              experience_score, strengths, missing)
        
        return MatchResult(
            overall_score=round(overall, 1),
            education_score=round(education_score * 100, 1),
            skills_score=round(skills_score * 100, 1),
            programming_score=round(programming_score * 100, 1),
            research_score=round(research_score * 100, 1),
            experience_score=round(experience_score * 100, 1),
            reasoning=reasoning,
            missing_skills=missing,
            strengths=strengths,
            status=status
        )
    
    def _combine_job_text(self, job: Dict[str, Any]) -> str:
        """Combine all job text fields for analysis."""
        fields = ['job_title', 'job_description', 'required_skills', 
                  'preferred_qualifications', 'key_matching_skills']
        texts = [str(job.get(f, '')) for f in fields if f in job]
        return ' '.join(texts).lower()
    
    def _score_education(self, job: Dict, job_text: str) -> float:
        """Score education alignment."""
        score = 0.5  # Base score for Master's student
        
        if any(kw in job_text for kw in ['master', 'msc', 'm.sc', 'graduate']):
            score += 0.3
        if any(kw in job_text for kw in ['phd', 'doctoral', 'doctorate']):
            score -= 0.1  # Slight penalty for PhD-required positions
        if any(kw in job_text for kw in ['bachelor', 'bsc', 'undergraduate']):
            score += 0.2
        
        return min(score, 1.0)
    
    def _score_skills(self, job: Dict, job_text: str) -> float:
        """Score skills alignment."""
        candidate_skills = set()
        for category, keywords in self.SKILL_KEYWORDS.items():
            if any(kw in str(self.profile).lower() for kw in keywords):
                candidate_skills.add(category)
        
        job_skills = set()
        for category, keywords in self.SKILL_KEYWORDS.items():
            if any(kw in job_text for kw in keywords):
                job_skills.add(category)
        
        if not job_skills:
            return 0.5
        
        overlap = len(candidate_skills & job_skills)
        return min(overlap / len(job_skills) * 1.2, 1.0)  # 20% bonus for strong match
    
    def _score_programming(self, job: Dict, job_text: str) -> float:
        """Score programming language alignment."""
        languages = {
            'python': ['python'],
            'c_cpp': ['c++', 'c/c++', 'cplusplus'],
            'c': [' c,', ' c '],
            'javascript': ['javascript', 'js'],
            'fortran': ['fortran'],
            'julia': ['julia'],
            'go': ['golang', ' go ']
        }
        
        candidate_langs = set()
        for lang, keywords in languages.items():
            if any(kw in str(self.profile).lower() for kw in keywords):
                candidate_langs.add(lang)
        
        job_langs = set()
        for lang, keywords in languages.items():
            if any(kw in job_text for kw in keywords):
                job_langs.add(lang)
        
        if not job_langs:
            return 0.7  # Default if no specific languages mentioned
        
        overlap = len(candidate_langs & job_langs)
        return min(overlap / len(job_langs) * 1.1, 1.0)
    
    def _score_research(self, job: Dict, job_text: str) -> float:
        """Score research relevance."""
        score = 0.5
        
        research_keywords = ['research', 'phd', 'doctoral', 'thesis', 'publication', 
                            'scientific', 'academic', 'university']
        if any(kw in job_text for kw in research_keywords):
            score += 0.2
        
        if any(kw in job_text for kw in ['hpc', 'quantum', 'parallel', 'distributed']):
            score += 0.2
        
        if 'publication' in job_text or 'publish' in job_text:
            # Check if candidate has publications
            has_pubs = 'publication' in str(self.profile).lower()
            score += 0.1 if has_pubs else -0.1
        
        return min(max(score, 0.0), 1.0)
    
    def _score_experience(self, job: Dict, job_text: str) -> float:
        """Score experience alignment."""
        score = 0.4  # Base for student/new grad
        
        # Check years of experience requirements
        years_match = re.search(r'(\d+)\+?\s*years?', job_text)
        if years_match:
            required_years = int(years_match.group(1))
            if required_years <= 1:
                score += 0.4
            elif required_years <= 3:
                score += 0.2
            elif required_years <= 5:
                score += 0.0
            else:
                score -= 0.2
        
        # Check for internship/thesis friendly positions
        if any(kw in job_text for kw in ['intern', 'thesis', 'student', 'entry']):
            score += 0.3
        
        return min(max(score, 0.0), 1.0)
    
    def _identify_missing_skills(self, job: Dict, job_text: str) -> List[str]:
        """Identify skills mentioned in job but not in profile."""
        missing = []
        
        common_skills = ['mpi', 'openmp', 'cuda', 'fortran', 'kubernetes', 'docker',
                        'aws', 'azure', 'gcp', 'slurm', 'lustre', 'qiskit', 'cirq']
        
        for skill in common_skills:
            if skill in job_text and skill not in str(self.profile).lower():
                missing.append(skill)
        
        return missing[:5]  # Top 5 missing skills
    
    def _identify_strengths(self, job: Dict, job_text: str) -> List[str]:
        """Identify candidate strengths for this job."""
        strengths = []
        
        if 'python' in job_text and 'python' in str(self.profile).lower():
            strengths.append('Python programming')
        if any(kw in job_text for kw in ['hpc', 'high performance']):
            strengths.append('HPC background')
        if 'quantum' in job_text and 'quantum' in str(self.profile).lower():
            strengths.append('Quantum computing knowledge')
        if 'optimization' in job_text:
            strengths.append('Optimization methods expertise')
        
        return strengths
    
    def _generate_reasoning(self, overall: float, edu: float, skills: float,
                           prog: float, research: float, exp: float,
                           strengths: List[str], missing: List[str]) -> str:
        """Generate human-readable reasoning."""
        parts = [f"Overall match: {overall:.0f}%"]
        parts.append(f"Education: {edu * 100:.0f}%, Skills: {skills * 100:.0f}%, Programming: {prog * 100:.0f}%")
        parts.append(f"Research: {research * 100:.0f}%, Experience: {exp * 100:.0f}%")
        
        if strengths:
            parts.append(f"Strengths: {', '.join(strengths)}")
        if missing:
            parts.append(f"Missing: {', '.join(missing)}")
        
        return "; ".join(parts)
