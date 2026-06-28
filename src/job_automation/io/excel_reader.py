"""Excel job reader — thin wrapper around ``pandas.read_excel``.

Wraps the legacy ``ExcelLoader`` column-normalization logic and returns a
list of validated :class:`Job` instances. Lives behind a function (not a
class) so M3 can replace it with an async poller without changing callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from job_automation.config import PathsConfig
from job_automation.logging import get_logger
from job_automation.models.job import Job

logger = get_logger(__name__)

# Column alias map — copied verbatim from ``src/excel_loader.py`` so M1 stays
# behavior-compatible. M2 can de-duplicate.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "company": ["Company", "company", "Employer", "employer", "Organization"],
    "job_title": ["Job_Title", "Job Title", "job_title", "Position", "position", "Title", "title"],
    "location": ["Location", "location", "City", "city", "Place"],
    "posting_date": ["Posting_Date", "Posting Date", "posting_date", "Date", "date", "Posted"],
    "job_description": ["Job_Description", "Job Description", "job_description", "Description", "description"],
    "required_skills": ["Required_Skills", "Required Skills", "required_skills", "Requirements", "requirements"],
    "preferred_qualifications": ["Preferred_Qualifications", "Preferred Qualifications", "preferred_qualifications"],
    "application_url": ["Application_URL", "Application URL", "application_url", "URL", "url", "Link"],
    "match_score": ["Match_Score", "Match Score", "match_score", "Score"],
    "key_matching_skills": ["Key_Matching_Skills", "Key Matching Skills", "key_matching_skills"],
    "missing_skills": ["Missing_Skills", "Missing Skills", "missing_skills"],
    "job_type": ["Job_Type", "Job Type", "job_type", "Type"],
    "deadline": ["Deadline", "deadline"],
    "source": ["Source", "source"],
}

# Fallback filenames to try if the configured path doesn't exist.
_FALLBACK_INPUTS = (
    "HPC_Quantum_Job_Matching_50_Positions.xlsx",
    "HPC_Quantum_Job_Matching_Results.xlsx",
    "jobs.xlsx",
)


def read_jobs_excel(
    paths: PathsConfig | None = None,
    *,
    excel_path: Path | None = None,
) -> list[Job]:
    """Read jobs from an Excel file and validate each row.

    Returns a list of :class:`Job`. Rows that fail validation are logged and
    skipped — the pipeline never aborts on one bad row. The ``strict=True``
    setting on :class:`Job` means coercion failures (e.g. ``company=123``)
    raise ``ValidationError`` which we catch and skip.
    """
    if paths is None:
        from job_automation.config import load_config
        paths = load_config().paths

    resolved = _resolve_input(excel_path or paths.input_excel)
    logger.info("loading_excel", extra={"path": str(resolved)})

    df = pd.read_excel(resolved)
    df = _normalize_columns(df)

    jobs: list[Job] = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            jobs.append(_row_to_job(row.to_dict()))
        except ValidationError as exc:
            skipped += 1
            logger.warning(
                "job_row_invalid",
                extra={"errors": exc.errors(), "row_index": row.name},
            )
    logger.info(
        "excel_loaded",
        extra={"rows_total": len(df), "rows_loaded": len(jobs), "rows_skipped": skipped},
    )
    return jobs


def _resolve_input(configured: Path) -> Path:
    """Return the first existing path among configured + fallback names."""
    configured = Path(configured)
    if configured.exists():
        return configured
    for name in _FALLBACK_INPUTS:
        candidate = configured.parent / name
        if candidate.exists():
            logger.info("using_fallback_input", extra={"path": str(candidate)})
            return candidate
    raise FileNotFoundError(
        f"Excel file not found: {configured} (no fallbacks matched)"
    )


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Excel columns to snake_case standard names."""
    rename_map: dict[str, str] = {}
    for standard, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = standard
                break
    return df.rename(columns=rename_map)


def _row_to_job(row: dict[str, Any]) -> Job:
    """Convert a pandas row dict to a validated :class:`Job`.

    Strips pandas NaN/NaT (these become ``None`` for optional fields, which
    is what the strict Pydantic model expects). Also performs Excel-specific
    coercions:

    - ISO date strings → ``datetime.date``
    - ``"Internship"`` → ``"internship"`` (literal expects lowercase)
    - Comma-separated skill strings → ``list[str]``
    """
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        cleaned[key] = _strip_nan(value)

    cleaned = _coerce_dates(cleaned)
    cleaned = _coerce_job_type(cleaned)
    cleaned = _coerce_skill_lists(cleaned)

    return Job.model_validate(cleaned)


def _coerce_dates(row: dict[str, Any]) -> dict[str, Any]:
    """Parse ISO date strings for ``posting_date`` and ``deadline``."""
    from datetime import date, datetime

    for key in ("posting_date", "deadline"):
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, date) and not isinstance(value, datetime):
            continue
        if isinstance(value, datetime):
            row[key] = value.date()
            continue
        if isinstance(value, str):
            try:
                row[key] = date.fromisoformat(value)
            except ValueError:
                logger.warning(
                    "invalid_date_string",
                    extra={"key": key, "value": value},
                )
                row[key] = None
    return row


def _coerce_job_type(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize Excel ``Job_Type`` values to lowercase literals."""
    raw = row.get("job_type")
    if not isinstance(raw, str):
        return row
    normalized = raw.strip().lower()
    valid = {"full-time", "part-time", "internship", "thesis", "contract", "unknown"}
    if normalized in valid:
        row["job_type"] = normalized
    else:
        # Unknown bucket — keep the data, mark as unknown, log for review.
        logger.info("unknown_job_type", extra={"value": raw})
        row["job_type"] = "unknown"
    return row


def _coerce_skill_lists(row: dict[str, Any]) -> dict[str, Any]:
    """Split comma- or semicolon-separated skill strings into lists."""
    for key in ("key_matching_skills", "missing_skills"):
        value = row.get(key)
        if value is None or isinstance(value, list):
            continue
        if isinstance(value, str):
            # Comma is primary; semicolon tolerated.
            parts = [p.strip() for p in value.replace(";", ",").split(",")]
            row[key] = [p for p in parts if p]
    return row


def _strip_nan(value: Any) -> Any:
    """Convert pandas NaN/NaT to None; leave everything else as-is."""
    if value is None:
        return None
    # pandas types aren't always hashable; compare via pd.isna which handles
    # NaN, NaT, and None uniformly.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
