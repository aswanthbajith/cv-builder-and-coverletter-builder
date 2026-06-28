"""Candidate profile model.

Mirrors the JSON files under ``profile/``. The legacy ``JobMatcher`` reads
these as plain dicts — M2 will switch it to consume :class:`Profile` directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExperienceEntry(BaseModel):
    """One position in the candidate's work history."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    title: str
    company: str
    location: str | None = None
    period: str = ""
    description: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    """One project (academic, personal, or professional)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    description: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """One degree program. Kept loose — different countries use different
    fields (GPA, CGPA, grade, thesis)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    degree: str
    institution: str
    period: str | None = None
    grade: str | None = None
    highlights: list[str] = Field(default_factory=list)
    coursework: list[str] = Field(default_factory=list)
    relevant_coursework: list[str] = Field(default_factory=list)


class LanguageEntry(BaseModel):
    """Spoken language and proficiency label."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    language: str
    proficiency: str


class Profile(BaseModel):
    """The full candidate profile, assembled from one or more JSON files."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    contact: dict[str, str] = Field(default_factory=dict)
    current_role: str | None = None
    professional_summary: str | None = None

    technical_skills: dict[str, list[str]] = Field(default_factory=dict)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    languages: list[LanguageEntry] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    certifications: list[Any] = Field(default_factory=list)
    publications: list[Any] = Field(default_factory=list)
    key_achievements: list[str] = Field(default_factory=list)


__all__ = [
    "EducationEntry",
    "ExperienceEntry",
    "LanguageEntry",
    "Profile",
    "ProjectEntry",
]