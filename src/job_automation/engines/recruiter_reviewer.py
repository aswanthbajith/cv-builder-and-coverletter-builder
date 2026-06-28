"""RecruiterReviewer — LLM-as-recruiter second-opinion judge.

Reads the draft resume + the last critic review + the job analysis and
emits a :class:`RecruiterReview` with verdict (interview / review /
reject), red_flags, and likely followup questions.

Distinct from :class:`ResumeCritic`: the critic cares about resume
quality, the recruiter cares about whether a human would put this on
the interview pile. The two verdicts together decide whether to ship.

Inputs:
    ctx.draft_resume, ctx.critic_iterations[-1], ctx.job_analysis
Outputs:
    ctx.recruiter_review
"""

from __future__ import annotations

import json

from job_automation.engines.base import PipelineContext
from job_automation.engines.llm_client import LLMClient
from job_automation.logging import get_logger
from job_automation.models.review import RecruiterReview

logger = get_logger(__name__)


class RecruiterReviewer:
    """LLM-as-recruiter judge."""

    name = "recruiter_reviewer"
    timeout_s = 20.0
    requires = frozenset({"draft_resume", "job_analysis"})
    produces = frozenset({"recruiter_review"})

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.draft_resume is None:
            ctx.recruiter_review = RecruiterReview(
                verdict="reject",
                red_flags=["no_draft_resume"],
                followups=[],
                rationale="No draft resume to review.",
            )
            ctx.errors[self.name] = "no_draft_resume"
            return ctx

        system = (
            "You are a recruiter reviewing a candidate's resume for a specific "
            "job. Output a JSON object with keys: 'verdict' ('interview' | "
            "'review' | 'reject'), 'red_flags' (array of short issue strings), "
            "'followups' (array of questions you'd ask on a phone screen), and "
            "'rationale' (1-2 sentence rationale). Reject only if the resume "
            "would be set aside; 'review' if borderline."
        )
        user = json.dumps(
            {
                "draft": ctx.draft_resume.model_dump(),
                "job_analysis": ctx.job_analysis.model_dump() if ctx.job_analysis else None,
                "last_critic_review": (
                    ctx.critic_iterations[-1].model_dump() if ctx.critic_iterations else None
                ),
            },
            ensure_ascii=False,
        )
        schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["interview", "review", "reject"]},
                "red_flags": {"type": "array", "items": {"type": "string"}},
                "followups": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["verdict", "red_flags", "followups", "rationale"],
        }
        try:
            response = await self._llm.complete_json(system=system, user=user, schema=schema)
            ctx.recruiter_review = RecruiterReview.model_validate(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recruiter_reviewer_fallback", extra={"error": str(exc)})
            ctx.recruiter_review = RecruiterReview(
                verdict="review",
                red_flags=[],
                followups=[],
                rationale="LLM judge unavailable; defaulting to review.",
            )
            ctx.errors[self.name] = str(exc)
        return ctx


__all__ = ["RecruiterReviewer"]
