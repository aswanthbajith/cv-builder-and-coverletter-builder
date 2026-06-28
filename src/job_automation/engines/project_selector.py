"""ProjectSelector — choose which projects to surface.

Same scoring as :class:`ExperienceSelector` but only considers
``source == "project"`` atoms. Targets 3 project entries; takes the top
4 atoms per source_ref to give the rewriter enough material.

Inputs:
    ctx.graph, ctx.job
Outputs:
    ctx.selected_projects
"""

from __future__ import annotations

from collections import defaultdict

from job_automation.engines.base import PipelineContext
from job_automation.knowledge import find_relevant_experiences
from job_automation.logging import get_logger

logger = get_logger(__name__)


class ProjectSelector:
    """Deterministic project selector."""

    name = "project_selector"
    timeout_s = 1.0
    requires = frozenset({"graph", "job"})
    produces = frozenset({"selected_projects"})

    def __init__(self, top_k: int = 24, max_source_refs: int = 3, max_atoms_per_ref: int = 4) -> None:
        self._top_k = top_k
        self._max_source_refs = max_source_refs
        self._max_atoms_per_ref = max_atoms_per_ref

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        scored = find_relevant_experiences(ctx.job, ctx.graph, top_k=self._top_k)
        project_scored = [s for s in scored if s.experience.source == "project"]

        grouped: dict[str, list] = defaultdict(list)
        for s in project_scored:
            grouped[s.experience.source_ref].append(s)

        selected: list = []
        seen: set[str] = set()
        # First, take the top atoms from each bucket sorted by best-atom score.
        bucket_best = sorted(grouped.items(), key=lambda kv: kv[1][0].score, reverse=True)
        for ref, items in bucket_best:
            if len(seen) >= self._max_source_refs:
                break
            items.sort(key=lambda s: s.score, reverse=True)
            selected.extend(items[: self._max_atoms_per_ref])
            seen.add(ref)

        ctx.selected_projects = selected
        logger.info(
            "project_selector_done",
            extra={"selected": len(selected), "source_refs": len(seen)},
        )
        return ctx


__all__ = ["ProjectSelector"]
