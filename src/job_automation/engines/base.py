"""Engine base types — :class:`BaseEngine`, :class:`PipelineContext`.

Engines are async functions that read typed fields from a shared
:class:`PipelineContext`, do work, and write new typed fields back. The
:class:`Pipeline` orchestrator chains them and handles the critic loop.

Engines declare ``requires`` and ``produces`` so the orchestrator can
validate the data flow at runtime and produce useful error messages when a
field is missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from job_automation.models.atomic import ScoredExperience
from job_automation.models.analysis import ATSKeyword, JobAnalysis, SkillGapReport
from job_automation.models.company import CompanyProfile
from job_automation.models.job import Job
from job_automation.models.profile import Profile
from job_automation.models.results import MatchResult, ResumeContent
from job_automation.models.review import ATSReport, CriticReview, RecruiterReview

if TYPE_CHECKING:
    from job_automation.knowledge.graph import KnowledgeGraph
    from job_automation.models.atomic import AtomicExperience


@dataclass
class PipelineContext:
    """Shared mutable state flowing between engines.

    Engines read from fields listed in their ``requires`` set and write to
    fields listed in their ``produces`` set. All other fields are untouched.

    ``errors`` is a dict of error messages keyed by engine name. The
    orchestrator consults it to decide whether a partial failure is
    shippable.
    """

    run_id: str
    job: Job
    graph: "KnowledgeGraph"
    profile: Profile

    match: MatchResult | None = None
    job_analysis: JobAnalysis | None = None
    company_profile: CompanyProfile | None = None
    ats_keywords: list[ATSKeyword] = field(default_factory=list)
    skill_gaps: SkillGapReport | None = None
    selected_experiences: list[ScoredExperience] = field(default_factory=list)
    selected_projects: list[ScoredExperience] = field(default_factory=list)
    rewritten_bullets: dict[str, list[str]] = field(default_factory=dict)
    rewritten_project_bullets: dict[str, list[str]] = field(default_factory=dict)
    summary: str | None = None
    draft_resume: ResumeContent | None = None
    critic_iterations: list[CriticReview] = field(default_factory=list)
    ats_score: ATSReport | None = None
    recruiter_review: RecruiterReview | None = None
    resume_tex_path: Path | None = None
    resume_pdf_path: Path | None = None

    # Telemetry
    timings_ms: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class EngineResult:
    """Outcome of running one engine.

    Carries timing + an optional error string for logging. The orchestrator
    accumulates these into ``ctx.errors`` and ``ctx.timings_ms``.
    """

    name: str
    duration_ms: float
    error: str | None = None


@runtime_checkable
class BaseEngine(Protocol):
    """Protocol every M2 engine implements.

    Engines are async because (a) the Gemini SDK ships async clients,
    (b) the M3 (Celery) layer reuses these methods, (c) explicit ``await``
    boundaries let the orchestrator apply per-engine timeouts.

    Class attributes declared on subclasses:
        name: stable id used in logs and ``ctx.errors``.
        timeout_s: max wall-clock seconds before the orchestrator cancels.
        requires: ctx fields this engine reads (for validation + docs).
        produces: ctx fields this engine writes (for validation + docs).
    """

    name: str
    timeout_s: float
    requires: frozenset[str]
    produces: frozenset[str]

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        """Execute the engine. Mutates ``ctx`` in place and returns it."""
        ...


__all__ = ["BaseEngine", "EngineResult", "PipelineContext"]