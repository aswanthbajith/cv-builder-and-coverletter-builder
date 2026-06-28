"""Console entry point for the job-automation pipeline.

Supports two engines via ``--engine``:

- ``legacy`` — the M0 keyword-edit pipeline (``src/main.py``). Default
  during the migration window; identical to ``python src/main.py``.
- ``v2`` — the M2 knowledge-graph construction pipeline. The default
  target once Phase E flips ``config.yaml:resume_engine`` to ``v2``.

The CLI picks up the engine selection from the CLI flag, then falls
back to ``config.yaml:resume_engine``. Pass ``--job-row N`` to target a
single row of ``input/jobs.xlsx`` (useful for A/B comparison during
Phase D). Pass ``--dry-run`` to skip the LaTeX compile.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the legacy src/ importable from the installed entry point. This stays
# in place until M3 lands and the legacy package is removed.
_LEGACY_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(_LEGACY_SRC))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments. Exposed so tests can drive the parser."""
    parser = argparse.ArgumentParser(
        prog="job-automation",
        description="Generate role-tailored resumes from the candidate knowledge graph.",
    )
    parser.add_argument(
        "--engine",
        choices=("legacy", "v2"),
        default=None,
        help=(
            "Which pipeline to run. 'legacy' runs the M0 keyword-edit "
            "pipeline; 'v2' runs the M2 knowledge-graph pipeline. "
            "Falls back to config.yaml:resume_engine when omitted."
        ),
    )
    parser.add_argument(
        "--job-row",
        type=int,
        default=None,
        help=(
            "Zero-indexed row of input/jobs.xlsx to process. Omit to "
            "process the entire batch."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run the engines but skip xelatex compilation. Useful for "
            "A/B smoke tests and CI."
        ),
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Override the input Excel path (defaults to config.yaml).",
    )
    return parser.parse_args(argv)


def _resolve_engine(arg: str | None, cfg_engine: str | None) -> str:
    """CLI flag wins over config; both fall back to 'legacy'."""
    chosen = arg or cfg_engine or "legacy"
    if chosen not in ("legacy", "v2"):
        # Config files are user-editable — guard against typos.
        print(
            f"warning: unknown resume_engine '{chosen}' in config; defaulting to legacy",
            file=sys.stderr,
        )
        return "legacy"
    return chosen


def main(argv: list[str] | None = None) -> int:
    """Run the configured pipeline. Returns the process exit code."""
    from job_automation.config import load_config
    from job_automation.logging import configure_logging

    args = _parse_args(argv)
    cfg = load_config()
    configure_logging(cfg.logging)

    engine = _resolve_engine(args.engine, getattr(cfg, "resume_engine", None))
    if engine == "legacy":
        return _run_legacy(args, cfg)
    return _run_v2(args, cfg)


def _run_legacy(args: argparse.Namespace, cfg: object) -> int:
    """Delegate to the legacy ``src/main.py`` pipeline."""
    import main as legacy_main_mod

    result: int = legacy_main_mod.main()  # type: ignore[no-untyped-call]
    return int(result or 0)


def _run_v2(args: argparse.Namespace, cfg: object) -> int:
    """Run the M2 knowledge-graph pipeline against one job."""
    from job_automation.engines.llm_client import GeminiClient
    from job_automation.engines.orchestrator import build_default_pipeline
    from job_automation.io import load_profile, read_jobs_excel
    from job_automation.knowledge import load_knowledge_graph
    from job_automation.logging import get_logger

    logger = get_logger(__name__)
    input_path = args.input or getattr(cfg.paths, "input_excel", None) or Path("input/jobs.xlsx")
    jobs = read_jobs_excel(input_path)
    if args.job_row is not None:
        if args.job_row < 0 or args.job_row >= len(jobs):
            print(f"error: --job-row {args.job_row} out of range (0..{len(jobs)-1})")
            return 2
        jobs = [jobs[args.job_row]]

    logger.info("v2_pipeline_start", extra={"jobs": len(jobs), "dry_run": args.dry_run})

    profile = load_profile(getattr(cfg, "paths", None))
    graph = load_knowledge_graph()
    llm = GeminiClient()  # reads GEMINI_API_KEY from env
    pipeline = build_default_pipeline(llm)

    exit_code = 0
    for job in jobs:
        try:
            result = pipeline.process_sync(job, graph, profile)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "v2_pipeline_job_failed",
                extra={"company": job.company, "title": job.job_title, "error": str(exc)},
            )
            print(f"error: {job.company} — {exc}")
            exit_code = 1
            continue
        logger.info(
            "v2_pipeline_job_done",
            extra={
                "company": job.company,
                "title": job.job_title,
                "tex": str(result.resume_tex_path) if result.resume_tex_path else None,
                "pdf": str(result.resume_pdf_path) if result.resume_pdf_path else None,
                "error": result.error,
            },
        )
        if result.error:
            print(f"warn: {job.company} — {result.error}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())