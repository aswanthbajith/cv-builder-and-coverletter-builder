"""Smoke tests for the legacy engines (M1 keeps them working).

These tests intentionally exercise the *current* implementation in
``src/`` — they validate that the M1 refactor didn't break the
existing engines. M2 will rewrite each test to use a BaseEngine
protocol and Pydantic models.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure the legacy src/ is on path for these smoke tests only.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_automation.config import load_config
from job_automation.io import load_profile

from excel_loader import ExcelLoader  # noqa: E402
from deduplicator import Deduplicator  # noqa: E402
from matcher import JobMatcher, MatchResult  # noqa: E402
from resume_generator import ResumeGenerator  # noqa: E402
from cover_letter_generator import CoverLetterGenerator  # noqa: E402
from latex_compiler import LaTeXCompiler  # noqa: E402
from excel_updater import ExcelUpdater  # noqa: E402


class TestLegacyConfigShim(unittest.TestCase):
    """``src/config.py`` should now raise a clear error."""

    def test_legacy_config_imports_raise(self):
        with self.assertRaises(ImportError):
            import config  # noqa: F401


class TestNewConfig(unittest.TestCase):
    """Verify the new pydantic-settings config also loads."""

    def test_load_config_returns_appconfig(self):
        cfg = load_config()
        from job_automation.config import AppConfig
        self.assertIsInstance(cfg, AppConfig)


class TestProfileIo(unittest.TestCase):
    def test_load_profile(self):
        profile = load_profile()
        self.assertEqual(profile.name, "Aswanth Bindu Ajith")
        self.assertIn("Python", profile.technical_skills["programming_languages"])


class TestExcelLoader(unittest.TestCase):
    def test_column_aliases(self):
        loader = ExcelLoader()
        self.assertIn("company", loader.COLUMN_ALIASES)
        self.assertIn("job_title", loader.COLUMN_ALIASES)


class TestDeduplicator(unittest.TestCase):
    def test_initialization(self):
        dedup = Deduplicator()
        self.assertAlmostEqual(dedup.similarity_threshold, 0.95)

    def test_simple_duplicate(self):
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "company": "Acme Corp",
                    "job_title": "Python Dev",
                    "location": "Berlin",
                    "job_description": "Build things",
                },
                {
                    "company": "Acme Corp",
                    "job_title": "Python Dev",
                    "location": "Berlin",
                    "job_description": "Build things",
                },
            ]
        )
        dedup = Deduplicator()
        result = dedup.deduplicate(df)
        self.assertTrue(result["duplicate"].iloc[1])


class TestJobMatcher(unittest.TestCase):
    def test_analyze_job(self):
        matcher = JobMatcher()
        job = {
            "job_title": "Python Developer",
            "job_description": "We need a Python developer with HPC skills.",
            "required_skills": "Python, NumPy, HPC",
        }
        result = matcher.analyze_job(job)
        self.assertIsInstance(result, MatchResult)
        self.assertGreaterEqual(result.overall_score, 0)
        self.assertLessEqual(result.overall_score, 100)
        self.assertIn(result.status, ["proceed", "skip", "review"])

    def test_score_education(self):
        matcher = JobMatcher()
        score = matcher._score_education({}, "master degree required")
        self.assertGreater(score, 0.5)


class TestResumeGenerator(unittest.TestCase):
    def test_build_content(self):
        gen = ResumeGenerator()
        job = {
            "job_title": "HPC Engineer",
            "job_description": "HPC and Python",
            "required_skills": "Python, MPI",
        }
        profile = {
            "name": "Test User",
            "contact": {"email": "test@example.com"},
            "professional_summary": "Summary here.",
            "technical_skills": ["Python", "HPC", "MPI"],
            "experience": [
                {
                    "title": "Dev",
                    "company": "Co",
                    "location": "City",
                    "period": "2020-2021",
                    "description": ["Did stuff with Python"],
                }
            ],
            "education": [
                {"degree": "MSc", "institution": "Uni", "period": "2020", "grade": "1.0"}
            ],
            "projects": [{"name": "Proj", "description": "Desc"}],
            "languages": [{"language": "English", "proficiency": "Fluent"}],
        }
        content = gen._build_resume_content(job, profile, None)
        self.assertIn("name", content)
        self.assertIn("skills", content)
        self.assertEqual(content["name"], "Test User")


class TestCoverLetterGenerator(unittest.TestCase):
    def test_generate(self):
        gen = CoverLetterGenerator()
        job = {
            "company": "TestCorp",
            "job_title": "Dev",
            "job_description": "Python and HPC work.",
        }
        profile = {
            "name": "Test User",
            "contact": {
                "email": "test@example.com",
                "phone": "123",
                "location": "Berlin",
                "linkedin": "li",
            },
            "experience": [{"title": "Intern", "highlight": "Did stuff."}],
            "projects": [{"name": "Proj", "description": "Desc"}],
        }
        path = gen.generate(job, profile, None, "Test_TestCorp")
        self.assertTrue(Path(path).exists())


class TestLaTeXCompiler(unittest.TestCase):
    def test_compile_missing_file(self):
        compiler = LaTeXCompiler()
        result = compiler.compile(Path("nonexistent.tex"))
        self.assertIsNone(result)


class TestExcelUpdater(unittest.TestCase):
    def test_hyperlinks(self):
        import pandas as pd

        updater = ExcelUpdater()
        df = pd.DataFrame({"resume_pdf": ["C:/tmp/test.pdf"], "cover_letter": [None]})
        linked = updater._add_hyperlinks(df)
        self.assertIn("HYPERLINK", linked["resume_pdf"].iloc[0])
        self.assertEqual(linked["cover_letter"].iloc[0], "")


if __name__ == "__main__":
    unittest.main()