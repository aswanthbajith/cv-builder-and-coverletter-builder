"""Pipeline orchestrator — chains the 12 engines per job.

The orchestrator owns:
- :class:`PipelineContext` construction for each job.
- Sequential + critic-loop engine execution with per-engine timeouts.
- Critic loop with bounded iterations (default 2) on top of
  :class:`ResumeCritic` and :class:`AchievementRewriter`.
- Best-effort ship on partial failure: every engine is run, errors are
  accumulated in ``ctx.errors``, and a usable artifact is produced when
  at minimum the LaTeX generator ran.

The orchestrator is engine-agnostic. It accepts any list of objects that
conform to :class:`BaseEngine`, so the test suite can swap in stub
engines or the legacy dataclass-driven code.

Async path (``process_async``) runs the deterministic engines in parallel
via :func:`asyncio.gather(return_exceptions=True)` where dependencies
permit. The LLM engines run sequentially after their deterministic
predecessors finish.

Sync path (``process_sync``) is a thin wrapper for the CLI and unit tests.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from job_automation.config import load_config
from job_automation.engines.base import BaseEngine, EngineResult, PipelineContext
from job_automation.engines.latex_generator import build_draft_resume
from job_automation.knowledge.graph import KnowledgeGraph
from job_automation.logging import get_logger
from job_automation.models.job import Job
from job_automation.models.profile import Profile
from job_automation.models.results import GenerationResult, MatchResult

logger = get_logger(__name__)


class Pipeline:
    """Run the M2 engine chain for one or more jobs.

    Construct once per batch (the engines are stateless and can be reused),
    then call :meth:`process_sync` or :meth:`process_async` for each job.

    The 12 stages are wired in the canonical order from the M2 plan:

        JobAnalyzer → CompanyResearcher → ATSKeywordExtractor
        → SkillGapAnalyzer → ExperienceSelector → AchievementRewriter
        → ProjectSelector → SummaryGenerator → ResumeCritic (loop)
        → ATSValidator → RecruiterReviewer → LaTeXGenerator → PDF

    Deterministic engines (KeywordExtractor, SkillGapAnalyzer,
    ExperienceSelector, ProjectSelector, ATSValidator) are independent
    of each other once their inputs are available, so the async path
    groups them into a :func:`asyncio.gather` barrier.
    """

    def __init__(
        self,
        *,
        job_analyzer: BaseEngine,
        company_researcher: BaseEngine,
        keyword_extractor: BaseEngine,
        skill_gap: BaseEngine,
        experience_selector: BaseEngine,
        achievement_rewriter: BaseEngine,
        project_selector: BaseEngine,
        summary_generator: BaseEngine,
        resume_critic: BaseEngine,
        ats_validator: BaseEngine,
        recruiter_reviewer: BaseEngine,
        latex_generator: BaseEngine,
        max_critic_iterations: int = 2,
    ) -> None:
        self._job_analyzer = job_analyzer
        self._company_researcher = company_researcher
        self._keyword_extractor = keyword_extractor
        self._skill_gap = skill_gap
        self._experience_selector = experience_selector
        self._achievement_rewriter = achievement_rewriter
        self._project_selector = project_selector
        self._summary_generator = summary_generator
        self._resume_critic = resume_critic
        self._ats_validator = ats_validator
        self._recruiter_reviewer = recruiter_reviewer
        self._latex_generator = latex_generator
        self._max_critic_iterations = max(1, max_critic_iterations)

    # ------------------------------------------------------------------ public

    def process_sync(self, job: Job, graph: KnowledgeGraph, profile: Profile) -> GenerationResult:
        """Run the full pipeline synchronously for one job."""
        return asyncio.run(self.process_async(job, graph, profile))

    async def process_async(
        self, job: Job, graph: KnowledgeGraph, profile: Profile
    ) -> GenerationResult:
        """Run the full pipeline asynchronously for one job."""
        run_id = uuid.uuid4().hex[:12]
        ctx = PipelineContext(run_id=run_id, job=job, graph=graph, profile=profile)

        try:
            await self._run_pre_rewrite(ctx)
            await self._run_rewrite_phase(ctx)
            await self._run_summary_and_critic_loop(ctx)
            await self._run_post_critic(ctx)
        except Exception as exc:  # noqa: BLE001 — ship best-effort
            logger.exception("pipeline_aborted", extra={"run_id": run_id, "error": str(exc)})
            ctx.errors["pipeline"] = str(exc)

        return self._finalize(ctx)

    # ------------------------------------------------------------------ phases

    async def _run_pre_rewrite(self, ctx: PipelineContext) -> None:
        """JobAnalyzer → CompanyResearcher → ATSKeywordExtractor / SkillGap / Selectors.

        The deterministic engines (keyword extractor, skill gap, both
        selectors) run concurrently after JobAnalyzer + CompanyResearcher
        finish, since they only depend on the resulting ctx fields.
        """
        await self._run_engine(ctx, self._job_analyzer)
        await self._run_engine(ctx, self._company_researcher)

        # Concurrently run deterministic engines that share the same
        # dependencies (job_analysis + company_profile).
        await asyncio.gather(
            self._run_engine(ctx, self._keyword_extractor),
            self._run_engine(ctx, self._skill_gap),
            self._run_engine(ctx, self._experience_selector),
            self._run_engine(ctx, self._project_selector),
            return_exceptions=True,
        )

    async def _run_rewrite_phase(self, ctx: PipelineContext) -> None:
        """AchievementRewriter — bullets for selected experiences and projects."""
        await self._run_engine(ctx, self._achievement_rewriter)

    async def _run_summary_and_critic_loop(self, ctx: PipelineContext) -> None:
        """SummaryGenerator → ResumeCritic → (rewrite → critic)*N."""
        await self._run_engine(ctx, self._summary_generator)

        # Build the first draft before the first critic pass.
        if ctx.summary is not None or ctx.rewritten_bullets or ctx.rewritten_project_bullets:
            ctx.draft_resume = build_draft_resume(ctx)

        for iteration in range(self._max_critic_iterations):
            await self._run_engine(ctx, self._resume_critic)
            review = ctx.critic_iterations[-1] if ctx.critic_iterations else None
            if review is None or review.verdict == "pass":
                return
            if review.verdict == "reject":
                logger.warning(
                    "critic_rejected",
                    extra={"iteration": iteration, "score": review.score},
                )
                # Loop once more on reject — fixes might rescue it.
                if iteration + 1 < self._max_critic_iterations:
                    await self._run_engine(ctx, self._achievement_rewriter)
                    ctx.draft_resume = build_draft_resume(ctx)
                    continue
                ctx.errors["critic"] = "max_iterations_exceeded"
                return
            # verdict == "revise" → re-run the rewriter with feedback.
            if iteration + 1 < self._max_critic_iterations:
                await self._run_engine(ctx, self._achievement_rewriter)
                ctx.draft_resume = build_draft_resume(ctx)
            else:
                ctx.errors["critic"] = "max_iterations_exceeded"

    async def _run_post_critic(self, ctx: PipelineContext) -> None:
        """ATSValidator + RecruiterReviewer + LaTeXGenerator (concurrent where safe)."""
        # ATSValidator + RecruiterReviewer share the draft resume; they can run
        # in parallel. LaTeXGenerator runs after to write the final artifact.
        await asyncio.gather(
            self._run_engine(ctx, self._ats_validator),
            self._run_engine(ctx, self._recruiter_reviewer),
            return_exceptions=True,
        )
        await self._run_engine(ctx, self._latex_generator)

    # ------------------------------------------------------------------ helpers

    async def _run_engine(self, ctx: PipelineContext, engine: BaseEngine) -> None:
        """Run one engine, time it, and absorb exceptions into ctx."""
        start = time.perf_counter()
        try:
            await asyncio.wait_for(engine.run(ctx), timeout=engine.timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                "engine_timeout",
                extra={"engine": engine.name, "timeout_s": engine.timeout_s},
            )
            ctx.errors[engine.name] = f"timeout_after_{engine.timeout_s}s"
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "engine_failed",
                extra={"engine": engine.name, "error": str(exc)},
            )
            ctx.errors[engine.name] = str(exc)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            ctx.timings_ms[engine.name] = round(duration_ms, 2)
            _ = EngineResult(name=engine.name, duration_ms=duration_ms)

    def _finalize(self, ctx: PipelineContext) -> GenerationResult:
        """Build the public :class:`GenerationResult` from the final context."""
        match = self._derive_match_result(ctx)
        # C3 wiring: elevate a RecruiterReviewer "reject" verdict into
        # ctx.errors so it surfaces in GenerationResult.error (and downstream
        # in the Excel output). Other verdicts (review / interview) are
        # intentionally NOT added — they are informational.
        if ctx.recruiter_review is not None and ctx.recruiter_review.verdict == "reject":
            rationale = (ctx.recruiter_review.rationale or "").strip()[:200]
            ctx.errors["recruiter_rejected"] = rationale or "no_rationale"
        # Pick the most informative error message (shortest non-empty wins).
        error = self._summarize_errors(ctx)
        return GenerationResult(
            job=ctx.job,
            match=match,
            resume_tex_path=ctx.resume_tex_path,
            resume_pdf_path=ctx.resume_pdf_path,
            generated_at=datetime.now(tz=timezone.utc),
            error=error,
        )

    @staticmethod
    def _derive_match_result(ctx: PipelineContext) -> MatchResult:
        """Synthesize a :class:`MatchResult` from gap analysis + critic scores.

        Real A/B comparison will replace this with a true match score; for
        now we expose the deterministic signals so the downstream UI works.
        """
        gaps = ctx.skill_gaps
        matched_n = len(gaps.matched) if gaps else 0
        partial_n = len(gaps.partial) if gaps else 0
        missing_n = len(gaps.missing) if gaps else 0
        total = max(1, matched_n + partial_n + missing_n)
        skills_score = round(100.0 * (matched_n + 0.5 * partial_n) / total, 1)
        critic_score = ctx.critic_iterations[-1].score * 10 if ctx.critic_iterations else 50.0
        ats_score = ctx.ats_score.overall if ctx.ats_score else 0.0
        overall = round(0.5 * skills_score + 0.3 * critic_score + 0.2 * ats_score, 1)
        status: Any
        if overall >= 80:
            status = "proceed"
        elif overall >= 60:
            status = "review"
        else:
            status = "skip"
        return MatchResult(
            overall_score=overall,
            education_score=50.0,
            skills_score=skills_score,
            programming_score=skills_score,
            research_score=50.0,
            experience_score=critic_score,
            reasoning=(
                f"matched={matched_n}, partial={partial_n}, missing={missing_n}; "
                f"critic_score={critic_score}, ats_score={ats_score}"
            ),
            missing_skills=gaps.missing if gaps else [],
            strengths=gaps.matched if gaps else [],
            status=status,
        )

    @staticmethod
    def _summarize_errors(ctx: PipelineContext) -> str | None:
        """Concatenate unique error messages — None when the pipeline was clean."""
        if not ctx.errors:
            return None
        # Prefer pipeline-level error if present.
        if "pipeline" in ctx.errors:
            return f"pipeline: {ctx.errors['pipeline']}"
        # Otherwise join up to 3 short messages.
        msgs = [f"{k}: {v}" for k, v in ctx.errors.items()]
        return "; ".join(msgs[:3])


# ----------------------------------------------------------------------- builder


def build_default_pipeline(llm: Any) -> Pipeline:
    """Construct a production-ready :class:`Pipeline` with all 12 engines.

    Pass the ``GeminiClient`` (or a ``FakeLLMClient`` in tests) — engines that
    don't need an LLM ignore it. The deterministic engines are wired with
    their default hyperparameters (top_k, max_source_refs, etc.).
    """
    from job_automation.engines.achievement_rewriter import AchievementRewriter
    from job_automation.engines.ats_validator import ATSValidator
    from job_automation.engines.company_researcher import CompanyResearcher
    from job_automation.engines.experience_selector import ExperienceSelector
    from job_automation.engines.job_analyzer import JobAnalyzer
    from job_automation.engines.keyword_extractor import ATSKeywordExtractor
    from job_automation.engines.latex_generator import LaTeXGenerator
    from job_automation.engines.project_selector import ProjectSelector
    from job_automation.engines.recruiter_reviewer import RecruiterReviewer
    from job_automation.engines.resume_critic import ResumeCritic
    from job_automation.engines.skill_gap import SkillGapAnalyzer
    from job_automation.engines.summary_generator import SummaryGenerator

    cfg = load_config()
    return Pipeline(
        job_analyzer=JobAnalyzer(llm),
        company_researcher=CompanyResearcher(paths=cfg.paths),
        keyword_extractor=ATSKeywordExtractor(),
        skill_gap=SkillGapAnalyzer(),
        experience_selector=ExperienceSelector(),
        achievement_rewriter=AchievementRewriter(llm),
        project_selector=ProjectSelector(),
        summary_generator=SummaryGenerator(llm),
        resume_critic=ResumeCritic(llm),
        ats_validator=ATSValidator(),
        recruiter_reviewer=RecruiterReviewer(llm),
        latex_generator=LaTeXGenerator(),
        max_critic_iterations=getattr(cfg, "critic", None)
        and getattr(cfg.critic, "max_iterations", 2)
        or 2,
    )


__all__ = ["Pipeline", "build_default_pipeline"]