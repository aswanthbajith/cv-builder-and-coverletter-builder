"""Pipeline result models.

These replace the untyped ``Dict[str, Any]`` and ``@dataclass`` that flow
through the current pipeline. Every engine returns one of these so M2 can
adopt dependency injection without touching consumer code.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from job_automation.models.job import Job

Status = Literal["proceed", "review", "skip"]


class MatchResult(BaseModel):
    """Output of :class:`job_automation.engines.matcher.JobMatcher.analyze_job`.

    Field names are kept identical to the legacy ``@dataclass MatchResult``
    in ``src/matcher.py`` so M2 can swap the dataclass import for this model
    with a one-line change.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    overall_score: float = Field(ge=0.0, le=100.0)
    education_score: float = Field(ge=0.0, le=100.0)
    skills_score: float = Field(ge=0.0, le=100.0)
    programming_score: float = Field(ge=0.0, le=100.0)
    research_score: float = Field(ge=0.0, le=100.0)
    experience_score: float = Field(ge=0.0, le=100.0)

    reasoning: str
    missing_skills: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    status: Status


class ResumeContent(BaseModel):
    """Structured resume content before LaTeX rendering (M2+)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    contact: dict[str, str]
    summary: str
    skills: list[str]
    experience: list[dict[str, object]] = Field(default_factory=list)
    education: list[dict[str, object]] = Field(default_factory=list)
    projects: list[dict[str, object]] = Field(default_factory=list)
    certifications: list[object] = Field(default_factory=list)
    languages: list[dict[str, str]] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    keyword_coverage: str = "0%"
    matched_keywords: int = 0
    total_keywords: int = 0


class GenerationResult(BaseModel):
    """End-to-end pipeline output for one job.

    Replaces the dict returned by ``main.process_job`` (lines 62-75). The
    ``error`` field carries a short message when one engine failed but the
    others still produced output — partial-success is a legitimate outcome.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    job: Job
    match: MatchResult
    resume_tex_path: Path | None = None
    resume_pdf_path: Path | None = None
    cover_letter_path: Path | None = None
    generated_at: datetime
    error: str | None = None


__all__ = ["GenerationResult", "MatchResult", "ResumeContent", "Status"]
