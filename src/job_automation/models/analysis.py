"""Job analysis + ATS keyword + skill-gap models — engine I/O contracts.

These are the typed outputs of the first three engines in the pipeline:

- :class:`JobAnalysis` — output of :class:`JobAnalyzer`
- :class:`ATSKeyword` — output of :class:`ATSKeywordExtractor`
- :class:`SkillGapReport` — output of :class:`SkillGapAnalyzer`

All are Pydantic v2, ``frozen=True``, ``extra="ignore"`` per the M1 contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobAnalysis(BaseModel):
    """Structured understanding of a job produced by ``JobAnalyzer``.

    Combines the role-family detected by the heuristic pass with the themes,
    must-haves, and nice-to-haves extracted by the LLM. ``seniority`` is the
    candidate's level the role is targeting — used by the rewriter to pick
    appropriately-pitched vocabulary.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    role_archetype: str = Field(
        description="Short label of the role, e.g. 'GPU Infrastructure Engineer'.",
    )
    themes: list[str] = Field(
        default_factory=list,
        description="3-7 high-level themes the role emphasizes.",
    )
    must_haves: list[str] = Field(
        default_factory=list,
        description="Skills or qualifications marked required by the job text.",
    )
    nice_to_haves: list[str] = Field(
        default_factory=list,
        description="Skills or qualifications marked preferred or 'a plus'.",
    )
    seniority: Literal["junior", "mid", "senior", "research"] = "junior"


class ATSKeyword(BaseModel):
    """One keyword with weight and source provenance.

    ``weight`` is 0..1; ``source`` indicates whether the keyword came from
    the job description, the company profile, or the inferred theme list —
    used by the cover-letter generator to vary terminology.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    term: str
    weight: float = Field(ge=0.0, le=1.0)
    source: Literal["job", "company", "inferred"] = "job"


class SkillGapReport(BaseModel):
    """Output of :class:`SkillGapAnalyzer`.

    Splits the candidate's atomic experiences into matched / partial /
    missing / transferable buckets relative to the job's ATS keywords.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    matched: list[str] = Field(
        default_factory=list,
        description="Skills the candidate fully covers.",
    )
    partial: list[str] = Field(
        default_factory=list,
        description="Skills the candidate partially covers via adjacent experience.",
    )
    missing: list[str] = Field(
        default_factory=list,
        description="Skills the job asks for but the candidate cannot demonstrate.",
    )
    transferable: list[str] = Field(
        default_factory=list,
        description="Skills the candidate has that the job didn't explicitly ask for but should be highlighted.",
    )


__all__ = ["ATSKeyword", "JobAnalysis", "SkillGapReport"]