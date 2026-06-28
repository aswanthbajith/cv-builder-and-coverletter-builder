"""Pipeline IO — file loaders that produce Pydantic models.

Splitting IO from engines lets M3 swap the synchronous Excel reader for an
async API poller, and lets tests construct jobs/profiles in-memory without
touching the filesystem.
"""

from job_automation.io.excel_reader import read_jobs_excel
from job_automation.io.excel_writer import V2_COLUMNS, write_generation_results
from job_automation.io.profile_loader import load_profile

__all__ = ["V2_COLUMNS", "load_profile", "read_jobs_excel", "write_generation_results"]
