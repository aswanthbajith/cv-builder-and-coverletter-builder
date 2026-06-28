"""Shared pytest fixtures.

The conftest does *not* manipulate ``sys.path`` — the new package is
installed via ``pip install -e ".[dev]"`` (see ``pyproject.toml``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from job_automation.config import (
    AppConfig,
    AtsConfig,
    GenerationConfig,
    LoggingConfig,
    MatchingConfig,
    PathsConfig,
    reset_config_cache,
)
from job_automation.models import (
    EducationEntry,
    ExperienceEntry,
    Job,
    LanguageEntry,
    Profile,
    ProjectEntry,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def config_yaml(project_root: Path) -> Path:
    """Path to the project's real config.yaml — used for round-trip tests."""
    return project_root / "config.yaml"


@pytest.fixture
def app_config() -> AppConfig:
    """An isolated ``AppConfig`` built from defaults — no file I/O."""
    reset_config_cache()
    return AppConfig(
        paths=PathsConfig(
            input_excel=Path("input/jobs.xlsx"),
            output_excel=Path("output/test.xlsx"),
            profile_dir=Path("profile"),
            templates_dir=Path("templates"),
            generated_dir=Path("generated"),
            log_file=Path("generated/Logs/test.log"),
        ),
        matching=MatchingConfig(),
        generation=GenerationConfig(max_workers=2, compile_latex=False),
        ats=AtsConfig(),
        logging=LoggingConfig(level="DEBUG", format="console", file_enabled=False),
    )


@pytest.fixture
def sample_job() -> Job:
    """A minimal valid Job suitable for matcher/generator tests."""
    return Job(
        company="Acme HPC",
        job_title="HPC Engineer Intern",
        location="Berlin, Germany",
        job_description="Work on Python-based HPC simulations using MPI and NumPy.",
        required_skills="Python, NumPy, MPI, Linux",
        preferred_qualifications="Experience with C++ a plus.",
        application_url="https://acme.example/jobs/1",
        job_type="internship",
    )


@pytest.fixture
def sample_profile() -> Profile:
    """A representative Profile mirroring profile/master_resume.json."""
    return Profile(
        name="Test Candidate",
        contact={
            "email": "test@example.com",
            "phone": "+49 000",
            "location": "Berlin",
            "linkedin": "LinkedIn",
        },
        current_role="M.Sc. student in HPC",
        professional_summary="Interdisciplinary student with HPC foundations.",
        technical_skills={
            "programming_languages": ["Python", "C++", "JavaScript"],
            "hpc_parallel": ["MPI", "OpenMP", "GPU concepts"],
            "scientific_computing": ["NumPy", "Pandas", "SciPy"],
            "machine_learning": ["PyTorch", "scikit-learn"],
            "quantum_computing": ["Qiskit"],
        },
        experience=[
            ExperienceEntry(
                title="Working Student",
                company="Acme",
                location="Berlin",
                period="2025 - Present",
                description=["Shipped 5+ features in sprint cycles"],
                technologies=["Python", "Git"],
            )
        ],
        education=[
            EducationEntry(
                degree="M.Sc. HPC",
                institution="Test University",
                period="2024 - Present",
            )
        ],
        projects=[
            ProjectEntry(
                name="Large-Scale Simulation",
                description=["Built a 30,000-entity simulation in NumPy"],
                metrics=["40% runtime reduction"],
            )
        ],
        languages=[
            LanguageEntry(language="English", proficiency="Professional"),
        ],
        research_interests=["HPC", "Quantum Computing"],
        key_achievements=["Reduced runtime by 40%"],
    )


@pytest.fixture
def profile_dir(tmp_path: Path, sample_profile: Profile) -> Path:
    """Materialize a sample profile to ``tmp_path`` so IO loaders can read it."""
    import json

    pdir = tmp_path / "profile"
    pdir.mkdir()
    (pdir / "master_resume.json").write_text(
        json.dumps(
            {
                "name": sample_profile.name,
                "contact": sample_profile.contact,
                "current_role": sample_profile.current_role,
                "professional_summary": sample_profile.professional_summary,
                "technical_skills": sample_profile.technical_skills,
                "experience": [e.model_dump() for e in sample_profile.experience],
                "education": [e.model_dump() for e in sample_profile.education],
                "projects": [p.model_dump() for p in sample_profile.projects],
                "languages": [lang.model_dump() for lang in sample_profile.languages],
                "research_interests": sample_profile.research_interests,
                "key_achievements": sample_profile.key_achievements,
            }
        ),
        encoding="utf-8",
    )
    return pdir


@pytest.fixture(autouse=True)
def _reset_config_between_tests() -> None:
    """Avoid cross-test pollution from the ``load_config`` cache."""
    reset_config_cache()
    yield
    reset_config_cache()
