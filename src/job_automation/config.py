"""Typed configuration for the job-automation pipeline.

Replaces the singleton ``Config`` class with a Pydantic-settings model that
reads ``config.yaml`` and allows ``JOB_AUTO_*`` environment variables to
override any field. Settings are loaded lazily via :func:`load_config`, which
caches the instance per process — safe for the CLI path but trivially
overridable in tests by passing a hand-built ``AppConfig``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class PathsConfig(BaseModel):
    """Filesystem paths used by the pipeline."""

    model_config = ConfigDict(extra="ignore")

    input_excel: Path = Path("input/jobs.xlsx")
    output_excel: Path = Path("output/Job_Matching_Updated.xlsx")
    profile_dir: Path = Path("profile")
    templates_dir: Path = Path("templates")
    generated_dir: Path = Path("generated")
    log_file: Path = Path("generated/Logs/generation.log")


class MatchingConfig(BaseModel):
    """Thresholds used by :class:`job_automation.engines.matcher.JobMatcher`."""

    model_config = ConfigDict(extra="ignore")

    minimum_match_score: float = Field(default=60.0, ge=0.0, le=100.0)
    duplicate_similarity_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    review_band: float = Field(
        default=10.0,
        ge=0.0,
        le=100.0,
        description="Width of the 'review' band below minimum_match_score",
    )


class GenerationConfig(BaseModel):
    """Document generation knobs."""

    model_config = ConfigDict(extra="ignore")

    generate_pdf: bool = True
    generate_docx: bool = True
    compile_latex: bool = True
    max_workers: int = Field(default=4, ge=1, le=64)


class AtsConfig(BaseModel):
    """ATS optimization targets — advisory, used by generators in M2+."""

    model_config = ConfigDict(extra="ignore")

    target_score: int = Field(default=90, ge=0, le=100)
    keyword_density_max: float = Field(default=0.08, gt=0.0, le=1.0)
    max_resume_pages: int = Field(default=1, ge=1, le=4)


class CriticConfig(BaseModel):
    """Critic loop tuning for the M2 pipeline."""

    model_config = ConfigDict(extra="ignore")

    max_iterations: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum rewrite→critic iterations. Higher = more polish, more cost.",
    )


class WebConfig(BaseModel):
    """Web research knobs used by ``CompanyResearcher``."""

    model_config = ConfigDict(extra="ignore")

    research_timeout_s: float = Field(default=10.0, gt=0.0, le=300.0)
    cache_max_age_days: int = Field(default=30, ge=1, le=365)


class LoggingConfig(BaseModel):
    """Logging configuration consumed by ``job_automation.logging``."""

    model_config = ConfigDict(extra="ignore")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["json", "console"] = "console"
    file_enabled: bool = True
    colored: bool = True  # only meaningful when format="console"


class AppConfig(BaseSettings):
    """Root configuration. Compose from YAML + env vars.

    Env var override uses the ``JOB_AUTO_`` prefix with double-underscore
    nesting. Example: ``JOB_AUTO_GENERATION__MAX_WORKERS=8`` overrides
    ``generation.max_workers``.
    """

    model_config = SettingsConfigDict(
        env_prefix="JOB_AUTO_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    paths: PathsConfig = Field(default_factory=PathsConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    ats: AtsConfig = Field(default_factory=AtsConfig)
    critic: CriticConfig = Field(default_factory=CriticConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add YAML source. Env vars take precedence over YAML."""
        yaml_path = Path("config.yaml")
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ]
        if yaml_path.exists():
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path)
            )
        return tuple(sources)


@lru_cache(maxsize=1)
def load_config(yaml_path: str | Path | None = None) -> AppConfig:
    """Return the process-wide :class:`AppConfig` instance.

    Pass ``yaml_path`` only from tests; production code lets pydantic-settings
    find ``config.yaml`` relative to CWD via the YAML source wired in
    :meth:`AppConfig.settings_customise_sources`.
    """
    if yaml_path is None:
        return AppConfig()

    # When an explicit path is supplied, override the YAML location for this
    # single call by reading the file ourselves and handing pydantic the dict.
    import yaml  # local import — only needed in test path

    with Path(yaml_path).open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return AppConfig(**data)


def reset_config_cache() -> None:
    """Clear the ``load_config`` cache. Test-only helper."""
    load_config.cache_clear()
