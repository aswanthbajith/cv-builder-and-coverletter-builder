"""AchievementRewriter — produce role-tailored bullets via the LLM.

The central engine for differentiation. For every selected atom, asks the
LLM to produce 1-3 bullet sentences that:

- Lead with the action verb in the source atom.
- Use the role-family-specific RewriteHint if one exists, otherwise use
  the atom's natural phrasing.
- Surface exactly the metrics in the atom's ``metrics`` field.
- Stay within the senior register appropriate for ``job_analysis.seniority``.

The grounding check (:mod:`engines.grounding`) validates every rewrite
before it lands in ``ctx.rewritten_bullets``. On grounding failure the
engine re-prompts with a "do not invent" instruction; on second failure
the engine ships the original atom text (truthfulness > variation).

Inputs:
    ctx.selected_experiences, ctx.selected_projects, ctx.ats_keywords,
    ctx.job_analysis, optional ``ctx.critic_iterations[-1].fixes`` (used as
    feedback on subsequent iterations).
Outputs:
    ctx.rewritten_bullets, ctx.rewritten_project_bullets
"""

from __future__ import annotations

import json

from job_automation.engines.base import PipelineContext
from job_automation.engines.exceptions import GroundingViolation
from job_automation.engines.grounding import validate_grounding
from job_automation.engines.llm_client import LLMClient
from job_automation.logging import get_logger
from job_automation.models.atomic import ScoredExperience

logger = get_logger(__name__)


class AchievementRewriter:
    """LLM-driven bullet rewriter with grounding validation."""

    name = "achievement_rewriter"
    timeout_s = 30.0
    requires = frozenset({"selected_experiences", "selected_projects", "job_analysis", "ats_keywords"})
    produces = frozenset({"rewritten_bullets", "rewritten_project_bullets"})

    def __init__(
        self,
        llm: LLMClient,
        *,
        max_attempts: int = 2,
        max_bullets_per_entry: int = 4,
    ) -> None:
        self._llm = llm
        self._max_attempts = max_attempts
        self._max_bullets_per_entry = max_bullets_per_entry

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        feedback = self._extract_feedback(ctx)
        ctx.rewritten_bullets = await self._rewrite_group(
            ctx.selected_experiences,
            ctx,
            feedback=feedback,
            group_label="work",
        )
        ctx.rewritten_project_bullets = await self._rewrite_group(
            ctx.selected_projects,
            ctx,
            feedback=feedback,
            group_label="project",
        )
        return ctx

    def _extract_feedback(self, ctx: PipelineContext) -> str:
        if not ctx.critic_iterations:
            return ""
        last = ctx.critic_iterations[-1]
        if last.verdict == "pass" or not last.fixes:
            return ""
        return "Apply these fixes from the previous critic pass: " + "; ".join(last.fixes)

    async def _rewrite_group(
        self,
        scored: list[ScoredExperience],
        ctx: PipelineContext,
        *,
        feedback: str,
        group_label: str,
    ) -> dict[str, list[str]]:
        """Rewrite a list of atoms into bullets, grouped by source_ref."""
        if not scored:
            return {}

        # Group atoms by source_ref so the LLM sees coherent entries.
        grouped: dict[str, list[ScoredExperience]] = {}
        for s in scored:
            grouped.setdefault(s.experience.source_ref, []).append(s)

        system = (
            "You are a resume bullet rewriter. Given a JSON object containing a "
            "list of 'atoms' (small atomic experiences from the candidate's "
            "career) and a 'job_analysis' object describing the target job, "
            "produce a JSON object mapping each 'source_ref' to an array of "
            "1-3 bullet sentences. Each bullet must lead with the action verb "
            "from the source atom and must use only metrics, technologies, "
            "and project names that appear in the source atom. Do not invent "
            "any numbers, tools, or projects. Output strictly valid JSON."
        )

        rewritten: dict[str, list[str]] = {}
        for source_ref, atoms in grouped.items():
            user_payload = {
                "job_analysis": ctx.job_analysis.model_dump() if ctx.job_analysis else None,
                "ats_keywords_top10": [
                    {"term": k.term, "weight": k.weight} for k in ctx.ats_keywords[:10]
                ],
                "source_ref": source_ref,
                "group_label": group_label,
                "atoms": [
                    {
                        "id": a.experience.id,
                        "title": a.experience.title,
                        "action_verb": a.experience.action_verb,
                        "context": a.experience.context,
                        "details": a.experience.details,
                        "outcome": a.experience.outcome,
                        "technologies": a.experience.technologies,
                        "metrics": a.experience.metrics,
                        "rewrite_hint": (
                            a.rewrite.emphasis if a.rewrite is not None else None
                        ),
                    }
                    for a in atoms
                ],
                "feedback": feedback,
            }
            user = json.dumps(user_payload, ensure_ascii=False)
            schema = {
                "type": "object",
                "properties": {
                    "bullets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": self._max_bullets_per_entry,
                    }
                },
                "required": ["bullets"],
            }

            source_atoms = [a.experience for a in atoms]
            attempt = 0
            accepted: list[str] | None = None
            while attempt < self._max_attempts:
                try:
                    if attempt > 0:
                        # Re-prompt with stricter instruction.
                        strict_user = user + "\n\nIMPORTANT: Do not invent metrics. Use only what is in the source atoms."
                    else:
                        strict_user = user
                    response = await self._llm.complete_json(
                        system=system,
                        user=strict_user,
                        schema=schema,
                    )
                    bullets = response.get("bullets", [])
                    if not isinstance(bullets, list):
                        raise ValueError("bullets is not a list")
                    candidates = [str(b).strip() for b in bullets if str(b).strip()]
                    # Grounding check across all candidates vs source atoms.
                    violations_per_bullet = [
                        validate_grounding(b, source_atoms) for b in candidates
                    ]
                    if any(violations_per_bullet):
                        bad = sum(1 for v in violations_per_bullet if v)
                        logger.warning(
                            "achievement_rewriter_grounding_failed",
                            extra={"source_ref": source_ref, "bad_bullets": bad, "attempt": attempt},
                        )
                        attempt += 1
                        continue
                    accepted = candidates[: self._max_bullets_per_entry]
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "achievement_rewriter_attempt_failed",
                        extra={"source_ref": source_ref, "attempt": attempt, "error": str(exc)},
                    )
                    attempt += 1

            if accepted is None:
                # Truthfulness > variation — ship original atom text.
                logger.warning(
                    "achievement_rewriter_falling_back_to_source",
                    extra={"source_ref": source_ref},
                )
                accepted = [a.experience.outcome for a in atoms][: self._max_bullets_per_entry]
                ctx.errors[f"{self.name}.{source_ref}"] = "grounding_failed_falling_back"

            rewritten[source_ref] = accepted

        return rewritten


__all__ = ["AchievementRewriter"]
