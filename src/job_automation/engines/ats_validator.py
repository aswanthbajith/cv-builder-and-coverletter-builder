"""ATSValidator — deterministic ATS score.

Computes keyword coverage, density, page-count estimate, and an overall
score. No LLM call.

Inputs:
    ctx.draft_resume, ctx.ats_keywords
Outputs:
    ctx.ats_score
"""

from __future__ import annotations

import re

from job_automation.engines.base import PipelineContext
from job_automation.config import load_config
from job_automation.logging import get_logger
from job_automation.models.review import ATSReport

logger = get_logger(__name__)

_WORD_RE = re.compile(r"[a-z0-9+#./\-]+")


class ATSValidator:
    """Deterministic ATS validator."""

    name = "ats_validator"
    timeout_s = 1.0
    requires = frozenset({"draft_resume", "ats_keywords"})
    produces = frozenset({"ats_score"})

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.draft_resume is None:
            ctx.ats_score = ATSReport(overall=0.0, coverage=0.0, density=0.0, length_ok=False, passed=False)
            ctx.errors[self.name] = "no_draft_resume"
            return ctx

        resume = ctx.draft_resume
        text = _resume_to_text(resume)
        words = _WORD_RE.findall(text.lower())
        word_count = len(words) or 1

        # Coverage: fraction of required keywords present.
        covered = 0
        for kw in ctx.ats_keywords:
            if kw.term.lower() in text.lower():
                covered += 1
        coverage = covered / len(ctx.ats_keywords) if ctx.ats_keywords else 0.0

        # Density: fraction of words that are ATS keywords.
        keyword_set = {kw.term.lower() for kw in ctx.ats_keywords}
        keyword_hits = sum(1 for w in words if w in keyword_set)
        density = keyword_hits / word_count

        # Length: rough estimate (300-350 words/page for a tight single-page resume).
        page_budget = load_config().ats.max_resume_pages
        length_ok = word_count <= page_budget * 350

        # Overall: weighted blend.
        density_penalty = max(0.0, density - load_config().ats.keyword_density_max)
        overall = (
            60.0 * coverage
            + 30.0 * (1.0 if length_ok else 0.0)
            + 10.0 * max(0.0, 1.0 - density_penalty * 10.0)
        )
        target = load_config().ats.target_score
        passed = overall >= target

        ctx.ats_score = ATSReport(
            overall=round(overall, 1),
            coverage=round(coverage, 3),
            density=round(density, 4),
            length_ok=length_ok,
            passed=passed,
        )
        logger.info(
            "ats_validated",
            extra={
                "overall": ctx.ats_score.overall,
                "coverage": ctx.ats_score.coverage,
                "density": ctx.ats_score.density,
                "length_ok": length_ok,
            },
        )
        return ctx


def _resume_to_text(resume) -> str:
    parts: list[str] = [resume.summary or ""]
    for exp in resume.experience:
        parts.append(str(exp.get("title", "")))
        parts.append(str(exp.get("company", "")))
        for b in exp.get("description", []) or []:
            parts.append(str(b))
    for proj in resume.projects:
        parts.append(str(proj.get("name", "")))
        for b in proj.get("description", []) or []:
            parts.append(str(b))
    for skill_line in resume.skills:
        parts.append(str(skill_line))
    return " ".join(parts)


__all__ = ["ATSValidator"]
