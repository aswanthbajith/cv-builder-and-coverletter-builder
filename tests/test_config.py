"""Configuration tests — round-trip the project's config.yaml, env override,
cache, and extra-field tolerance.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from job_automation.config import (
    AppConfig,
    AtsConfig,
    GenerationConfig,
    MatchingConfig,
    PathsConfig,
    load_config,
    reset_config_cache,
)


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.matching.minimum_match_score == 60.0
        assert cfg.matching.duplicate_similarity_threshold == 0.95
        assert cfg.generation.max_workers == 4
        assert cfg.generation.compile_latex is True

    def test_yaml_round_trip(self, config_yaml) -> None:
        cfg = load_config(yaml_path=config_yaml)
        assert cfg.matching.minimum_match_score == 60.0
        assert cfg.paths.profile_dir == __import__("pathlib").Path("profile")

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reset_config_cache()
        monkeypatch.setenv("JOB_AUTO_GENERATION__MAX_WORKERS", "12")
        cfg = AppConfig()
        assert cfg.generation.max_workers == 12

    def test_extra_yaml_keys_ignored(self, tmp_path) -> None:
        yaml = tmp_path / "config.yaml"
        yaml.write_text(
            """
            matching:
              minimum_match_score: 75
            unknown_future_key: 42
            paths:
              made_up_path: nope
            """,
            encoding="utf-8",
        )
        reset_config_cache()
        cfg = load_config(yaml_path=yaml)
        assert cfg.matching.minimum_match_score == 75.0

    def test_cache_returns_same_instance(self, config_yaml) -> None:
        reset_config_cache()
        a = load_config(yaml_path=config_yaml)
        b = load_config(yaml_path=config_yaml)
        assert a is b

    def test_cache_clear(self, config_yaml) -> None:
        reset_config_cache()
        a = load_config(yaml_path=config_yaml)
        reset_config_cache()
        b = load_config(yaml_path=config_yaml)
        assert a is not b

    def test_bounds_enforced(self) -> None:
        with pytest.raises(ValidationError):
            MatchingConfig(minimum_match_score=200.0)
        with pytest.raises(ValidationError):
            GenerationConfig(max_workers=0)
        with pytest.raises(ValidationError):
            AtsConfig(target_score=-1)

    def test_nested_construction(self) -> None:
        cfg = AppConfig(
            paths=PathsConfig(
                input_excel=Path("custom/in.xlsx"),
            ),
        )
        assert cfg.paths.input_excel.name == "in.xlsx"
        assert "custom" in str(cfg.paths.input_excel)
