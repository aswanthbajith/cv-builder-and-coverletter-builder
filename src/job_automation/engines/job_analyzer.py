"""JobAnalyzer — extract structured understanding of the job via the LLM.

The first LLM call in the pipeline. Produces :class:`JobAnalysis` with
role archetype, themes, must-haves, nice-to-haves, and seniority. Later
engines consume this output.

Inputs:
    ctx.job, ctx.graph
Outputs:
    ctx.job_analysis
"""

from __future__ import annotations

import json

from job_automation.engines.base import PipelineContext
from job_automation.engines.llm_client import LLMClient
from job_automation.logging import get_logger
from job_automation.models.analysis import JobAnalysis

logger = get_logger(__name__)


class JobAnalyzer:
    """LLM-driven job analyzer. Async per the BaseEngine convention."""

    name = "job_analyzer"
    timeout_s = 30.0
    requires = frozenset({"job"})
    produces = frozenset({"job_analysis"})

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        job = ctx.job
        system = (
            "You are a job-posting analyzer. Given a job posting, output a JSON "
            "object with exactly these keys: role_archetype (string), themes "
            "(array of 3-7 short strings), must_haves (array of strings), "
            "nice_to_haves (array of strings), seniority (one of 'junior', "
            "'mid', 'senior', 'research')."
        )
        user = json.dumps(
            {
                "title": job.job_title,
                "company": job.company,
                "location": job.location,
                "description": job.job_description,
                "required_skills": job.required_skills,
                "preferred_qualifications": job.preferred_qualifications,
            },
            ensure_ascii=False,
        )
        schema = {
            "type": "object",
            "properties": {
                "role_archetype": {"type": "string"},
                "themes": {"type": "array", "items": {"type": "string"}},
                "must_haves": {"type": "array", "items": {"type": "string"}},
                "nice_to_haves": {"type": "array", "items": {"type": "string"}},
                "seniority": {
                    "type": "string",
                    "enum": ["junior", "mid", "senior", "research"],
                },
            },
            "required": ["role_archetype", "themes", "must_haves", "nice_to_haves", "seniority"],
        }
        try:
            raw = await self._llm.complete_json(
                system=system,
                user=user,
                schema=schema,
            )
            ctx.job_analysis = JobAnalysis.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            # On any failure, fall back to a heuristic analysis so the
            # pipeline can continue without LLM output.
            logger.warning(
                "job_analyzer_fallback",
                extra={"error": str(exc)},
            )
            ctx.job_analysis = JobAnalysis(
                role_archetype=job.job_title,
                themes=[],
                must_haves=[],
                nice_to_haves=[],
                seniority="junior",
            )
            ctx.errors[self.name] = str(exc)
        return ctx


__all__ = ["JobAnalyzer"]
