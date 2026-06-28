"""SkillGapAnalyzer — bucket the candidate's skills vs the job's keywords.

Deterministic. Iterates over the knowledge graph's reverse indexes and
classifies each required keyword as matched / partial / missing /
transferable. No LLM call.

Inputs:
    ctx.graph, ctx.ats_keywords
Outputs:
    ctx.skill_gaps
"""

from __future__ import annotations

from job_automation.engines.base import PipelineContext
from job_automation.logging import get_logger
from job_automation.models.analysis import SkillGapReport

logger = get_logger(__name__)


class SkillGapAnalyzer:
    """Deterministic gap analysis over the knowledge graph."""

    name = "skill_gap"
    timeout_s = 1.0
    requires = frozenset({"graph", "ats_keywords"})
    produces = frozenset({"skill_gaps"})

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        graph = ctx.graph
        matched: list[str] = []
        partial: list[str] = []
        missing: list[str] = []

        for kw in ctx.ats_keywords:
            term = kw.term.lower()
            direct = graph.by_skill(term) or graph.by_technology(term)
            if direct:
                matched.append(kw.term)
                continue

            partial_match = _partial_tech_match(term, graph)
            if partial_match:
                partial.append(kw.term)
            else:
                missing.append(kw.term)

        transferable = _transferable_skills(graph, {kw.term.lower() for kw in ctx.ats_keywords})

        ctx.skill_gaps = SkillGapReport(
            matched=matched,
            partial=partial,
            missing=missing,
            transferable=transferable,
        )
        logger.info(
            "skill_gap_done",
            extra={
                "matched": len(matched),
                "partial": len(partial),
                "missing": len(missing),
                "transferable": len(transferable),
            },
        )
        return ctx


def _partial_tech_match(term: str, graph: object) -> bool:
    """Return True if any candidate technology key is a substring of ``term`` or vice versa."""
    by_tech = getattr(graph, "_by_technology", {})
    if not by_tech:
        return False
    for tech in by_tech:
        if len(tech) < 3:
            continue
        if term in tech or tech in term:
            return True
    return False


def _transferable_skills(graph: object, job_terms: set[str]) -> list[str]:
    """Skills the candidate has that the job didn't explicitly ask for."""
    candidate_skill_set: set[str] = set()
    for atom in graph.experiences:  # type: ignore[attr-defined]
        for s in atom.skills:
            candidate_skill_set.add(s.lower())
        for t in atom.technologies:
            candidate_skill_set.add(t.lower())
    return sorted(s for s in candidate_skill_set if s not in job_terms and len(s) > 2)


__all__ = ["SkillGapAnalyzer"]
