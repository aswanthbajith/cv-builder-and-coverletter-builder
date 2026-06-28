"""job_automation — typed pipeline for resume + cover-letter generation.

Public surface for M1:

- :class:`Job`, :class:`Profile`, :class:`MatchResult`, :class:`GenerationResult`
  — the Pydantic contracts every engine honors.
- :func:`load_config` — pydantic-settings backed configuration.
- :func:`get_logger`, :func:`configure_logging`, :func:`log_context` —
  correlation-ID aware logging.
- :func:`read_jobs_excel`, :func:`load_profile` — IO entry points.

M2 adds: 12-engine pipeline (:class:`Pipeline`), knowledge graph
(``job_automation.knowledge``), LLM client protocol with Gemini + fake.
M3 will add: Celery tasks.
"""

from __future__ import annotations

from job_automation.config import (
    AppConfig,
    AtsConfig,
    CriticConfig,
    GenerationConfig,
    LoggingConfig,
    MatchingConfig,
    PathsConfig,
    WebConfig,
    load_config,
    reset_config_cache,
)
from job_automation.engines import Pipeline
from job_automation.io import load_profile, read_jobs_excel
from job_automation.knowledge import load_knowledge_graph
from job_automation.logging import (
    configure_logging,
    get_logger,
    log_context,
)
from job_automation.models import (
    EducationEntry,
    ExperienceEntry,
    GenerationResult,
    Job,
    JobType,
    LanguageEntry,
    MatchResult,
    Profile,
    ProjectEntry,
    ResumeContent,
    Status,
)

__version__ = "0.3.0"

__all__ = [
    "AppConfig",
    "AtsConfig",
    "CriticConfig",
    "EducationEntry",
    "ExperienceEntry",
    "GenerationConfig",
    "GenerationResult",
    "Job",
    "JobType",
    "LanguageEntry",
    "LoggingConfig",
    "MatchResult",
    "MatchingConfig",
    "PathsConfig",
    "Pipeline",
    "Profile",
    "ProjectEntry",
    "ResumeContent",
    "Status",
    "WebConfig",
    "__version__",
    "configure_logging",
    "get_logger",
    "load_config",
    "load_knowledge_graph",
    "load_profile",
    "log_context",
    "read_jobs_excel",
    "reset_config_cache",
]
