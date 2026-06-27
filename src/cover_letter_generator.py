"""Cover letter generation in DOCX format."""

import logging
from pathlib import Path
from typing import Dict, Any
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


class CoverLetterGenerator:
    """Generate tailored cover letters in Microsoft Word format."""
    
    def __init__(self):
        self.output_dir = Path(config.get('paths.generated_dir', 'generated')) / 'CoverLetters' / 'docx'
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, job: Dict[str, Any], profile: Dict[str, Any],
                 match_result: Any, filename_base: str) -> str:
        """Generate tailored DOCX cover letter."""
        
        doc = Document()
        
        # Set margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
        
        # Add content
        self._add_header(doc, profile)
        self._add_date(doc)
        self._add_recipient(doc, job)
        self._add_salutation(doc, job)
        self._add_opening(doc, job, profile, match_result)
        self._add_body(doc, job, profile, match_result)
        self._add_closing(doc, profile)
        
        # Save
        output_path = self.output_dir / f"{filename_base}_CoverLetter.docx"
        doc.save(output_path)
        
        logger.info(f"Generated cover letter: {output_path}")
        return str(output_path)
    
    def _add_header(self, doc: Document, profile: Dict) -> None:
        """Add candidate contact information."""
        name = profile.get('name', 'Candidate Name')
        contact = profile.get('contact', {})
        
        p = doc.add_paragraph()
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(14)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        
        contact_info = ' | '.join([
            str(contact.get('email', '')),
            str(contact.get('phone', '')),
            str(contact.get('location', '')),
            str(contact.get('linkedin', ''))
        ])
        
        p = doc.add_paragraph(contact_info)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    def _add_date(self, doc: Document) -> None:
        """Add current date."""
        from datetime import datetime
        doc.add_paragraph(datetime.now().strftime('%B %d, %Y'))
    
    def _add_recipient(self, doc: Document, job: Dict) -> None:
        """Add company and position information."""
        company = job.get('company', 'Hiring Team')
        title = job.get('job_title', 'Position')
        
        doc.add_paragraph()
        doc.add_paragraph(f"{company}")
        p = doc.add_paragraph(f"Re: Application for {title}")
        if p.runs:
            p.runs[0].bold = True
    
    def _add_salutation(self, doc: Document, job: Dict) -> None:
        """Add greeting line."""
        company = job.get('company', 'the company')
        doc.add_paragraph(f"Dear {company} Hiring Team,")
    
    def _add_opening(self, doc: Document, job: Dict, profile: Dict, match_result: Any) -> None:
        """Add opening paragraph hooking the reader."""
        company = job.get('company', 'your organization')
        title = job.get('job_title', 'this position')
        
        # Build opening based on match strengths
        strengths = match_result.strengths if match_result else []
        strength_text = ''
        if strengths:
            strength_text = f" My background in {', '.join(strengths[:2])} aligns directly with your requirements."
        
        opening = (f"I am writing to express my strong interest in the {title} at {company}. "
                  f"As a {profile.get('current_role', 'Master\'s student in High Performance Computing and Quantum Computing')}, "
                  f"I bring a unique interdisciplinary perspective combining mechanical engineering fundamentals "
                  f"with advanced computational expertise.{strength_text}")
        
        doc.add_paragraph(opening)
    
    def _add_body(self, doc: Document, job: Dict, profile: Dict, match_result: Any) -> None:
        """Add body paragraphs with specific qualifications."""
        
        # Technical skills paragraph
        job_desc = str(job.get('job_description', '')).lower()
        
        tech_para = "My technical qualifications include: "
        skills = []
        
        if 'python' in job_desc:
            skills.append("advanced Python programming with NumPy, Pandas, and SciPy")
        if 'hpc' in job_desc or 'parallel' in job_desc:
            skills.append("high-performance computing and parallel programming concepts")
        if 'quantum' in job_desc:
            skills.append("quantum computing coursework and optimization methods")
        if 'machine learning' in job_desc or 'ai' in job_desc:
            skills.append("machine learning with PyTorch and scientific machine learning")
        if 'simulation' in job_desc:
            skills.append("computational modeling and simulation workflows")
        
        if not skills:
            skills.append("software development, analytical problem solving, and scientific computation")
        
        tech_para += '; '.join(skills) + "."
        
        doc.add_paragraph(tech_para)
        
        # Experience paragraph
        experience = profile.get('experience', [])
        if experience:
            exp = experience[0]  # Most recent
            exp_para = (f"In my role as {exp.get('title', 'Working Student')}, "
                       f"I {exp.get('highlight', 'gained practical experience in software development, contributing to testing, debugging, and continuous integration.')}")
            doc.add_paragraph(exp_para)
        
        # Projects paragraph
        projects = profile.get('projects', [])
        relevant_projects = [p for p in projects if any(kw in str(p).lower() for kw in job_desc.split())]
        
        if relevant_projects:
            proj = relevant_projects[0]
            proj_para = (f"A relevant project is {proj.get('name', 'my academic project')}, where "
                        f"I {proj.get('description', 'developed computational solutions and analyzed large datasets.')}")
            doc.add_paragraph(proj_para)
        
        # Motivation paragraph
        motivation = (f"What attracts me most to {job.get('company', 'your organization')} is "
                       f"the opportunity to apply my interdisciplinary background to innovative challenges. "
                       f"I am eager to contribute my analytical thinking, structured problem-solving, "
                       f"and passion for computational innovation to your team.")
        
        doc.add_paragraph(motivation)
    
    def _add_closing(self, doc: Document, profile: Dict) -> None:
        """Add closing paragraph and signature."""
        closing = ("I would welcome the opportunity to discuss how my background and skills "
                  "can contribute to your team. Thank you for your time and consideration. "
                  "I look forward to hearing from you.")
        
        doc.add_paragraph(closing)
        doc.add_paragraph()
        doc.add_paragraph("Sincerely,")
        doc.add_paragraph()
        doc.add_paragraph(profile.get('name', 'Candidate Name'))
