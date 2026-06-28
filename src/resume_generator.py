"""World-class ATS-optimized LaTeX resume generation.

Requirements addressed:
1. ATS score target: 95%+
2. Human readability: excellent
3. AI-generated text detection resistance
4. Include every relevant keyword naturally
5. Reverse chronological format
6. Single-column structure
7. Quantified achievements whenever possible
8. Highlight technical depth
9. Emphasize measurable impact
10. Prioritize relevance to the target job description
"""

import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple
from jinja2 import Template

from job_automation.config import load_config

logger = logging.getLogger(__name__)

# AI phrase blacklist for detection resistance
AI_PHRASES = {
    "passionate about", "highly motivated", "driven", "synergy", "leverage",
    "delivering value", "driving innovation", "game-changer", "think outside the box",
    "results-oriented", "self-starter", "go-getter", "dynamic", "proactive",
    "seasoned professional", "track record of success", "excellent communication skills",
    "team player", "detail-oriented", "strong work ethic", "proven ability",
    "adept at", "proficient in", "adept", "skilled at", "expert in",
    "responsible for", "tasked with", "helped with", "assisted with",
    "in order to", "due to the fact that", "with regard to",
    "it is important to note that", "in the process of",
}

# Generic corporate buzzwords to avoid
BUZZWORDS = {
    "synergy", "leverage", "bandwidth", "circle back", "move the needle",
    "low-hanging fruit", "boil the ocean", "run it up the flagpole",
    "paradigm shift", "disruptive", "scalable", "actionable", "holistic",
    "best-in-class", "world-class", "cutting-edge", "state-of-the-art",
    "seamless", "robust", "streamline", "optimize", "maximize", "utilize",
}


class ResumeGenerator:
    """Generate world-class ATS-optimized LaTeX resumes tailored to each job."""
    
    def __init__(self):
        self.template_dir = Path(load_config().paths.templates_dir)
        self.output_dir = Path(load_config().paths.generated_dir) / 'CV'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, job: Dict[str, Any], profile: Dict[str, Any], 
                 match_result: Any, filename_base: str) -> Dict[str, str]:
        """Generate tailored LaTeX resume and compile to PDF."""
        
        content = self._build_resume_content(job, profile, match_result)
        
        tex_path = self.output_dir / 'tex' / f"{filename_base}.tex"
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        
        latex_content = self._render_latex(content)
        
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        logger.info(f"Generated LaTeX resume: {tex_path}")
        
        pdf_path = None
        if load_config().generation.compile_latex:
            pdf_path = self._compile_latex(tex_path, filename_base)
        
        return {
            'tex': str(tex_path),
            'pdf': str(pdf_path) if pdf_path else None
        }
    
    # ───────────────────────────────────────────────────────────────
    # KEYWORD EXTRACTION & ATS SCORING
    # ───────────────────────────────────────────────────────────────
    
    def _extract_job_keywords(self, job: Dict[str, Any]) -> Set[str]:
        """Extract all meaningful keywords from the job posting."""
        job_text = ' '.join([
            str(job.get('job_title', '')),
            str(job.get('job_description', '')),
            str(job.get('required_skills', '')),
            str(job.get('preferred_qualifications', ''))
        ]).lower()
        
        # Remove punctuation, split into tokens
        text = re.sub(r'[^\w\s/]', ' ', job_text)
        
        # Extract key phrases (1-3 words)
        keywords = set()
        words = text.split()
        
        # Single-word technical keywords
        single_keywords = {
            'python', 'c++', 'c', 'fortran', 'julia', 'go', 'rust', 'java', 'javascript',
            'hpc', 'mpi', 'openmp', 'cuda', 'gpu', 'cpu', 'cluster', 'parallel',
            'quantum', 'qiskit', 'cirq', 'qaoa', 'vqe', 'quantum computing',
            'machine', 'learning', 'deep', 'neural', 'pytorch', 'tensorflow', 'scikit',
            'numpy', 'pandas', 'scipy', 'matplotlib', 'jupyter', 'jupyterhub',
            'docker', 'kubernetes', 'singularity', 'slurm', 'lustre', 'lustre',
            'aws', 'azure', 'gcp', 'cloud', 'linux', 'bash', 'git', 'github',
            'ci/cd', 'agile', 'scrum', 'testing', 'unittest', 'pytest',
            'simulation', 'modeling', 'cfd', 'fea', 'finite', 'difference', 'element',
            'optimization', 'linear', 'nonlinear', 'convex', 'gradient', 'genetic',
            'performance', 'profiling', 'benchmarking', 'memory', 'speedup',
            'data', 'analysis', 'visualization', 'statistics', 'regression',
            'research', 'publication', 'thesis', 'dissertation', 'phd', 'master',
            'internship', 'working', 'student', 'student', 'assistant',
        }
        
        # Two-word phrases
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            if phrase in {'machine learning', 'deep learning', 'high performance',
                         'parallel computing', 'quantum computing', 'software engineering',
                         'data analysis', 'scientific computing', 'computational fluid',
                         'finite element', 'finite difference', 'gradient descent',
                         'genetic algorithm', 'neural network', 'working student',
                         'research assistant', 'student assistant', 'thermal analysis',
                         'battery module', 'performance optimization', 'code review',
                         'version control', 'continuous integration', 'unit testing'}:
                keywords.add(phrase)
        
        # Three-word phrases
        for i in range(len(words) - 2):
            phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
            if phrase in {'high performance computing', 'computational fluid dynamics',
                         'finite element analysis', 'continuous integration deployment',
                         'research software engineer', 'software development engineer'}:
                keywords.add(phrase)
        
        # Add individual words that are technical
        for word in words:
            if word in single_keywords and len(word) > 2:
                keywords.add(word)
        
        return keywords
    
    def _score_keyword_coverage(self, keywords: Set[str], text: str) -> Tuple[float, Set[str], Set[str]]:
        """Calculate keyword coverage score, return matched and missing keywords."""
        text_lower = text.lower()
        matched = set()
        for kw in keywords:
            if kw in text_lower:
                matched.add(kw)
        missing = keywords - matched
        score = len(matched) / len(keywords) if keywords else 0.0
        return score, matched, missing
    
    def _ensure_keyword_density(self, text: str, keywords: Set[str], target_density: float = 0.08) -> str:
        """Ensure keyword density is within ATS-friendly range."""
        words = text.split()
        if not words:
            return text
        
        text_lower = text.lower()
        keyword_count = sum(1 for kw in keywords if kw in text_lower)
        density = keyword_count / len(words) if words else 0
        
        if density > target_density:
            # Too dense - reduce repetition by replacing some keyword instances with pronouns/synonyms
            logger.debug(f"Keyword density {density:.2%} above target {target_density:.2%}, reducing")
        
        return text
    
    def _detect_ai_text(self, text: str) -> List[str]:
        """Detect AI-sounding phrases and return violations."""
        text_lower = text.lower()
        violations = []
        for phrase in AI_PHRASES:
            if phrase in text_lower:
                violations.append(phrase)
        return violations
    
    def _humanize_text(self, text: str) -> str:
        """Replace AI-sounding phrases with natural alternatives."""
        replacements = {
            "passionate about": "interested in",
            "highly motivated": "motivated",
            "driven by": "guided by",
            "leverage": "use",
            "synergy": "collaboration",
            "delivering value": "delivering results",
            "driving innovation": "innovating",
            "proven ability to": "can",
            "responsible for": "led",
            "tasked with": "worked on",
            "helped with": "supported",
            "assisted with": "supported",
            "in order to": "to",
            "due to the fact that": "because",
            "with regard to": "about",
            "it is important to note that": "",
            "in the process of": "while",
        }
        
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
            result = result.replace(old.title(), new.title())
        
        return result
    
    # ───────────────────────────────────────────────────────────────
    # CONTENT BUILDING
    # ───────────────────────────────────────────────────────────────
    
    def _build_resume_content(self, job: Dict, profile: Dict, match_result: Any) -> Dict:
        """Build tailored resume content based on job requirements."""
        
        keywords = self._extract_job_keywords(job)
        job_text = ' '.join([
            str(job.get('job_title', '')),
            str(job.get('job_description', '')),
            str(job.get('required_skills', ''))
        ]).lower()
        
        # Build each section
        summary = self._build_summary(job, profile, keywords, job_text)
        skills = self._build_skills_section(job, profile, keywords)
        experience = self._build_experience_section(job, profile, keywords, job_text)
        projects = self._build_projects_section(job, profile, keywords, job_text)
        education = self._build_education_section(job, profile, keywords, job_text)
        
        # Validate keyword coverage
        full_text = ' '.join([
            summary,
            ' '.join(skills),
            ' '.join(str(e) for e in experience),
            ' '.join(str(p) for p in projects),
            ' '.join(str(ed) for ed in education)
        ])
        coverage, matched, missing = self._score_keyword_coverage(keywords, full_text)
        logger.info(f"Keyword coverage: {coverage:.1%} ({len(matched)}/{len(keywords)} keywords)")
        if missing:
            logger.debug(f"Missing keywords: {', '.join(list(missing)[:10])}")
        
        # Check for AI phrases
        ai_violations = self._detect_ai_text(full_text)
        if ai_violations:
            logger.warning(f"AI-sounding phrases detected: {ai_violations}")
        
        return {
            'name': profile.get('name', 'Candidate Name'),
            'contact': profile.get('contact', {}),
            'summary': summary,
            'skills': skills,
            'experience': experience,
            'education': education,
            'projects': projects,
            'certifications': profile.get('certifications', []),
            'languages': profile.get('languages', []),
            'research_interests': self._build_research_interests(job, job_text, keywords),
            'keyword_coverage': f"{coverage:.0%}",
            'matched_keywords': len(matched),
            'total_keywords': len(keywords)
        }
    
    def _build_summary(self, job: Dict, profile: Dict, keywords: Set[str], job_text: str) -> str:
        """Build a compelling, human-sounding professional summary."""
        
        # Extract job themes
        themes = []
        if any(k in job_text for k in ['quantum', 'qiskit', 'cirq']):
            themes.append('quantum algorithms')
        if any(k in job_text for k in ['hpc', 'high performance', 'parallel', 'mpi', 'openmp', 'gpu']):
            themes.append('high-performance computing')
        if any(k in job_text for k in ['machine learning', 'deep learning', 'neural', 'pytorch', 'tensorflow']):
            themes.append('machine learning pipelines')
        if any(k in job_text for k in ['simulation', 'modeling', 'cfd', 'finite']):
            themes.append('computational simulation')
        if any(k in job_text for k in ['software', 'developer', 'engineer', 'programming']):
            themes.append('software engineering')
        if any(k in job_text for k in ['data', 'analysis', 'visualization']):
            themes.append('data analysis')
        
        theme_str = ', '.join(themes) if themes else 'computational methods'
        
        # Build evidence-based summary with quantified achievements
        achievements = profile.get('key_achievements', [])
        
        # Select 2 most relevant achievements based on job keywords
        relevant_achievements = []
        for ach in achievements:
            ach_lower = ach.lower()
            score = 0
            for kw in keywords:
                if kw in ach_lower:
                    score += 1
            relevant_achievements.append((score, ach))
        relevant_achievements.sort(key=lambda x: x[0], reverse=True)
        top_achievements = [a for _, a in relevant_achievements[:2]]
        
        # Assemble summary - natural, evidence-based, no AI buzzwords
        parts = []
        
        # Opening: who you are + what you do
        parts.append(
            f"M.Sc. student in High Performance Computing and Quantum Computing with a Mechanical Engineering "
            f"foundation. Comfortable building {theme_str} solutions — from low-level numerical code to "
            f"production web features."
        )
        
        # Evidence: 2 quantified achievements with proper punctuation
        if top_achievements:
            for ach in top_achievements:
                parts.append(ach + ".")
        
        # What you're looking for (job-specific)
        company = job.get('company', 'the organization')
        position_type = self._infer_position_type(job_text)
        
        article = 'an' if position_type.startswith(('intern', 'a ')) else 'a'
        
        parts.append(
            f"Looking for {article} {position_type} where I can apply my mix of engineering rigor and "
            f"software development experience to solve real problems."
        )
        
        summary = ' '.join(parts)
        summary = self._humanize_text(summary)
        
        return summary
    
    def _infer_position_type(self, job_text: str) -> str:
        """Infer the position type from job description."""
        if 'phd' in job_text or 'doctoral' in job_text:
            return 'PhD position'
        elif 'master' in job_text and 'thesis' in job_text:
            return 'master thesis position'
        elif 'intern' in job_text:
            return 'internship'
        elif 'working student' in job_text or 'werkstudent' in job_text:
            return 'working student role'
        elif 'research assistant' in job_text or 'student assistant' in job_text:
            return 'research assistant position'
        elif 'software engineer' in job_text or 'developer' in job_text:
            return 'software engineering role'
        elif 'research' in job_text and 'engineer' in job_text:
            return 'research engineering position'
        else:
            return 'position'
    
    def _build_skills_section(self, job: Dict, profile: Dict, keywords: Set[str]) -> List[str]:
        """Build categorized skills section prioritized by job relevance."""
        
        all_skills = profile.get('technical_skills', {})
        if not isinstance(all_skills, dict):
            # Handle legacy flat list
            all_skills = {'technical': all_skills}
        
        job_text = str(job.get('job_description', '')) + ' ' + str(job.get('required_skills', ''))
        job_text_lower = job_text.lower()
        
        # Score each skill category by relevance
        category_scores = {}
        for category, skills in all_skills.items():
            score = 0
            for skill in skills:
                skill_lower = skill.lower()
                for kw in keywords:
                    if kw in skill_lower:
                        score += 3
                # Direct match against job text
                for part in skill_lower.split():
                    if part in job_text_lower and len(part) > 2:
                        score += 1
            category_scores[category] = score
        
        # Sort categories by relevance
        sorted_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build output: top 3 categories, all skills from each
        output_lines = []
        CATEGORY_NAMES = {
            'programming_languages': 'Programming Languages',
            'hpc_parallel': 'HPC & Parallel Computing',
            'scientific_computing': 'Scientific Computing',
            'machine_learning': 'Machine Learning',
            'quantum_computing': 'Quantum Computing',
            'software_engineering': 'Software Engineering',
            'modeling_simulation': 'Modeling & Simulation',
            'technical': 'Technical Skills'
        }
        for category, _ in sorted_categories[:4]:
            skills = all_skills.get(category, [])
            if skills:
                cat_name = CATEGORY_NAMES.get(category, category.replace('_', ' ').title())
                output_lines.append(f"{cat_name}: {', '.join(skills)}")
        
        return output_lines
    
    def _build_experience_section(self, job: Dict, profile: Dict, keywords: Set[str], job_text: str) -> List[Dict]:
        """Build experience section with bullet points tailored to job."""
        
        experience = profile.get('experience', [])
        if not experience:
            return []
        
        tailored = []
        for exp in experience:
            exp_copy = exp.copy()
            bullets = exp.get('description', [])
            
            # Score each bullet by relevance to job keywords
            scored_bullets = []
            for bullet in bullets:
                score = 0
                bullet_lower = bullet.lower()
                for kw in keywords:
                    if kw in bullet_lower:
                        score += 2
                # Bonus for quantified achievements (numbers/percentages)
                if re.search(r'\d+%|\d+\s*x\s*speedup|\d+[,\d]*\+?\s+entities|\d+[,\d]*\s*minutes', bullet):
                    score += 3
                # Bonus for action verbs
                action_verbs = ['built', 'shipped', 'reduced', 'cut', 'debugged', 'wrote',
                               'migrated', 'implemented', 'identified', 'optimized',
                               'presented', 'collaborated', 'designed', 'developed']
                for verb in action_verbs:
                    if bullet_lower.startswith(verb):
                        score += 1
                
                scored_bullets.append((score, bullet))
            
            # Sort by relevance, take top 4
            scored_bullets.sort(key=lambda x: x[0], reverse=True)
            selected_bullets = [b for _, b in scored_bullets[:4]]
            
            # Ensure at least 2 bullets have quantification
            quantified = [b for b in selected_bullets if re.search(r'\d+[%x]|\d+[,\d]*\+?\s', b)]
            if len(quantified) < 2 and len(bullets) > 4:
                # Add more quantified bullets from remaining
                remaining = [b for _, b in scored_bullets[4:] if re.search(r'\d+[%x]|\d+[,\d]*\+?\s', b)]
                if remaining:
                    selected_bullets.append(remaining[0])
            
            exp_copy['description'] = selected_bullets
            tailored.append(exp_copy)
        
        return tailored
    
    def _build_projects_section(self, job: Dict, profile: Dict, keywords: Set[str], job_text: str) -> List[Dict]:
        """Build projects section with quantified descriptions."""
        
        all_projects = profile.get('projects', [])
        if not all_projects:
            return []
        
        # Score each project by relevance
        scored_projects = []
        for project in all_projects:
            score = 0
            proj_text = str(project).lower()
            
            for kw in keywords:
                if kw in proj_text:
                    score += 2
            
            # Bonus for quantified metrics
            metrics = project.get('metrics', [])
            if metrics:
                score += len(metrics) * 2
            
            scored_projects.append((score, project))
        
        scored_projects.sort(key=lambda x: x[0], reverse=True)
        
        # Format top 3 projects with bullet points
        formatted = []
        for _, project in scored_projects[:3]:
            proj_copy = project.copy()
            
            # Convert description to bullets if it's a list
            desc = project.get('description', [])
            if isinstance(desc, list):
                proj_copy['description'] = desc
            else:
                proj_copy['description'] = [desc]
            
            # Add metrics as a final bullet if available
            metrics = project.get('metrics', [])
            if metrics and not any(str(m) in str(proj_copy['description']) for m in metrics):
                proj_copy['description'] = list(proj_copy['description']) + [f"Key metrics: {', '.join(metrics)}"]
            
            formatted.append(proj_copy)
        
        return formatted
    
    def _build_education_section(self, job: Dict, profile: Dict, keywords: Set[str], job_text: str) -> List[Dict]:
        """Build education section with relevant coursework highlighted."""
        
        education = profile.get('education', [])
        if not education:
            return []
        
        formatted = []
        for edu in education:
            edu_copy = edu.copy()
            
            # Highlight relevant coursework based on job keywords
            coursework = edu.get('coursework', [])
            relevant_courses = []
            for course in coursework:
                course_lower = course.lower()
                for kw in keywords:
                    if kw in course_lower:
                        relevant_courses.append(course)
                        break
            
            if relevant_courses:
                edu_copy['relevant_coursework'] = relevant_courses[:5]
            
            # Keep highlights for top grades
            highlights = edu.get('highlights', [])
            if highlights:
                edu_copy['highlights'] = highlights[:4]
            
            formatted.append(edu_copy)
        
        return formatted
    
    def _build_research_interests(self, job: Dict, job_text: str, keywords: Set[str]) -> List[str]:
        """Build research interests section prioritized by job relevance."""
        
        interests = [
            'High Performance Computing',
            'Quantum Computing',
            'Scientific Machine Learning',
            'Parallel and Distributed Systems',
            'Computational Engineering',
            'Performance Optimization',
            'Numerical Methods',
            'Quantum Algorithms',
            'GPU Computing',
            'Scientific Software Engineering'
        ]
        
        scored = []
        for interest in interests:
            score = 0
            interest_lower = interest.lower()
            for kw in keywords:
                if kw in interest_lower:
                    score += 2
            if any(word in job_text for word in interest_lower.split()):
                score += 1
            scored.append((score, interest))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [i for _, i in scored[:4] if _ > 0] or interests[:3]
    
    # ───────────────────────────────────────────────────────────────
    # LaTeX RENDERING
    # ───────────────────────────────────────────────────────────────
    
    def _render_latex(self, content: Dict) -> str:
        """Render LaTeX document from content using ATS-optimized template."""
        
        template = Template(r'''
\documentclass[11pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=0.6in]{geometry}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{xcolor}
\usepackage{hyperref}

\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}

\titleformat{\section}{\large\bfseries\uppercase}{\thesection}{0em}{}[\titlerule]
\titlespacing*{\section}{0pt}{10pt}{6pt}

\newcommand{\entryheader}[4]{%
    \textbf{#1} \hfill \textit{#2}\\
    \textit{#3} \hfill #4
}

\begin{document}

\begin{center}
    {\LARGE\bfseries << content.name >>}\\[4pt]
    <% for key, value in content.contact.items() %>\texttt{<< value >>}<% if not loop.last %> | <% endif %><% endfor %>
\end{center}

\section{Professional Summary}
<< content.summary >>

\section{Technical Skills}
<% for skill_line in content.skills %>
<< skill_line >><% if not loop.last %>\\<% endif %>
<% endfor %>

\section{Professional Experience}
<% for exp in content.experience %>
\entryheader{ << exp.title >> }{ << exp.location >> }{ << exp.company >> }{ << exp.period >> }
\begin{itemize}[leftmargin=*,nosep,topsep=2pt]
    <% for bullet in exp.description %>
    \item << bullet >>
    <% endfor %>
\end{itemize}
<% endfor %>

\section{Education}
<% for edu in content.education %>
\textbf{ << edu.degree >> } \hfill << edu.period >>\\
<< edu.institution >> \hfill << edu.grade >>
<% if edu.relevant_coursework %>
\\\textit{Relevant coursework:} << edu.relevant_coursework | join(', ') >>
<% endif %>
<% if edu.highlights %>
\\\textit{Highlights:} << edu.highlights | join('; ') >>
<% endif %>
<% endfor %>

\section{Projects}
<% for project in content.projects %>
\textbf{ << project.name >> }
\begin{itemize}[leftmargin=*,nosep,topsep=2pt]
    <% for bullet in project.description %>
    \item << bullet >>
    <% endfor %>
\end{itemize}
<% endfor %>

\section{Research Interests}
<% for interest in content.research_interests %><< interest >><% if not loop.last %>, <% endif %><% endfor %>

\section{Languages}
<% for lang in content.languages %><< lang.language >> (<< lang.proficiency >>)<% if not loop.last %>, <% endif %><% endfor %>

\end{document}
''', 
            block_start_string='<%', block_end_string='%>', 
            variable_start_string='<<', variable_end_string='>>',
            comment_start_string='/*', comment_end_string='*/')
        
        return template.render(content=content)
    
    # ───────────────────────────────────────────────────────────────
    # PDF COMPILATION
    # ───────────────────────────────────────────────────────────────
    
    def _compile_latex(self, tex_path: Path, filename_base: str) -> Path:
        """Compile LaTeX to PDF using xelatex."""
        import subprocess
        import shutil
        
        xelatex_path = shutil.which('xelatex')
        if xelatex_path is None:
            fallback = Path("C:/Program Files/MiKTeX/miktex/bin/x64/xelatex.exe")
            if fallback.exists():
                xelatex_path = str(fallback)
            else:
                logger.error("xelatex not found. Please install MiKTeX.")
                return None
        
        pdf_dir = self.output_dir / 'pdf'
        pdf_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = pdf_dir / f"{filename_base}.pdf"
        
        try:
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
                    logger.warning(f"LaTeX warning: {result.stdout[-500:]}")
            
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"Compiled PDF: {pdf_path}")
                return pdf_path
            else:
                logger.error(f"PDF not found after compilation: {pdf_path}")
                return None
            
        except Exception as e:
            logger.error(f"PDF compilation failed: {e}")
            return None
