"""Company research output model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CompanyProfile(BaseModel):
    """Structured research output for a target company.

    Produced by the ``CompanyResearcher`` engine (which delegates the
    actual web search to Claude Code's ``WebSearch`` tool, per the M2 plan)
    and consumed by ``SummaryGenerator`` and ``ATSKeywordExtractor``.

    All fields default to empty so a partial / failed research call still
    produces a valid object and lets the pipeline continue.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    company: str
    focus_areas: list[str] = Field(
        default_factory=list,
        description="What the company is currently focused on (products, research).",
    )
    technologies: list[str] = Field(
        default_factory=list,
        description="Technologies they publicly mention in job ads or engineering blog.",
    )
    terminology: list[str] = Field(
        default_factory=list,
        description="Vocabulary they repeatedly use (e.g. 'scalability', 'kernel', 'workflow').",
    )
    culture_signals: list[str] = Field(
        default_factory=list,
        description="Phrases the company uses to describe itself (e.g. 'fast-paced', 'research-driven').",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="URLs used as the basis for this profile (for auditing).",
    )

    @classmethod
    def empty(cls, company: str) -> "CompanyProfile":
        """Return an empty profile — used when research fails or is skipped."""
        return cls(company=company)


__all__ = ["CompanyProfile"]