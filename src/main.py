"""Main entry point for the Job Application Automation System."""

import logging
import sys
import json
import re
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List

# Add src to path for legacy engines during the M1 → M3 migration window.
sys.path.insert(0, str(Path(__file__).parent))

from job_automation.config import load_config
from excel_loader import ExcelLoader
from deduplicator import Deduplicator
from matcher import JobMatcher
from resume_generator import ResumeGenerator
from cover_letter_generator import CoverLetterGenerator


def setup_logging() -> logging.Logger:
    """Configure structured logging."""
    log_path = Path(load_config().paths.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger('JobAutomation')


def sanitize_filename(text: str) -> str:
    """Convert text to safe filename."""
    # Remove/replace illegal characters
    safe = re.sub(r'[^\w\s-]', '', str(text))
    safe = re.sub(r'[-\s]+', '_', safe)
    return safe[:50]  # Limit length


def process_job(job: Dict[str, Any], profile: Dict[str, Any], 
                matcher: JobMatcher, resume_gen: ResumeGenerator,
                cover_gen: CoverLetterGenerator, logger: logging.Logger) -> Dict[str, Any]:
    """Process a single job: match, generate documents."""
    
    job_id = job.get('_df_index', job.get('rank', job.get('index', 0)))
    company = job.get('company', 'Unknown')
    title = job.get('job_title', 'Position')
    
    logger.info(f"Processing job {job_id}: {company} - {title}")
    
    # Step 1: Match analysis
    match_result = matcher.analyze_job(job)
    
    result = {
        'index': job_id,
        'company': company,
        'job_title': title,
        'match_percent': match_result.overall_score,
        'match_reasoning': match_result.reasoning,
        'missing_skills': ', '.join(match_result.missing_skills),
        'strengths': ', '.join(match_result.strengths),
        'status': match_result.status,
        'resume_tex': None,
        'resume_pdf': None,
        'cover_letter': None,
        'generated_date': None
    }
    
    # Step 2: Skip if below threshold
    if match_result.status == 'skip':
        logger.info(f"Skipping job {job_id}: match score {match_result.overall_score}% < threshold")
        return result
    
    # Step 3: Generate filename base
    filename_base = f"{sanitize_filename(company)}_{sanitize_filename(title)}"
    
    # Step 4: Generate resume
    try:
        resume_paths = resume_gen.generate(job, profile, match_result, filename_base)
        result['resume_tex'] = resume_paths.get('tex')
        result['resume_pdf'] = resume_paths.get('pdf')
        logger.info(f"Generated resume for job {job_id}")
    except Exception as e:
        logger.error(f"Resume generation failed for job {job_id}: {e}")
    
    # Step 5: Generate cover letter
    try:
        cover_path = cover_gen.generate(job, profile, match_result, filename_base)
        result['cover_letter'] = cover_path
        logger.info(f"Generated cover letter for job {job_id}")
    except Exception as e:
        logger.error(f"Cover letter generation failed for job {job_id}: {e}")
    
    from datetime import datetime
    result['generated_date'] = datetime.now().isoformat()
    
    return result


def main():
    """Main execution flow."""
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("AI Job Application Automation System Starting")
    logger.info("=" * 60)
    
    # Step 1: Load Excel
    logger.info("Step 1: Loading job listings from Excel")
    loader = ExcelLoader()
    df = loader.load()
    
    if df is None or len(df) == 0:
        logger.error("No jobs found in Excel file. Exiting.")
        return 1
    
    logger.info(f"Loaded {len(df)} job listings")
    
    # Step 2: Deduplicate
    logger.info("Step 2: Removing duplicate job postings")
    deduplicator = Deduplicator()
    df = deduplicator.deduplicate(df)
    
    duplicates = df[df['duplicate'] == True]
    logger.info(f"Marked {len(duplicates)} duplicates")
    
    # Step 3: Load profile
    logger.info("Step 3: Loading candidate profile")
    profile_path = Path(load_config().paths.profile_dir)
    profile = {}
    
    for file_name in ['master_resume.json', 'experience.json', 'skills.json', 'projects.json']:
        file_path = profile_path / file_name
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                profile.update(json.load(f))
    
    logger.info(f"Loaded profile with {len(profile)} sections")
    
    # Step 4: Initialize generators
    logger.info("Step 4: Initializing document generators")
    matcher = JobMatcher()
    resume_gen = ResumeGenerator()
    cover_gen = CoverLetterGenerator()
    
    # Step 5: Process jobs
    logger.info("Step 5: Matching jobs and generating documents")
    jobs_list = df.to_dict('records')
    results = []
    
    # Build index mapping
    for i, job in enumerate(jobs_list):
        job['_df_index'] = i
    
    max_workers = load_config().generation.max_workers
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_job, job, profile, matcher, resume_gen, cover_gen, logger)
            for job in jobs_list if not job.get('duplicate', False)
        ]
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                logger.error(f"Error processing job thread: {e}")
    
    # Step 6: Merge results back into DataFrame and save
    logger.info("Step 6: Updating Excel with results and hyperlinks")
    
    for res in results:
        idx = res['index']
        if idx < len(df):
            df.at[idx, 'match_percent'] = res['match_percent']
            df.at[idx, 'match_reasoning'] = res['match_reasoning']
            df.at[idx, 'missing_skills'] = res['missing_skills']
            df.at[idx, 'strengths'] = res['strengths']
            df.at[idx, 'status'] = res['status']
            df.at[idx, 'resume_tex'] = res['resume_tex']
            df.at[idx, 'resume_pdf'] = res['resume_pdf']
            df.at[idx, 'cover_letter'] = res['cover_letter']
            df.at[idx, 'generated_date'] = res['generated_date']
    
    loader.save(df)
    
    logger.info("=" * 60)
    logger.info("Processing complete!")
    logger.info("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
