"""SummaryGenerator — produce the 2-3 sentence professional summary.

LLM-driven. Combines the candidate's role-archetype, the job's
role-archetype, and 1-2 of the top-selected atoms into a 50-word
summary that survives the AI-phrase detector.

Inputs:
    ctx.job_analysis, ctx.company_profile, ctx.selected_experiences,
    ctx.graph
Outputs:
    ctx.summary
"""

from __future__ import annotations

import json

from job_automation.engines.base import PipelineContext
from job_automation.engines.llm_client import LLMClient
from job_automation.logging import get_logger

logger = get_logger(__name__)


class SummaryGenerator:
    """LLM-driven summary writer."""

    name = "summary_generator"
    timeout_s = 15.0
    requires = frozenset({"job_analysis", "selected_experiences"})
    produces = frozenset({"summary"})

    def __init__(self, llm: LLMClient, *, max_words: int = 50) -> None:
        self._llm = llm
        self._max_words = max_words

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        job = ctx.job
        analysis = ctx.job_analysis
        top_atoms = ctx.selected_experiences[:2]

        system = (
            "You write professional summaries for technical resumes. Output "
            "a JSON object with one key, 'summary', whose value is a single "
            "string of at most 50 words. The summary must avoid AI tells "
            "('passionate', 'driven', 'leverage', 'delve'). Use only the "
            "candidate's actual experience; do not invent metrics. When a "
            "company_profile is provided, weave in 1 short phrase that "
            "aligns the candidate's experience with the company's focus "
            "areas or terminology."
        )
        user = json.dumps(
            {
                "candidate_name": ctx.profile.name,
                "job_title": job.job_title,
                "company": job.company,
                "role_archetype": analysis.role_archetype if analysis else job.job_title,
                "themes": analysis.themes if analysis else [],
                "company_profile": (
                    ctx.company_profile.model_dump() if ctx.company_profile else None
                ),
                "top_experiences": [
                    {
                        "title": a.experience.title,
                        "outcome": a.experience.outcome,
                        "technologies": a.experience.technologies,
                    }
                    for a in top_atoms
                ],
                "max_words": self._max_words,
            },
            ensure_ascii=False,
        )
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        try:
            response = await self._llm.complete_json(system=system, user=user, schema=schema)
            summary = str(response.get("summary", "")).strip()
            ctx.summary = summary or self._fallback_summary(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.warning("summary_generator_fallback", extra={"error": str(exc)})
            ctx.summary = self._fallback_summary(ctx)
            ctx.errors[self.name] = str(exc)
        return ctx

    def _fallback_summary(self, ctx: PipelineContext) -> str:
        """Return a deterministic summary built from the profile + job."""
        role = ctx.job_analysis.role_archetype if ctx.job_analysis else ctx.job.job_title
        top = ctx.selected_experiences[:1]
        if top:
            return (
                f"M.Sc. student targeting {role} roles. "
                f"Most relevant experience: {top[0].experience.outcome}"
            )
        return f"M.Sc. student targeting {role} roles."


__all__ = ["SummaryGenerator"]
