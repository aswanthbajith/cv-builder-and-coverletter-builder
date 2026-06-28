"""ExperienceSelector — choose which work experiences to surface.

Wraps :func:`find_relevant_experiences` and groups the top atoms by their
``source_ref`` so the rewriter sees a coherent work-entry shape.

For the resume, the selector targets 3 work-entries (i.e. ``source_ref``
buckets with ``source == "work"``) since the candidate has only one
work history entry today — this cap lets the resume grow gracefully as
more roles are added.

Inputs:
    ctx.graph, ctx.job
Outputs:
    ctx.selected_experiences — top-scored :class:`ScoredExperience` atoms
"""

from __future__ import annotations

from collections import defaultdict

from job_automation.engines.base import PipelineContext
from job_automation.knowledge import find_relevant_experiences
from job_automation.logging import get_logger

logger = get_logger(__name__)


class ExperienceSelector:
    """Deterministic selector — picks the highest-scoring work atoms."""

    name = "experience_selector"
    timeout_s = 1.0
    requires = frozenset({"graph", "job"})
    produces = frozenset({"selected_experiences"})

    def __init__(self, top_k: int = 12, max_source_refs: int = 3) -> None:
        self._top_k = top_k
        self._max_source_refs = max_source_refs

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        scored = find_relevant_experiences(ctx.job, ctx.graph, top_k=self._top_k)
        # Keep only work atoms.
        work_scored = [s for s in scored if s.experience.source == "work"]

        # Group by source_ref and keep top 4 per source.
        grouped: dict[str, list] = defaultdict(list)
        for s in work_scored:
            grouped[s.experience.source_ref].append(s)
        selected: list = []
        for ref, items in grouped.items():
            items.sort(key=lambda s: s.score, reverse=True)
            selected.extend(items[:4])

        # Truncate to max_source_refs buckets (with all top-4 atoms each).
        seen: set[str] = set()
        capped: list = []
        for s in sorted(selected, key=lambda s: s.score, reverse=True):
            if s.experience.source_ref in seen:
                if sum(1 for x in capped if x.experience.source_ref == s.experience.source_ref) >= 4:
                    continue
                capped.append(s)
                continue
            if len(seen) >= self._max_source_refs:
                continue
            seen.add(s.experience.source_ref)
            capped.append(s)

        ctx.selected_experiences = capped
        logger.info(
            "experience_selector_done",
            extra={"selected": len(capped), "source_refs": len(seen)},
        )
        return ctx


__all__ = ["ExperienceSelector"]
