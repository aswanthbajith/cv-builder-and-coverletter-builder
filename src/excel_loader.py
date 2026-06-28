"""Excel file loading and normalization."""

import logging
import pandas as pd
from pathlib import Path
from typing import Optional, List

from job_automation.config import load_config

logger = logging.getLogger(__name__)


class ExcelLoader:
    """Load and normalize Excel job listings."""
    
    # Column name mappings for normalization
    COLUMN_ALIASES = {
        'company': ['Company', 'company', 'Employer', 'employer', 'Organization'],
        'job_title': ['Job_Title', 'Job Title', 'job_title', 'Position', 'position', 'Title', 'title'],
        'location': ['Location', 'location', 'City', 'city', 'Place'],
        'posting_date': ['Posting_Date', 'Posting Date', 'posting_date', 'Date', 'date', 'Posted'],
        'job_description': ['Job_Description', 'Job Description', 'job_description', 'Description', 'description'],
        'required_skills': ['Required_Skills', 'Required Skills', 'required_skills', 'Requirements', 'requirements'],
        'preferred_qualifications': ['Preferred_Qualifications', 'Preferred Qualifications', 'preferred_qualifications'],
        'application_url': ['Application_URL', 'Application URL', 'application_url', 'URL', 'url', 'Link'],
        'match_score': ['Match_Score', 'Match Score', 'match_score', 'Score'],
        'key_matching_skills': ['Key_Matching_Skills', 'Key Matching Skills', 'key_matching_skills'],
        'missing_skills': ['Missing_Skills', 'Missing Skills', 'missing_skills'],
        'job_type': ['Job_Type', 'Job Type', 'job_type', 'Type'],
        'deadline': ['Deadline', 'deadline'],
        'source': ['Source', 'source']
    }
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or str(load_config().paths.input_excel)
        self.df: Optional[pd.DataFrame] = None
    
    def load(self) -> pd.DataFrame:
        """Load Excel file and normalize column names."""
        path = Path(self.file_path)
        
        if not path.exists():
            # Try alternative file names
            alternatives = [
                'HPC_Quantum_Job_Matching_50_Positions.xlsx',
                'HPC_Quantum_Job_Matching_Results.xlsx',
                'jobs.xlsx'
            ]
            for alt in alternatives:
                alt_path = path.parent / alt
                if alt_path.exists():
                    path = alt_path
                    break
        
        logger.info(f"Loading Excel file: {path}")
        
        self.df = pd.read_excel(path)
        self._normalize_columns()
        
        logger.info(f"Loaded {len(self.df)} job listings")
        return self.df
    
    def _normalize_columns(self) -> None:
        """Normalize column names to standard format."""
        column_map = {}
        for standard, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in self.df.columns:
                    column_map[alias] = standard
                    break
        
        self.df.rename(columns=column_map, inplace=True)
        
        # Ensure required columns exist
        required = ['company', 'job_title', 'location', 'job_description']
        missing = [c for c in required if c not in self.df.columns]
        if missing:
            logger.warning(f"Missing columns: {missing}")
    
    def save(self, df: pd.DataFrame, output_path: Optional[str] = None) -> None:
        """Save DataFrame to Excel with hyperlinks."""
        output_path = output_path or str(load_config().paths.output_excel)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create hyperlinks for generated files
        df_with_links = self._create_hyperlinks(df)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_with_links.to_excel(writer, index=False, sheet_name='Job Matches')
            
            # Adjust column widths
            worksheet = writer.sheets['Job Matches']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Saved updated Excel to: {output_path}")
    
    def _create_hyperlinks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert file paths to Excel hyperlinks."""
        result = df.copy()
        
        for col in ['resume_pdf', 'resume_tex', 'cover_letter']:
            if col in result.columns:
                result[col] = result[col].apply(
                    lambda x: f'=HYPERLINK("{x}","Open {col.replace("_", " ").title()}")' 
                    if pd.notna(x) and str(x).strip() else ''
                )
        
        return result
