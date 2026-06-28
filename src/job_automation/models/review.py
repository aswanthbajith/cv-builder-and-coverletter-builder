"""Review models — ResumeCritic, ATSValidator, RecruiterReviewer outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CriticReview(BaseModel):
    """Output of :class:`ResumeCritic`.

    Iteratively produced by the critic loop; the orchestrator consults the
    last review to decide whether to accept the draft or trigger another
    rewrite pass.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    verdict: Literal["pass", "revise", "reject"]
    issues: list[str] = Field(
        default_factory=list,
        description="Concrete issues the critic flagged in the draft.",
    )
    fixes: list[str] = Field(
        default_factory=list,
        description="Actionable fixes the AchievementRewriter should apply next iteration.",
    )
    score: float = Field(
        ge=0.0,
        le=10.0,
        description="Quality score on a 0-10 scale. ≥7 = pass, 5-7 = revise, <5 = reject.",
    )


class ATSReport(BaseModel):
    """Output of :class:`ATSValidator`.

    Deterministic — no LLM. Computes keyword coverage, density, page count,
    and whether the draft passes the configured ATS target.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    overall: float = Field(ge=0.0, le=100.0, description="Composite ATS score.")
    coverage: float = Field(
        ge=0.0, le=1.0, description="Fraction of required keywords present in the resume text.",
    )
    density: float = Field(
        ge=0.0, le=1.0, description="Fraction of total words that are ATS keywords.",
    )
    length_ok: bool = Field(description="Whether the resume fits the configured page limit.")
    passed: bool = Field(description="True if overall ≥ the configured target score.")


class RecruiterReview(BaseModel):
    """Output of :class:`RecruiterReviewer`.

    LLM-judged. A 'red flag' is anything that would prompt a recruiter to
    set the resume aside (vague claims, AI-tells, fabricated metrics).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    verdict: Literal["interview", "review", "reject"]
    red_flags: list[str] = Field(default_factory=list)
    followups: list[str] = Field(
        default_factory=list,
        description="Questions the recruiter would likely ask in a phone screen.",
    )
    rationale: str = Field(description="1-2 sentence rationale for the verdict.")


__all__ = ["ATSReport", "CriticReview", "RecruiterReview"]