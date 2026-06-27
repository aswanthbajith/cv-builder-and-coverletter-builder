"""ATS-optimized LaTeX resume generation."""

import logging
import re
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Template
try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


class ResumeGenerator:
    """Generate ATS-optimized LaTeX resumes tailored to each job."""
    
    def __init__(self):
        self.template_dir = Path(config.get('paths.templates_dir', 'templates'))
        self.output_dir = Path(config.get('paths.generated_dir', 'generated')) / 'CV'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, job: Dict[str, Any], profile: Dict[str, Any], 
                 match_result: Any, filename_base: str) -> Dict[str, str]:
        """Generate tailored LaTeX resume and compile to PDF."""
        
        # Build tailored content
        content = self._build_resume_content(job, profile, match_result)
        
        # Generate LaTeX
        tex_path = self.output_dir / 'tex' / f"{filename_base}.tex"
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        
        latex_content = self._render_latex(content)
        
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        logger.info(f"Generated LaTeX resume: {tex_path}")
        
        # Compile to PDF
        pdf_path = None
        if config.get('generation.compile_latex', True):
            pdf_path = self._compile_latex(tex_path, filename_base)
        
        return {
            'tex': str(tex_path),
            'pdf': str(pdf_path) if pdf_path else None
        }
    
    def _build_resume_content(self, job: Dict, profile: Dict, match_result: Any) -> Dict:
        """Build tailored resume content based on job requirements."""
        
        # Extract keywords from job
        job_text = ' '.join([
            str(job.get('job_title', '')),
            str(job.get('job_description', '')),
            str(job.get('required_skills', ''))
        ]).lower()
        
        # Tailor professional summary
        summary = self._tailor_summary(job, profile, job_text)
        
        # Prioritize relevant skills
        skills = self._prioritize_skills(job, profile, job_text)
        
        # Select relevant projects
        projects = self._select_projects(job, profile, job_text)
        
        # Tailor experience descriptions
        experience = self._tailor_experience(job, profile, job_text)
        
        return {
            'name': profile.get('name', 'Candidate Name'),
            'contact': profile.get('contact', {}),
            'summary': summary,
            'skills': skills,
            'experience': experience,
            'education': profile.get('education', []),
            'projects': projects,
            'certifications': profile.get('certifications', []),
            'languages': profile.get('languages', []),
            'research_interests': self._tailor_research_interests(job, job_text)
        }
    
    def _tailor_summary(self, job: Dict, profile: Dict, job_text: str) -> str:
        """Create job-specific professional summary."""
        base_summary = profile.get('professional_summary', '')
        
        # Extract key job themes
        themes = []
        if 'quantum' in job_text:
            themes.append('quantum computing')
        if 'hpc' in job_text or 'high performance' in job_text:
            themes.append('high-performance computing')
        if 'machine learning' in job_text or 'ai' in job_text:
            themes.append('machine learning and AI')
        if 'simulation' in job_text:
            themes.append('scientific simulation')
        
        theme_str = ', '.join(themes) if themes else 'computational science'
        
        return (f"{base_summary} Passionate about applying {theme_str} to solve "
                f"complex engineering challenges. Seeking to contribute to "
                f"{job.get('company', 'the organization')}'s innovative projects.")
    
    def _prioritize_skills(self, job: Dict, profile: Dict, job_text: str) -> List[str]:
        """Reorder skills based on job relevance."""
        all_skills = profile.get('technical_skills', [])
        
        # Score each skill by relevance to job
        scored = []
        for skill in all_skills:
            score = 0
            skill_lower = skill.lower()
            if any(kw in job_text for kw in skill_lower.split()):
                score += 10
            # Check category relevance
            if 'python' in skill_lower and 'python' in job_text:
                score += 5
            if 'hpc' in skill_lower and any(kw in job_text for kw in ['hpc', 'parallel', 'mpi']):
                score += 5
            
            scored.append((score, skill))
        
        scored.sort(reverse=True)
        return [s for _, s in scored[:8]]  # Top 8 skills
    
    def _select_projects(self, job: Dict, profile: Dict, job_text: str) -> List[Dict]:
        """Select most relevant projects for this job."""
        all_projects = profile.get('projects', [])
        
        scored = []
        for i, project in enumerate(all_projects):
            score = 0
            proj_text = str(project).lower()
            
            if 'hpc' in job_text and any(kw in proj_text for kw in ['parallel', 'mpi', 'gpu', 'cluster']):
                score += 5
            if 'quantum' in job_text and 'quantum' in proj_text:
                score += 5
            if 'simulation' in job_text and 'simulation' in proj_text:
                score += 3
            
            scored.append((score, i, project))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, _, p in scored[:3]]  # Top 3 projects
    
    def _tailor_experience(self, job: Dict, profile: Dict, job_text: str) -> List[Dict]:
        """Tailor experience descriptions to highlight relevant aspects."""
        experience = profile.get('experience', [])
        
        tailored = []
        for exp in experience:
            exp_copy = exp.copy()
            description = exp.get('description', [])
            
            # Highlight relevant bullet points
            relevant = []
            for bullet in description:
                bullet_lower = bullet.lower()
                relevance = 0
                
                if any(kw in job_text for kw in bullet_lower.split()):
                    relevance += 1
                if 'python' in job_text and 'python' in bullet_lower:
                    relevance += 2
                
                if relevance > 0:
                    relevant.append(bullet)
            
            exp_copy['description'] = relevant[:4] if relevant else description[:4]
            tailored.append(exp_copy)
        
        return tailored
    
    def _tailor_research_interests(self, job: Dict, job_text: str) -> List[str]:
        """Select research interests relevant to job."""
        interests = [
            'High Performance Computing',
            'Quantum Computing',
            'Scientific Machine Learning',
            'Parallel and Distributed Systems',
            'Computational Engineering',
            'Performance Optimization'
        ]
        
        relevant = []
        for interest in interests:
            if any(kw in job_text for kw in interest.lower().split()):
                relevant.append(interest)
        
        return relevant[:3] if relevant else interests[:3]
    
    def _render_latex(self, content: Dict) -> str:
        """Render LaTeX document from content."""
        
        template = Template(r'''
\documentclass[11pt,a4paper]{article}

% ATS-optimized packages
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=0.6in]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{xcolor}
\usepackage{hyperref}

% No graphics, no tables, no icons - ATS friendly
\pagestyle{empty}
\setlength{\parindent}{0pt}

% Section formatting
\titleformat{\section}{\large\bfseries\uppercase}{\thesection}{0em}{}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{6pt}

% Custom commands
\newcommand{\jobtitle}[4]{
    \textbf{#1} \hfill \textit{#2}\\
    \textit{#3} \hfill #4
}

\begin{document}

% Header
\begin{center}
    {\LARGE\bfseries << content.name >>}\\[6pt]
    <% for key, value in content.contact.items() %>
    << value >><% if not loop.last %> | <% endif %>
    <% endfor %>
\end{center}

% Professional Summary
\section{Professional Summary}
<< content.summary >>

% Technical Skills
\section{Technical Skills}
<% for skill in content.skills %>
<< skill >><% if not loop.last %>, <% endif %>
<% endfor %>

% Experience
\section{Professional Experience}
<% for exp in content.experience %>
\jobtitle{ << exp.title >> }{ << exp.location >> }{ << exp.company >> }{ << exp.period >> }
\begin{itemize}[leftmargin=*,nosep,topsep=3pt]
    <% for bullet in exp.description %>
    \item << bullet >>
    <% endfor %>
\end{itemize}
<% endfor %>

% Education
\section{Education}
<% for edu in content.education %>
\textbf{ << edu.degree >> } \hfill << edu.period >>\\
<< edu.institution >> \hfill << edu.grade >>
<% endfor %>

% Projects
\section{Key Projects}
<% for project in content.projects %>
\textbf{ << project.name >> }\\
<< project.description >>
<% endfor %>

% Research Interests
\section{Research Interests}
<% for interest in content.research_interests %>
<< interest >><% if not loop.last %>, <% endif %>
<% endfor %>

% Languages
\section{Languages}
<% for lang in content.languages %>
<< lang.language >> (<< lang.proficiency >>)<% if not loop.last %>, <% endif %>
<% endfor %>

\end{document}
''', block_start_string='<%', block_end_string='%>', variable_start_string='<<', variable_end_string='>>', comment_start_string='/*', comment_end_string='*/')
        
        return template.render(content=content)
    
    def _compile_latex(self, tex_path: Path, filename_base: str) -> Path:
        """Compile LaTeX to PDF using xelatex."""
        import subprocess
        import shutil
        
        # Find xelatex executable (handles Windows PATH issues)
        xelatex_path = shutil.which('xelatex')
        if xelatex_path is None:
            # Fallback to common MiKTeX installation path
            fallback = Path("C:/Program Files/MiKTeX/miktex/bin/x64/xelatex.exe")
            if fallback.exists():
                xelatex_path = str(fallback)
            else:
                logger.error("xelatex not found. Please install MiKTeX or add xelatex to PATH.")
                return None
        
        pdf_dir = self.output_dir / 'pdf'
        pdf_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = pdf_dir / f"{filename_base}.pdf"
        
        try:
            # Run xelatex twice for references
            for _ in range(2):
                result = subprocess.run(
                    [xelatex_path, '-interaction=nonstopmode', 
                     '-output-directory', str(pdf_dir),
                     str(tex_path)],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode != 0 and '!' in result.stdout:
                    logger.warning(f"LaTeX compilation warning: {result.stdout[-500:]}")
            
            # Verify PDF was actually created
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"Compiled PDF: {pdf_path}")
                return pdf_path
            else:
                logger.error(f"PDF file not found after compilation: {pdf_path}")
                return None
            
        except Exception as e:
            logger.error(f"PDF compilation failed: {e}")
            return None
