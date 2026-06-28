"""Pydantic model contract tests.

Verifies that strict mode rejects coercion, that frozen models are
immutable, that required fields are enforced, and that the model surface
matches what M2's engines will consume.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
)

# ─── Job ──────────────────────────────────────────────────────────────────


class TestJob:
    def test_minimal_valid(self, sample_job: Job) -> None:
        assert sample_job.company == "Acme HPC"
        assert sample_job.job_type == "internship"

    def test_strict_rejects_int_for_string(self) -> None:
        with pytest.raises(ValidationError):
            Job(  # type: ignore[arg-type]
                company=123,  # type: ignore[arg-type]
                job_title="X",
                location="Y",
                job_description="Z",
            )

    def test_extra_columns_ignored(self) -> None:
        job = Job.model_validate(
            {
                "company": "A",
                "job_title": "B",
                "location": "C",
                "job_description": "D",
                "unexpected_column": "ignored",
            }
        )
        assert not hasattr(job, "unexpected_column")

    def test_immutable(self, sample_job: Job) -> None:
        with pytest.raises(ValidationError):
            sample_job.company = "Other"  # type: ignore[misc]

    def test_job_type_literal_valid(self) -> None:
        job = Job.model_validate(
            {
                "company": "A",
                "job_title": "B",
                "location": "C",
                "job_description": "D",
                "job_type": "internship",
            }
        )
        assert job.job_type == "internship"

    def test_job_type_literal_invalid(self) -> None:
        # Strict literal validation rejects unknown values.
        with pytest.raises(ValidationError):
            Job.model_validate(
                {
                    "company": "A",
                    "job_title": "B",
                    "location": "C",
                    "job_description": "D",
                    "job_type": "made-up",
                }
            )

    def test_match_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Job(
                company="A",
                job_title="B",
                location="C",
                job_description="D",
                match_score=150.0,
            )


# ─── Profile ──────────────────────────────────────────────────────────────


class TestProfile:
    def test_round_trip(self, sample_profile: Profile) -> None:
        dumped = sample_profile.model_dump()
        restored = Profile.model_validate(dumped)
        assert restored == sample_profile

    def test_required_name(self) -> None:
        with pytest.raises(ValidationError):
            Profile()  # type: ignore[call-arg]

    def test_experience_entry_strict(self) -> None:
        with pytest.raises(ValidationError):
            ExperienceEntry(title=1, company="x")  # type: ignore[arg-type]

    def test_project_entry_default_factories(self) -> None:
        p = ProjectEntry(name="X")
        assert p.description == []
        assert p.metrics == []

    def test_immutable(self, sample_profile: Profile) -> None:
        with pytest.raises(ValidationError):
            sample_profile.name = "Other"  # type: ignore[misc]


# ─── MatchResult ──────────────────────────────────────────────────────────


class TestMatchResult:
    def test_status_literal(self) -> None:
        # Valid status
        MatchResult(
            overall_score=80.0,
            education_score=70.0,
            skills_score=90.0,
            programming_score=80.0,
            research_score=60.0,
            experience_score=50.0,
            reasoning="ok",
            missing_skills=[],
            strengths=["Python"],
            status="proceed",
        )
        # Invalid status
        with pytest.raises(ValidationError):
            MatchResult(
                overall_score=80.0,
                education_score=70.0,
                skills_score=90.0,
                programming_score=80.0,
                research_score=60.0,
                experience_score=50.0,
                reasoning="ok",
                missing_skills=[],
                strengths=[],
                status="maybe",  # type: ignore[arg-type]
            )


# ─── GenerationResult ────────────────────────────────────────────────────


class TestGenerationResult:
    def test_optional_paths(self, sample_job: Job) -> None:
        from datetime import datetime, timezone

        match = MatchResult(
            overall_score=80.0,
            education_score=70.0,
            skills_score=90.0,
            programming_score=80.0,
            research_score=60.0,
            experience_score=50.0,
            reasoning="ok",
            missing_skills=[],
            strengths=[],
            status="proceed",
        )
        result = GenerationResult(
            job=sample_job,
            match=match,
            generated_at=datetime.now(tz=timezone.utc),
        )
        assert result.resume_pdf_path is None
        assert result.error is None

    def test_immutable(self, sample_job: Job) -> None:
        from datetime import datetime, timezone

        match = MatchResult(
            overall_score=80.0,
            education_score=70.0,
            skills_score=90.0,
            programming_score=80.0,
            research_score=60.0,
            experience_score=50.0,
            reasoning="ok",
            missing_skills=[],
            strengths=[],
            status="proceed",
        )
        result = GenerationResult(
            job=sample_job, match=match, generated_at=datetime.now(tz=timezone.utc)
        )
        with pytest.raises(ValidationError):
            result.error = "boom"  # type: ignore[misc]


# ─── ResumeContent ───────────────────────────────────────────────────────


class TestResumeContent:
    def test_minimal(self) -> None:
        content = ResumeContent(
            name="X",
            contact={"email": "a@b"},
            summary="s",
            skills=["Python"],
        )
        assert content.experience == []
        assert content.keyword_coverage == "0%"