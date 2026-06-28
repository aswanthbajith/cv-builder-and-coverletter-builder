from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from job_automation.engines.achievement_rewriter import AchievementRewriter
from job_automation.engines.ats_validator import ATSValidator
from job_automation.engines.base import PipelineContext
from job_automation.engines.company_researcher import CompanyResearcher
from job_automation.engines.experience_selector import ExperienceSelector
from job_automation.engines.job_analyzer import JobAnalyzer
from job_automation.engines.keyword_extractor import ATSKeywordExtractor
from job_automation.engines.latex_generator import LaTeXGenerator, build_draft_resume
from job_automation.engines.orchestrator import Pipeline
from job_automation.engines.project_selector import ProjectSelector
from job_automation.engines.recruiter_reviewer import RecruiterReviewer
from job_automation.engines.resume_critic import ResumeCritic
from job_automation.engines.skill_gap import SkillGapAnalyzer
from job_automation.engines.summary_generator import SummaryGenerator
from job_automation.engines.llm_client import FakeLLMClient
from job_automation.knowledge.graph import KnowledgeGraph, load_knowledge_graph
from job_automation.knowledge.retriever import (
    detect_role_family,
    find_relevant_experiences,
    group_by_source_ref,
)
from job_automation.models.analysis import ATSKeyword, JobAnalysis, SkillGapReport
from job_automation.models.atomic import AtomicExperience
from job_automation.models.company import CompanyProfile
from job_automation.models.job import Job
from job_automation.models.profile import Profile
from job_automation.models.results import ResumeContent
from job_automation.models.review import CriticReview


class RaisingLLM:
    async def complete_json(self, **_: object) -> dict[str, object]:
        raise RuntimeError("boom")

    async def complete_text(self, **_: object) -> str:
        raise RuntimeError("boom")


class StubEngine:
    def __init__(self, *, name: str, produces: frozenset[str], handler) -> None:
        self.name = name
        self.timeout_s = 1.0
        self.requires = frozenset()
        self.produces = produces
        self._handler = handler

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        return await self._handler(ctx)


@pytest.fixture
def sample_graph() -> KnowledgeGraph:
    atoms = [
        AtomicExperience(
            id="exp_hpc_1",
            source="work",
            source_ref="acme_hpc",
            title="HPC Simulation Engineer",
            action_verb="Implemented",
            context="Developed Python MPI workloads for supercomputers.",
            details="Built GPU and MPI pipelines for simulations.",
            outcome="Reduced runtime by 40%.",
            technologies=["Python", "MPI", "CUDA"],
            skills=["parallel computing", "performance tuning"],
            metrics=["40%"],
            role_family_tags=["hpc"],
        ),
        AtomicExperience(
            id="exp_quantum_1",
            source="project",
            source_ref="qiskit_proj",
            title="Quantum Algorithm Prototype",
            action_verb="Built",
            context="Explored variational circuits with Qiskit.",
            details="Benchmarked circuits on local simulators.",
            outcome="Validated algorithmic approaches.",
            technologies=["Qiskit", "Python"],
            skills=["research", "algorithms"],
            metrics=[],
            role_family_tags=["quantum"],
        ),
        AtomicExperience(
            id="exp_software_1",
            source="work",
            source_ref="acme_sw",
            title="Backend Service Engineer",
            action_verb="Optimized",
            context="Improved service reliability for cloud workloads.",
            details="Wrote Python services and deployment tooling.",
            outcome="Cut deployment time by 30%.",
            technologies=["Python", "Docker", "Git"],
            skills=["software engineering"],
            metrics=["30%"],
            role_family_tags=["software"],
        ),
        AtomicExperience(
            id="exp_data_1",
            source="project",
            source_ref="ml_proj",
            title="Machine Learning Experiment",
            action_verb="Trained",
            context="Trained forecasting models for research data.",
            details="Used pandas and scikit-learn for feature engineering.",
            outcome="Improved accuracy by 12%.",
            technologies=["Python", "pandas", "scikit-learn"],
            skills=["data analysis"],
            metrics=["12%"],
            role_family_tags=["data"],
        ),
    ]
    return KnowledgeGraph(atoms)


@pytest.fixture
def sample_job() -> Job:
    return Job(
        company="Acme HPC",
        job_title="HPC Engineer",
        location="Berlin",
        job_description="Build high-performance Python simulations using MPI and CUDA.",
        required_skills="Python, MPI, CUDA, Linux",
        preferred_qualifications="Experience with GPU clusters and distributed systems.",
    )


@pytest.fixture
def sample_profile() -> Profile:
    return Profile(
        name="Test Candidate",
        contact={"email": "test@example.com", "phone": "+49 000", "location": "Berlin"},
        technical_skills={
            "programming_languages": ["Python", "C++"],
            "hpc_parallel": ["MPI", "CUDA"],
            "scientific_computing": ["NumPy"],
        },
        experience=[
            {
                "title": "Working Student",
                "company": "Acme",
                "location": "Berlin",
                "period": "2024-present",
                "description": ["Built HPC workflows"],
                "technologies": ["Python", "MPI"],
            }
        ],
        education=[
            {
                "degree": "M.Sc. HPC",
                "institution": "TU Berlin",
                "period": "2024-present",
            }
        ],
        projects=[
            {
                "name": "Simulation Study",
                "description": ["Simulated large systems"],
                "technologies": ["Python"],
                "metrics": ["40%"],
            }
        ],
        languages=[{"language": "English", "proficiency": "Professional"}],
        research_interests=["HPC", "Distributed Computing"],
    )


@pytest.mark.asyncio
async def test_job_analyzer_falls_back_on_llm_error(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="1", job=sample_job, graph=sample_graph, profile=sample_profile)
    engine = JobAnalyzer(RaisingLLM())

    await engine.run(ctx)

    assert ctx.job_analysis is not None
    assert ctx.job_analysis.role_archetype == sample_job.job_title
    assert engine.name in ctx.errors


@pytest.mark.asyncio
async def test_skill_gap_analysis_buckets_keywords(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="1", job=sample_job, graph=sample_graph, profile=sample_profile)
    ctx.ats_keywords = [
        ATSKeyword(term="Python", weight=1.0),
        ATSKeyword(term="CUDA", weight=0.8),
        ATSKeyword(term="Rust", weight=0.7),
    ]
    await SkillGapAnalyzer().run(ctx)

    assert ctx.skill_gaps is not None
    assert "Python" in ctx.skill_gaps.matched
    assert "CUDA" in ctx.skill_gaps.matched
    assert "Rust" in ctx.skill_gaps.missing


@pytest.mark.asyncio
async def test_selectors_and_retriever_rank_relevant_atoms(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="2", job=sample_job, graph=sample_graph, profile=sample_profile)

    await ExperienceSelector(top_k=6, max_source_refs=2).run(ctx)
    assert len(ctx.selected_experiences) <= 8

    await ProjectSelector(top_k=6, max_source_refs=2, max_atoms_per_ref=2).run(ctx)
    assert len(ctx.selected_projects) <= 4

    scored = find_relevant_experiences(sample_job, sample_graph, top_k=4)
    assert scored
    assert scored[0].experience.id == "exp_hpc_1"
    assert detect_role_family(sample_job) == "hpc"
    grouped = group_by_source_ref(scored)
    assert grouped


@pytest.mark.asyncio
async def test_company_researcher_populates_cache(tmp_path: Path, sample_job: Job, sample_profile: Profile) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    paths = SimpleNamespace(profile_dir=profile_dir)
    ctx = PipelineContext(run_id="3", job=sample_job, graph=KnowledgeGraph([]), profile=sample_profile)
    researcher = CompanyResearcher(
        paths=paths,
        research_fn=lambda company, title: {
            "name": company,
            "focus_areas": ["HPC"],
            "technologies": ["CUDA"],
            "terminology": ["MPI"],
        },
    )

    await researcher.run(ctx)

    assert isinstance(ctx.company_profile, CompanyProfile)
    assert (profile_dir / "company_cache" / "acme_hpc.json").exists()


@pytest.mark.asyncio
async def test_keyword_extractor_and_grounding_logic(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="4", job=sample_job, graph=sample_graph, profile=sample_profile)
    ctx.job_analysis = JobAnalysis(role_archetype="HPC Engineer", themes=["CUDA"], must_haves=["MPI"], nice_to_haves=["Linux"], seniority="mid")
    ctx.company_profile = CompanyProfile.empty(sample_job.company)
    await ATSKeywordExtractor().run(ctx)

    assert ctx.ats_keywords
    assert any(k.term.lower() in {"ython", "inux", "simulations", "using"} for k in ctx.ats_keywords)

    from job_automation.engines.grounding import validate_grounding

    atom = AtomicExperience(
        id="grounded",
        source="project",
        source_ref="local",
        title="GPU Port",
        action_verb="Implemented",
        context="Ported code to GPU kernels.",
        details="Used CUDA and Python for kernels.",
        outcome="Achieved 2x speedup.",
        technologies=["CUDA", "Python"],
        metrics=["2x"],
    )
    assert validate_grounding("Implemented CUDA and Python kernels with 2x speedup.", atom) == []
    assert validate_grounding("Used TensorFlow with 3x speedup.", atom)


@pytest.mark.asyncio
async def test_achievement_rewriter_and_summary_generator_use_fake_llm(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="5", job=sample_job, graph=sample_graph, profile=sample_profile)
    ctx.job_analysis = JobAnalysis(role_archetype="HPC Engineer", themes=["MPI"], must_haves=["CUDA"], nice_to_haves=["Linux"], seniority="mid")
    ctx.ats_keywords = [ATSKeyword(term="Python", weight=1.0), ATSKeyword(term="MPI", weight=1.0)]
    ctx.selected_experiences = [
        SimpleNamespace(
            experience=AtomicExperience(
                id="exp_hpc_1",
                source="work",
                source_ref="acme_hpc",
                title="HPC Simulation Engineer",
                action_verb="Implemented",
                context="Built GPU simulation workflows.",
                details="Used Python and MPI for large-scale runs.",
                outcome="Improved runtime by 40%.",
                technologies=["Python", "MPI"],
                metrics=["40%"],
            ),
            score=0.9,
            rewrite=None,
        )
    ]
    ctx.selected_projects = []

    llm = FakeLLMClient()
    llm.set_json_response("achievement_rewriter", "source_ref", {"bullets": ["Implemented Python and MPI workflows for GPU simulations."]})
    llm.set_json_response("summary_generator", "summary", {"summary": "HPC-focused engineer with Python and MPI experience."})

    await AchievementRewriter(llm).run(ctx)
    await SummaryGenerator(llm).run(ctx)

    assert ctx.rewritten_bullets["acme_hpc"]
    assert ctx.summary is not None


@pytest.mark.asyncio
async def test_ats_validator_resume_critic_and_recruiter_reviewer(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    ctx = PipelineContext(run_id="6", job=sample_job, graph=sample_graph, profile=sample_profile)
    ctx.ats_keywords = [ATSKeyword(term="Python", weight=1.0), ATSKeyword(term="MPI", weight=1.0)]
    ctx.draft_resume = ResumeContent(
        name="Test Candidate",
        contact={"email": "test@example.com"},
        summary="HPC-focused engineer with Python and MPI experience.",
        skills=["Python, MPI"],
        experience=[{"title": "Engineer", "company": "Acme", "description": ["Implemented Python and MPI workflows with 40% speedup."]}],
        education=[{"degree": "M.Sc.", "institution": "TU", "period": "2024"}],
        projects=[{"name": "Simulation", "description": ["Used Python and MPI."]}],
        languages=[{"language": "English", "proficiency": "Professional"}],
        research_interests=["HPC"],
    )
    ctx.job_analysis = JobAnalysis(role_archetype="HPC Engineer", themes=["MPI"], must_haves=["CUDA"], nice_to_haves=["Linux"], seniority="mid")

    await ATSValidator().run(ctx)
    assert ctx.ats_score is not None
    assert ctx.ats_score.overall >= 0.0

    critic = ResumeCritic(FakeLLMClient())
    await critic.run(ctx)
    assert ctx.critic_iterations[-1].verdict in {"pass", "reject", "revise"}

    reviewer = RecruiterReviewer(FakeLLMClient())
    await reviewer.run(ctx)
    assert reviewer.name in {"recruiter_reviewer"}
    assert ctx.recruiter_review is not None


@pytest.mark.asyncio
async def test_latex_generator_renders_tex_and_pdf(tmp_path: Path, sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = PipelineContext(run_id="7", job=sample_job, graph=sample_graph, profile=sample_profile)
    ctx.summary = "HPC-focused engineer with Python and MPI experience."
    ctx.ats_keywords = [ATSKeyword(term="Python", weight=1.0)]
    ctx.rewritten_bullets = {"work_acme": ["Implemented Python and MPI workflows for GPU simulations."]}
    ctx.rewritten_project_bullets = {}
    ctx.draft_resume = build_draft_resume(ctx)

    monkeypatch.setattr("job_automation.engines.latex_generator._find_xelatex", lambda: "/fake/xelatex")

    class DummyCompletedProcess:
        returncode = 0

    def _fake_run(cmd: list[str], *args: object, **kwargs: object) -> DummyCompletedProcess:
        output_dir = Path(cmd[cmd.index("-output-directory") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = Path(cmd[-1])
        (output_dir / f"{tex_path.stem}.pdf").write_bytes(b"pdf")
        return DummyCompletedProcess()

    monkeypatch.setattr("job_automation.engines.latex_generator.subprocess.run", _fake_run)

    generator = LaTeXGenerator(output_dir=tmp_path, compile_pdf=True)
    await generator.run(ctx)

    assert ctx.resume_tex_path is not None
    assert ctx.resume_tex_path.exists()
    assert ctx.resume_pdf_path is not None
    assert ctx.resume_pdf_path.exists()


def test_cli_resolution_and_parsing() -> None:
    from job_automation.cli import _parse_args, _resolve_engine

    args = _parse_args(["--engine", "v2", "--job-row", "1", "--dry-run", "--input", "custom.xlsx"])
    assert args.engine == "v2"
    assert args.job_row == 1
    assert args.dry_run is True
    assert _resolve_engine("legacy", "v2") == "legacy"
    assert _resolve_engine(None, "bad") == "legacy"
    assert _resolve_engine("v2", None) == "v2"


def test_load_knowledge_graph_from_disk(tmp_path: Path) -> None:
    profile_dir = tmp_path / "profile"
    atomic_dir = profile_dir / "atomic"
    atomic_dir.mkdir(parents=True, exist_ok=True)
    (atomic_dir / "index.json").write_text(
        '{"categories": [{"path": "coursework/test.json"}] }',
        encoding="utf-8",
    )
    (atomic_dir / "coursework" / "test.json").parent.mkdir(parents=True, exist_ok=True)
    (atomic_dir / "coursework" / "test.json").write_text(
        '[{"id": "atom1", "source": "work", "source_ref": "ref1", "title": "Test", "action_verb": "Built", "context": "Context", "details": "Details", "outcome": "Outcome", "technologies": ["Python"], "skills": ["analysis"], "metrics": [], "domain_tags": [], "role_family_tags": ["software"], "seniority": "junior"}]',
        encoding="utf-8",
    )

    graph = load_knowledge_graph(SimpleNamespace(profile_dir=profile_dir), with_embeddings=False)
    assert len(graph) == 1
    assert graph.get("atom1") is not None


def test_knowledge_graph_accessors(sample_graph: KnowledgeGraph) -> None:
    assert len(sample_graph) == 4
    assert sample_graph.get("exp_hpc_1") is not None
    assert sample_graph.by_skill("parallel computing")
    assert sample_graph.by_technology("cuda")
    assert sample_graph.by_role_family("hpc")
    assert sample_graph.by_source_ref("acme_hpc")

    dummy_index = SimpleNamespace(search=lambda query, top_k: [("exp_hpc_1", 0.9)])
    wrapped = sample_graph.with_embeddings(dummy_index)
    assert wrapped.embedding_index is dummy_index
    assert wrapped.get("exp_hpc_1") is not None


def test_retriever_scoring_helpers() -> None:
    from job_automation.knowledge.retriever import _keyword_overlap_score, _normalize, _role_family_score, detect_role_family
    from job_automation.models.atomic import AtomicExperience

    atom = AtomicExperience(
        id="a",
        source="work",
        source_ref="ref",
        title="HPC Simulation",
        action_verb="Implemented",
        context="Built Python MPI workflows.",
        details="Used CUDA and openmp.",
        outcome="Improved performance.",
        technologies=["Python", "MPI"],
        skills=["performance tuning"],
        metrics=["40%"],
        role_family_tags=["hpc"],
        seniority="mid",
    )
    assert _normalize("Python 3.11") == {"python", "3.11"}
    assert _keyword_overlap_score(atom, {"python", "mpi"}) > 0.0
    assert _role_family_score(atom, "hpc") == 1.0
    job = Job(
        company="Acme HPC",
        job_title="HPC Engineer",
        location="Berlin",
        job_description="Build high-performance Python simulations using MPI and CUDA.",
        required_skills="Python, MPI, CUDA, Linux",
        preferred_qualifications="Experience with GPU clusters and distributed systems.",
    )
    assert detect_role_family(job) == "hpc"


def test_pipeline_error_summarization_and_embedding_persistence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    from job_automation.engines.orchestrator import Pipeline
    from job_automation.engines.base import PipelineContext
    from job_automation.models.results import GenerationResult
    from job_automation.knowledge.embeddings import build_or_load_embedding_index

    class NoopEngine:
        name = "noop"
        timeout_s = 1.0
        requires = frozenset()
        produces = frozenset()

        async def run(self, ctx: PipelineContext) -> PipelineContext:
            return ctx

    pipeline = Pipeline(
        job_analyzer=NoopEngine(),
        company_researcher=NoopEngine(),
        keyword_extractor=NoopEngine(),
        skill_gap=NoopEngine(),
        experience_selector=NoopEngine(),
        achievement_rewriter=NoopEngine(),
        project_selector=NoopEngine(),
        summary_generator=NoopEngine(),
        resume_critic=NoopEngine(),
        ats_validator=NoopEngine(),
        recruiter_reviewer=NoopEngine(),
        latex_generator=NoopEngine(),
    )

    ctx = PipelineContext(run_id="test", job=sample_job, graph=sample_graph, profile=sample_profile)
    monkeypatch.setattr("job_automation.engines.orchestrator.logger.exception", lambda *args, **kwargs: None)
    result = asyncio.run(pipeline.process_async(ctx.job, ctx.graph, ctx.profile))
    assert isinstance(result, GenerationResult)

    # Embedding persistence helpers should return None for empty experience lists.
    ids_path = tmp_path / "ids.json"
    ids_path.write_text('["a", "b"]', encoding="utf-8")
    assert build_or_load_embedding_index([], tmp_path) is None


def test_pipeline_process_sync_with_stub_engines(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    async def noop_handler(ctx: PipelineContext) -> PipelineContext:
        return ctx

    async def job_handler(ctx: PipelineContext) -> PipelineContext:
        ctx.job_analysis = JobAnalysis(role_archetype="HPC", themes=["MPI"], must_haves=["CUDA"], nice_to_haves=["Linux"], seniority="mid")
        return ctx

    async def skill_handler(ctx: PipelineContext) -> PipelineContext:
        ctx.skill_gaps = SkillGapReport(matched=["Python"], partial=[], missing=[], transferable=[])
        return ctx

    async def summary_handler(ctx: PipelineContext) -> PipelineContext:
        ctx.summary = "Summary"
        return ctx

    async def latex_handler(ctx: PipelineContext) -> PipelineContext:
        ctx.resume_tex_path = Path("generated/CV/v2/test.tex")
        ctx.resume_pdf_path = Path("generated/CV/v2/test.pdf")
        return ctx

    pipeline = Pipeline(
        job_analyzer=StubEngine(name="job_analyzer", produces=frozenset({"job_analysis"}), handler=job_handler),
        company_researcher=StubEngine(name="company_researcher", produces=frozenset({"company_profile"}), handler=noop_handler),
        keyword_extractor=StubEngine(name="keyword_extractor", produces=frozenset({"ats_keywords"}), handler=noop_handler),
        skill_gap=StubEngine(name="skill_gap", produces=frozenset({"skill_gaps"}), handler=skill_handler),
        experience_selector=StubEngine(name="experience_selector", produces=frozenset({"selected_experiences"}), handler=noop_handler),
        achievement_rewriter=StubEngine(name="achievement_rewriter", produces=frozenset({"rewritten_bullets"}), handler=noop_handler),
        project_selector=StubEngine(name="project_selector", produces=frozenset({"selected_projects"}), handler=noop_handler),
        summary_generator=StubEngine(name="summary_generator", produces=frozenset({"summary"}), handler=summary_handler),
        resume_critic=StubEngine(name="resume_critic", produces=frozenset({"critic_iterations"}), handler=noop_handler),
        ats_validator=StubEngine(name="ats_validator", produces=frozenset({"ats_score"}), handler=noop_handler),
        recruiter_reviewer=StubEngine(name="recruiter_reviewer", produces=frozenset({"recruiter_review"}), handler=noop_handler),
        latex_generator=StubEngine(name="latex_generator", produces=frozenset({"resume_tex_path", "resume_pdf_path"}), handler=latex_handler),
    )

    result = pipeline.process_sync(sample_job, sample_graph, sample_profile)

    assert result.job == sample_job
    assert result.match.status in {"proceed", "review", "skip"}


def test_orchestrator_run_engine_captures_errors(sample_job: Job, sample_profile: Profile, sample_graph: KnowledgeGraph) -> None:
    class FailingEngine:
        name = "bad"
        timeout_s = 1.0
        requires = frozenset()
        produces = frozenset()

        async def run(self, ctx: PipelineContext) -> PipelineContext:
            raise RuntimeError("boom")

    class SlowEngine:
        name = "slow"
        timeout_s = 0.001
        requires = frozenset()
        produces = frozenset()

        async def run(self, ctx: PipelineContext) -> PipelineContext:
            await asyncio.sleep(0.01)
            return ctx

    pipeline = Pipeline(
        job_analyzer=StubEngine(name="job_analyzer", produces=frozenset(), handler=lambda ctx: None),
        company_researcher=StubEngine(name="company_researcher", produces=frozenset(), handler=lambda ctx: None),
        keyword_extractor=StubEngine(name="keyword_extractor", produces=frozenset(), handler=lambda ctx: None),
        skill_gap=StubEngine(name="skill_gap", produces=frozenset(), handler=lambda ctx: None),
        experience_selector=StubEngine(name="experience_selector", produces=frozenset(), handler=lambda ctx: None),
        achievement_rewriter=StubEngine(name="achievement_rewriter", produces=frozenset(), handler=lambda ctx: None),
        project_selector=StubEngine(name="project_selector", produces=frozenset(), handler=lambda ctx: None),
        summary_generator=StubEngine(name="summary_generator", produces=frozenset(), handler=lambda ctx: None),
        resume_critic=StubEngine(name="resume_critic", produces=frozenset(), handler=lambda ctx: None),
        ats_validator=StubEngine(name="ats_validator", produces=frozenset(), handler=lambda ctx: None),
        recruiter_reviewer=StubEngine(name="recruiter_reviewer", produces=frozenset(), handler=lambda ctx: None),
        latex_generator=StubEngine(name="latex_generator", produces=frozenset(), handler=lambda ctx: None),
    )
    ctx = PipelineContext(run_id="8", job=sample_job, graph=sample_graph, profile=sample_profile)

    asyncio.run(pipeline._run_engine(ctx, FailingEngine()))
    asyncio.run(pipeline._run_engine(ctx, SlowEngine()))

    assert ctx.errors["bad"] == "boom"
    assert ctx.errors["slow"].startswith("timeout_after")


def test_logging_helpers() -> None:
    from job_automation.logging import configure_logging, get_logger

    cfg = SimpleNamespace(level="INFO", format="console", file_enabled=False)
    configure_logging(cfg)
    logger = get_logger("tests")
    logger.info("coverage_check", extra={"ok": True})


def test_cli_main_and_v2_entrypoints(monkeypatch: pytest.MonkeyPatch) -> None:
    from job_automation import cli

    monkeypatch.setattr(cli, "_run_legacy", lambda args, cfg: 3)
    monkeypatch.setattr(cli, "_run_v2", lambda args, cfg: 7)

    class DummyCfg:
        resume_engine = "legacy"
        logging = SimpleNamespace()

    monkeypatch.setattr("job_automation.config.load_config", lambda: DummyCfg())
    monkeypatch.setattr("job_automation.logging.configure_logging", lambda cfg: None)

    assert cli.main(["--engine", "legacy"]) == 3
    assert cli.main(["--engine", "v2"]) == 7


def test_llm_client_fake_and_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    from job_automation.engines.exceptions import LLMUnavailable
    from job_automation.engines.llm_client import GeminiClient, FakeLLMClient

    fake = FakeLLMClient()
    fake.set_json_response("engine", "prompt", {"ok": True})
    fake.set_text_response("engine", "text")

    assert asyncio.run(fake.complete_json("s", "prompt", {})) == {"ok": True}
    assert asyncio.run(fake.complete_text("s", "prompt")) == '{"ok": true}'

    client = GeminiClient(api_key="x")

    class FakeResponse:
        text = '{"ok": true}'

    class FakeModel:
        def generate_content(self, *args: object, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    client._ensure_client = lambda: FakeModel()  # type: ignore[assignment]
    payload = asyncio.run(client.complete_json("s", "u", {"type": "object"}))
    assert payload == {"ok": True}
    text = asyncio.run(client.complete_text("s", "u"))
    assert text == '{"ok": true}'

    class FailingThenWorkingModel:
        calls = 0

        def generate_content(self, *args: object, **kwargs: object) -> FakeResponse:
            self.calls += 1
            if self.calls == 1:
                raise ValueError("temporary")
            return FakeResponse()

    client._ensure_client = lambda: FailingThenWorkingModel()  # type: ignore[assignment]
    payload = asyncio.run(client.complete_json("s", "u", {"type": "object"}))
    assert payload == {"ok": True}

    class AlwaysFailingModel:
        def generate_content(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("fail")

    client._ensure_client = lambda: AlwaysFailingModel()  # type: ignore[assignment]
    with pytest.raises(LLMUnavailable):
        asyncio.run(client.complete_text("s", "u"))


def test_profile_loader_and_excel_reader_helpers(tmp_path: Path) -> None:
    from job_automation.io.excel_reader import _coerce_job_type, _coerce_skill_lists, _normalize_columns, _row_to_job
    from job_automation.io.profile_loader import load_profile

    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "master_resume.json").write_text(json.dumps({"name": "Tester", "contact": {"email": "a@b.com"}, "technical_skills": {"programming_languages": ["Python"]}}), encoding="utf-8")
    (profile_dir / "experience.json").write_text(json.dumps({"experience": [{"title": "Engineer", "company": "Acme", "location": "Berlin", "period": "2024-present", "description": ["Built stuff"], "technologies": ["Python"]}]}), encoding="utf-8")
    profile = load_profile(SimpleNamespace(profile_dir=profile_dir))
    assert profile.name == "Tester"

    import pandas as pd

    df = pd.DataFrame([{"Company": "Acme", "Job Title": "Engineer", "Location": "Berlin", "Description": "Build things", "Required Skills": "Python, MPI", "Job Type": "Internship"}])
    normalized = _normalize_columns(df)
    assert "company" in normalized.columns
    row = _row_to_job(normalized.iloc[0].to_dict())
    assert row.job_type == "internship"
    assert row.key_matching_skills == []
    assert _coerce_job_type({"job_type": "unknown"})["job_type"] == "unknown"
    assert _coerce_skill_lists({"key_matching_skills": "Python; MPI"})["key_matching_skills"] == ["Python", "MPI"]


def test_grounding_and_embeddings_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from job_automation.engines.grounding import grounding_failure_ratio, validate_grounding
    from job_automation.knowledge.embeddings import EmbeddingIndex, build_or_load_embedding_index, json_dumps_ids, json_load_ids

    atom = AtomicExperience(
        id="a",
        source="project",
        source_ref="r",
        title="GPU Port",
        action_verb="Implemented",
        context="Ported code to GPU kernels.",
        details="Used CUDA and Python.",
        outcome="Achieved 2x speedup.",
        technologies=["CUDA", "Python"],
        metrics=["2x"],
    )
    assert validate_grounding("Implemented CUDA and Python kernels with 2x speedup.", atom) == []
    assert grounding_failure_ratio(["Used TensorFlow with 3x speedup."], [atom]) == 1.0

    import numpy as np

    class FakeModel:
        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> object:
            return np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    monkeypatch.setattr("job_automation.knowledge.embeddings._get_model", lambda: FakeModel())
    monkeypatch.setattr("job_automation.knowledge.embeddings._build_faiss_index", lambda vectors: None)
    index = EmbeddingIndex(["a", "b"], np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    assert index.search("cuda", top_k=1) == []

    ids_path = tmp_path / "ids.json"
    ids_path.write_text(json_dumps_ids(["a", "b"]), encoding="utf-8")
    assert json_load_ids(ids_path) == ["a", "b"]

    monkeypatch.setattr("job_automation.knowledge.embeddings._get_model", lambda: FakeModel())
    monkeypatch.setattr("job_automation.knowledge.embeddings._persist_faiss", lambda vectors, path: None)
    built = build_or_load_embedding_index([atom], tmp_path)
    assert built is not None
