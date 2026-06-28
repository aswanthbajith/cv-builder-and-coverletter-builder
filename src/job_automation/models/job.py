"""Job posting model.

Mirrors the columns loaded by the legacy ``ExcelLoader`` plus the optional
columns listed in ``workflow_requirements.md``. All fields are strict — int
won't coerce to str, etc. Unknown Excel columns are silently dropped
(``extra="ignore"``) so the loader can evolve without breaking the model.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobType = Literal[
    "full-time", "part-time", "internship", "thesis", "contract", "unknown",
]


class Job(BaseModel):
    """A single job posting as ingested from Excel or a future API source."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        strict=True,
    )

    # Required — loader falls back to empty string if Excel column is missing,
    # but the model still requires non-empty strings at validation time.
    company: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    job_description: str = Field(min_length=1)

    # Optional descriptive fields. URL kept as plain str to match the legacy
    # loader (which uses URL only for an exact-equality dedup check). Tighten
    # to HttpUrl in a follow-up once the loader is fixed to validate URIs.
    required_skills: str | None = None
    preferred_qualifications: str | None = None
    application_url: str | None = None
    posting_date: date | None = None
    deadline: date | None = None
    job_type: JobType = "unknown"
    source: str | None = None

    # Pre-existing score (e.g. from a previous run's match analysis)
    match_score: float | None = Field(default=None, ge=0.0, le=100.0)
    key_matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)

    # Pipeline-internal — populated by the orchestrator, ignored if absent.
    duplicate: bool = False
    duplicate_of: int | None = None
    deduplication_reason: str | None = None


__all__ = ["Job", "JobType"]