"""ResumeCritic — judge the draft and trigger revisions.

LLM-driven judge. Inspects the draft :class:`ResumeContent` against the
job analysis and company profile and emits a :class:`CriticReview` with
verdict (pass / revise / reject), issues, fixes, and a 0-10 score.

Pre-LLM deterministic checks run first:
- Bullet count must be ≥ 6.
- At least 70% of bullets must contain a number or % (specificity).
- AI-tell phrases (``passionate``, ``delve``, ``leverage``) cannot appear.

Inputs:
    ctx.draft_resume, ctx.job_analysis, ctx.company_profile
Outputs:
    ctx.critic_iterations (appended)
"""

from __future__ import annotations

import json
import re

from job_automation.engines.base import PipelineContext
from job_automation.engines.llm_client import LLMClient
from job_automation.logging import get_logger
from job_automation.models.results import ResumeContent
from job_automation.models.review import CriticReview

logger = get_logger(__name__)

_AI_TELLS = (
    "passionate",
    "driven",
    "delve",
    "leverage",
    "spearhead",
    "tapestry",
    "in today's",
    "in the realm of",
    "navigate the",
    "robust solution",
)


class ResumeCritic:
    """LLM-driven resume critic with deterministic pre-filter."""

    name = "resume_critic"
    timeout_s = 20.0
    requires = frozenset({"draft_resume", "job_analysis"})
    produces = frozenset({"critic_iterations"})

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.draft_resume is None:
            # Nothing to critique — pass through.
            ctx.critic_iterations.append(
                CriticReview(verdict="pass", issues=[], fixes=[], score=5.0)
            )
            return ctx

        # Deterministic pre-filter.
        prefilter_issues = self._deterministic_check(ctx.draft_resume)
        if any("ai_tell" in i for i in prefilter_issues):
            # Hard fail — don't even bother with the LLM judge.
            review = CriticReview(
                verdict="reject",
                issues=prefilter_issues,
                fixes=["Remove AI-tell phrases"],
                score=3.0,
            )
            ctx.critic_iterations.append(review)
            return ctx

        system = (
            "You are a strict resume reviewer. Given the candidate's draft "
            "resume (JSON) and the target job analysis (JSON), produce a JSON "
            "object with keys 'verdict' ('pass'|'revise'|'reject'), 'issues' "
            "(array of short issue strings), 'fixes' (array of actionable "
            "fixes), and 'score' (0-10). Reject only if the resume contains "
            "fabricated facts or AI-tell phrases. Pass if it is ready to "
            "send. Revise otherwise."
        )
        user = json.dumps(
            {
                "draft": ctx.draft_resume.model_dump(),
                "job_analysis": ctx.job_analysis.model_dump() if ctx.job_analysis else None,
                "company_profile": ctx.company_profile.model_dump() if ctx.company_profile else None,
            },
            ensure_ascii=False,
        )
        schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "revise", "reject"]},
                "issues": {"type": "array", "items": {"type": "string"}},
                "fixes": {"type": "array", "items": {"type": "string"}},
                "score": {"type": "number", "minimum": 0, "maximum": 10},
            },
            "required": ["verdict", "issues", "fixes", "score"],
        }
        try:
            response = await self._llm.complete_json(system=system, user=user, schema=schema)
            review = CriticReview.model_validate(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("resume_critic_fallback", extra={"error": str(exc)})
            review = CriticReview(
                verdict="pass",
                issues=prefilter_issues,
                fixes=[],
                score=6.0,
            )
            ctx.errors[self.name] = str(exc)

        # Merge prefilter issues with LLM issues for the final review.
        if prefilter_issues and not review.issues:
            review = CriticReview(
                verdict=review.verdict,
                issues=prefilter_issues,
                fixes=review.fixes,
                score=review.score,
            )
        ctx.critic_iterations.append(review)
        return ctx

    def _deterministic_check(self, resume: ResumeContent) -> list[str]:
        """Return prefilter issue strings. Empty list = pass."""
        issues: list[str] = []
        all_bullets: list[str] = []
        for exp in resume.experience:
            for b in exp.get("description", []) or []:
                all_bullets.append(str(b))
        for proj in resume.projects:
            for b in proj.get("description", []) or []:
                all_bullets.append(str(b))

        if len(all_bullets) < 6:
            issues.append("insufficient_bullets")

        quantified = sum(1 for b in all_bullets if re.search(r"\d", b))
        if all_bullets and quantified / len(all_bullets) < 0.7:
            issues.append("low_specificity")

        blob = (resume.summary or "").lower() + " ".join(all_bullets).lower()
        for tell in _AI_TELLS:
            if tell in blob:
                issues.append(f"ai_tell:{tell}")
                break

        return issues


__all__ = ["ResumeCritic"]


# Mark ResumeContent import for runtime use.
_ = ResumeContent
