"""Engine pipeline — 12 engines that turn a Job + Profile into a PDF.

The M2 architecture replaces the legacy ``resume_generator.py`` keyword-edit
pipeline with a constructor pipeline:

    KnowledgeGraph -> JobAnalyzer -> CompanyResearcher -> ATSKeywordExtractor
                  -> SkillGapAnalyzer -> ExperienceSelector -> AchievementRewriter
                  -> ProjectSelector -> SummaryGenerator -> ResumeCritic (loop)
                  -> ATSValidator -> RecruiterReviewer -> LaTeXGenerator -> PDF

Every engine is async and conforms to :class:`BaseEngine`. The orchestrator
in ``orchestrator.py`` wires them in order and runs the critic loop.

This module exports the base types only — each engine lives in its own file.
"""

from __future__ import annotations

from job_automation.engines.base import BaseEngine, EngineResult, PipelineContext
from job_automation.engines.exceptions import (
    CriticRejected,
    EngineError,
    GroundingViolation,
    LLMUnavailable,
)
from job_automation.engines.orchestrator import Pipeline

__all__ = [
    "BaseEngine",
    "CriticRejected",
    "EngineError",
    "EngineResult",
    "GroundingViolation",
    "LLMUnavailable",
    "Pipeline",
    "PipelineContext",
]