"""IO loader tests — profile_loader and excel_reader."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from job_automation.config import PathsConfig
from job_automation.io import load_profile, read_jobs_excel
from job_automation.models import Job, Profile


class TestLoadProfile:
    def test_loads_from_directory(self, profile_dir: Path) -> None:
        paths = PathsConfig(profile_dir=profile_dir, generated_dir=profile_dir.parent)
        profile = load_profile(paths=paths)
        assert isinstance(profile, Profile)
        assert profile.name == "Test Candidate"
        assert "Python" in profile.technical_skills["programming_languages"]

    def test_missing_directory_logs_and_raises(self, tmp_path: Path) -> None:
        paths = PathsConfig(profile_dir=tmp_path / "does_not_exist")
        # Profile model requires ``name`` — without a master_resume.json the
        # empty merged dict should fail validation.
        with pytest.raises(Exception):
            load_profile(paths=paths)


class TestReadJobsExcel:
    def test_round_trip_real_input(self, project_root: Path) -> None:
        """Smoke test against the project's real ``input/jobs.xlsx`` if present."""
        excel = project_root / "input" / "jobs.xlsx"
        if not excel.exists():
            pytest.skip("input/jobs.xlsx not present")
        paths = PathsConfig(input_excel=excel, output_excel=excel)
        jobs = read_jobs_excel(paths=paths, excel_path=excel)
        assert isinstance(jobs, list)
        assert all(isinstance(j, Job) for j in jobs)
        assert len(jobs) > 0

    def test_missing_file(self, tmp_path: Path) -> None:
        from job_automation.io.excel_reader import _resolve_input

        with pytest.raises(FileNotFoundError):
            _resolve_input(tmp_path / "absent.xlsx")

    def test_validates_rows(self, tmp_path: Path) -> None:
        """Rows missing required fields are skipped, not crash-the-pipeline."""
        from job_automation.io.excel_reader import _row_to_job

        # Missing company should fail validation.
        with pytest.raises(Exception):
            _row_to_job({"job_title": "x", "location": "y", "job_description": "z"})

        # Valid row succeeds.
        job = _row_to_job(
            {
                "company": "Acme",
                "job_title": "Dev",
                "location": "Berlin",
                "job_description": "Build things",
            }
        )
        assert job.company == "Acme"