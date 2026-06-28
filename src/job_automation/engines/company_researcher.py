"""CompanyResearcher — produces :class:`CompanyProfile`.

Two operating modes:

1. **Offline (default in M2 runtime)**: Reads from the on-disk cache at
   ``profile/company_cache/{slug}.json``. If a fresh entry exists (≤ 30
   days), returns it. Otherwise returns :class:`CompanyProfile.empty`
   and logs a warning.

2. **Research hook (test + dev)**: An injected ``research_fn(company,
   job_title) -> dict`` is called when the cache is missing. Production
   can wire this to a Celery task that calls Google CSE; tests inject a
   canned response. Per the M2 plan, the actual web-search happens in
   Claude Code's ``WebSearch`` tool — Python only consumes the result.

Inputs:
    ctx.job
Outputs:
    ctx.company_profile
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from job_automation.config import PathsConfig
from job_automation.engines.base import PipelineContext
from job_automation.logging import get_logger
from job_automation.models.company import CompanyProfile

logger = get_logger(__name__)

ResearchFn = Callable[[str, str], dict]


def _slug(text: str) -> str:
    """Filesystem-safe slug for a company name."""
    slug = re.sub(r"[^\w\s-]", "", str(text or "")).strip().lower()
    slug = re.sub(r"[-\s]+", "_", slug)
    return slug[:60] or "unknown"


class CompanyResearcher:
    """Cache-first company profiler.

    ``research_fn`` is the injection seam for live research. Defaults to
    returning an empty profile (i.e. cache miss → empty result).
    """

    name = "company_researcher"
    timeout_s = 30.0
    requires = frozenset({"job"})
    produces = frozenset({"company_profile"})

    def __init__(
        self,
        paths: PathsConfig | None = None,
        *,
        research_fn: ResearchFn | None = None,
        cache_max_age_days: int = 30,
    ) -> None:
        self._paths = paths
        self._research_fn = research_fn
        self._cache_max_age_days = cache_max_age_days
        self._cache_dir: Path | None = None

    def _cache_dir_path(self) -> Path:
        if self._cache_dir is None:
            if self._paths is None:
                from job_automation.config import load_config

                self._paths = load_config().paths
            self._cache_dir = self._paths.profile_dir / "company_cache"
        return self._cache_dir

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        company = ctx.job.company
        cache_dir = self._cache_dir_path()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{_slug(company)}.json"

        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                cached_at = datetime.fromisoformat(raw["cached_at"]).date()
                age = (date.today() - cached_at).days
                if age <= self._cache_max_age_days:
                    raw.pop("cached_at", None)
                    ctx.company_profile = CompanyProfile.model_validate(raw)
                    logger.info(
                        "company_research_cache_hit",
                        extra={"company": company, "age_days": age},
                    )
                    return ctx
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "company_research_cache_invalid",
                    extra={"path": str(cache_path), "error": str(exc)},
                )

        # Cache miss — call the research hook (if injected) or return empty.
        if self._research_fn is None:
            logger.warning(
                "company_research_no_fn",
                extra={"company": company},
            )
            ctx.company_profile = CompanyProfile.empty(company)
            ctx.errors[self.name] = "no_research_fn_available"
            return ctx

        try:
            raw = self._research_fn(company, ctx.job.job_title)
            raw["cached_at"] = datetime.now(tz=timezone.utc).date().isoformat()
            cache_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
            raw.pop("cached_at", None)
            ctx.company_profile = CompanyProfile.model_validate(raw)
            logger.info("company_research_done", extra={"company": company})
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "company_research_failed",
                extra={"company": company, "error": str(exc)},
            )
            ctx.company_profile = CompanyProfile.empty(company)
            ctx.errors[self.name] = str(exc)
        return ctx


__all__ = ["CompanyResearcher", "ResearchFn"]


# Exposed for tests + dev — bound default cache_max_age to 30 days.
_DEFAULT_MAX_AGE = timedelta(days=30).days
