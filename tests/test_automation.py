"""Unit tests for the Job Application Automation System."""

import sys
import json
import unittest
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import config
from excel_loader import ExcelLoader
from deduplicator import Deduplicator
from matcher import JobMatcher, MatchResult
from resume_generator import ResumeGenerator
from cover_letter_generator import CoverLetterGenerator
from latex_compiler import LaTeXCompiler
from excel_updater import ExcelUpdater


class TestConfig(unittest.TestCase):
    def test_singleton(self):
        c1 = config
        c2 = config
        self.assertIs(c1, c2)

    def test_get_paths(self):
        self.assertIsNotNone(config.get('paths.input_excel'))
        self.assertIsNotNone(config.get('paths.output_excel'))


class TestExcelLoader(unittest.TestCase):
    def test_column_aliases(self):
        loader = ExcelLoader()
        self.assertIn('company', loader.COLUMN_ALIASES)
        self.assertIn('job_title', loader.COLUMN_ALIASES)


class TestDeduplicator(unittest.TestCase):
    def test_initialization(self):
        dedup = Deduplicator()
        self.assertAlmostEqual(dedup.similarity_threshold, 0.95)

    def test_simple_duplicate(self):
        import pandas as pd
        df = pd.DataFrame([
            {'company': 'Acme Corp', 'job_title': 'Python Dev', 'location': 'Berlin', 'job_description': 'Build things'},
            {'company': 'Acme Corp', 'job_title': 'Python Dev', 'location': 'Berlin', 'job_description': 'Build things'}
        ])
        dedup = Deduplicator()
        result = dedup.deduplicate(df)
        self.assertTrue(result['duplicate'].iloc[1])


class TestJobMatcher(unittest.TestCase):
    def test_analyze_job(self):
        matcher = JobMatcher()
        job = {
            'job_title': 'Python Developer',
            'job_description': 'We need a Python developer with HPC skills.',
            'required_skills': 'Python, NumPy, HPC'
        }
        result = matcher.analyze_job(job)
        self.assertIsInstance(result, MatchResult)
        self.assertGreaterEqual(result.overall_score, 0)
        self.assertLessEqual(result.overall_score, 100)
        self.assertIn(result.status, ['proceed', 'skip', 'review'])

    def test_score_education(self):
        matcher = JobMatcher()
        score = matcher._score_education({}, 'master degree required')
        self.assertGreater(score, 0.5)


class TestResumeGenerator(unittest.TestCase):
    def test_build_content(self):
        gen = ResumeGenerator()
        job = {'job_title': 'HPC Engineer', 'job_description': 'HPC and Python', 'required_skills': 'Python, MPI'}
        profile = {
            'name': 'Test User',
            'contact': {'email': 'test@example.com'},
            'professional_summary': 'Summary here.',
            'technical_skills': ['Python', 'HPC', 'MPI'],
            'experience': [{'title': 'Dev', 'company': 'Co', 'location': 'City', 'period': '2020-2021', 'description': ['Did stuff with Python']}],
            'education': [{'degree': 'MSc', 'institution': 'Uni', 'period': '2020', 'grade': '1.0'}],
            'projects': [{'name': 'Proj', 'description': 'Desc'}],
            'languages': [{'language': 'English', 'proficiency': 'Fluent'}]
        }
        content = gen._build_resume_content(job, profile, None)
        self.assertIn('name', content)
        self.assertIn('skills', content)
        self.assertEqual(content['name'], 'Test User')


class TestCoverLetterGenerator(unittest.TestCase):
    def test_generate(self):
        gen = CoverLetterGenerator()
        job = {'company': 'TestCorp', 'job_title': 'Dev', 'job_description': 'Python and HPC work.'}
        profile = {
            'name': 'Test User',
            'contact': {'email': 'test@example.com', 'phone': '123', 'location': 'Berlin', 'linkedin': 'li'},
            'experience': [{'title': 'Intern', 'highlight': 'Did stuff.'}],
            'projects': [{'name': 'Proj', 'description': 'Desc'}]
        }
        path = gen.generate(job, profile, None, 'Test_TestCorp')
        self.assertTrue(Path(path).exists())


class TestLaTeXCompiler(unittest.TestCase):
    def test_compile_missing_file(self):
        compiler = LaTeXCompiler()
        result = compiler.compile(Path('nonexistent.tex'))
        self.assertIsNone(result)


class TestExcelUpdater(unittest.TestCase):
    def test_hyperlinks(self):
        import pandas as pd
        updater = ExcelUpdater()
        df = pd.DataFrame({'resume_pdf': ['C:/tmp/test.pdf'], 'cover_letter': [None]})
        linked = updater._add_hyperlinks(df)
        self.assertIn('HYPERLINK', linked['resume_pdf'].iloc[0])
        self.assertEqual(linked['cover_letter'].iloc[0], '')


if __name__ == '__main__':
    unittest.main()
