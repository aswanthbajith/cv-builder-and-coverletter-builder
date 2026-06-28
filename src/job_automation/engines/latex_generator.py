"""LaTeXGenerator — render the final draft to a .tex file and (optionally) PDF.

Combines:
- The deterministic LaTeX template (kept aligned with the legacy
  ``templates/cv_template.tex`` so visual style is consistent across
  legacy and v2 output).
- The rewritten bullets from ``ctx.rewritten_bullets`` and
  ``ctx.rewritten_project_bullets``.
- The summary, skills, education from the legacy ``Profile`` (read from
  ``ctx.profile``).

Outputs:
    ctx.resume_tex_path (always)
    ctx.resume_pdf_path (when compile_latex is True and xelatex is on PATH)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from job_automation.config import load_config
from job_automation.engines.base import PipelineContext
from job_automation.logging import get_logger
from job_automation.models.results import ResumeContent

logger = get_logger(__name__)


_LATEX_SPECIAL_CHARS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def _escape(text: str) -> str:
    """Escape LaTeX special characters in a string."""
    out: list[str] = []
    for ch in str(text):
        out.append(_LATEX_SPECIAL_CHARS.get(ch, ch))
    return "".join(out)


class LaTeXGenerator:
    """Render :class:`ResumeContent` to .tex and (optionally) PDF."""

    name = "latex_generator"
    timeout_s = 5.0
    requires = frozenset({"draft_resume"})
    produces = frozenset({"resume_tex_path", "resume_pdf_path"})

    def __init__(
        self,
        output_dir: Path | None = None,
        *,
        compile_pdf: bool | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._compile_pdf = compile_pdf

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        cfg = load_config()
        if self._output_dir is None:
            base = cfg.paths.generated_dir / "CV" / "v2"
        else:
            base = self._output_dir
        tex_dir = base / "tex"
        pdf_dir = base / "pdf"
        tex_dir.mkdir(parents=True, exist_ok=True)
        pdf_dir.mkdir(parents=True, exist_ok=True)

        if ctx.draft_resume is None:
            ctx.errors[self.name] = "no_draft_resume"
            return ctx

        filename = _slug(f"{ctx.job.company}_{ctx.job.job_title}")
        tex_path = tex_dir / f"{filename}.tex"
        tex_path.write_text(_render(ctx), encoding="utf-8")
        ctx.resume_tex_path = tex_path
        logger.info("latex_generated", extra={"path": str(tex_path)})

        should_compile = self._compile_pdf
        if should_compile is None:
            should_compile = cfg.generation.compile_latex
        if not should_compile:
            return ctx

        xelatex = _find_xelatex()
        if xelatex is None:
            logger.warning("xelatex_missing_skipping_pdf")
            ctx.errors[self.name] = "xelatex_not_found"
            return ctx

        try:
            for _ in range(2):
                result = subprocess.run(
                    [xelatex, "-interaction=nonstopmode", "-halt-on-error",
                     "-output-directory", str(pdf_dir), str(tex_path)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    break
            pdf_path = pdf_dir / f"{filename}.pdf"
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                ctx.resume_pdf_path = pdf_path
                logger.info("latex_compiled", extra={"path": str(pdf_path)})
            else:
                ctx.errors[self.name] = "pdf_missing_after_compile"
        except Exception as exc:  # noqa: BLE001
            logger.warning("latex_compile_failed", extra={"error": str(exc)})
            ctx.errors[self.name] = str(exc)
        return ctx


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", str(text or ""))
    safe = re.sub(r"[-\s]+", "_", safe).strip("_")
    return safe[:80] or "resume"


def _find_xelatex() -> str | None:
    found = shutil.which("xelatex")
    if found:
        return found
    fallback = Path("C:/Program Files/MiKTeX/miktex/bin/x64/xelatex.exe")
    if fallback.exists():
        return str(fallback)
    return None


def _render(ctx: PipelineContext) -> str:
    """Render the LaTeX document body for the resume."""
    resume = ctx.draft_resume
    assert resume is not None
    name = _escape(resume.name)
    contact_parts = []
    for k, v in resume.contact.items():
        contact_parts.append(f"\\texttt{{{_escape(v)}}}")
    contact = " | ".join(contact_parts)

    summary = _escape(resume.summary or "")

    skills_block = " \\\\\n".join(_escape(line) for line in resume.skills)

    experience_block: list[str] = []
    for exp in resume.experience:
        title = _escape(exp.get("title", ""))
        location = _escape(exp.get("location", "") or "")
        company = _escape(exp.get("company", ""))
        period = _escape(exp.get("period", "") or "")
        bullets = exp.get("description", []) or []
        experience_block.append(
            "\\textbf{" + title + "} \\hfill \\textit{" + location + "}\\\\\n"
            "\\textit{" + company + "} \\hfill " + period + "\n"
            "\\begin{itemize}[leftmargin=*,nosep,topsep=2pt]\n"
            + "".join("\\item " + _escape(b) + "\n" for b in bullets)
            + "\\end{itemize}"
        )

    education_block: list[str] = []
    for edu in resume.education:
        degree = _escape(edu.get("degree", ""))
        period = _escape(edu.get("period", "") or "")
        institution = _escape(edu.get("institution", ""))
        grade = _escape(edu.get("grade", "") or "")
        line = f"\\textbf{{{degree}}} \\hfill {period}\\\\\n{institution} \\hfill {grade}"
        if edu.get("relevant_coursework"):
            line += "\\\\\\textit{Relevant coursework:} " + _escape(", ".join(edu["relevant_coursework"]))
        if edu.get("highlights"):
            line += "\\\\\\textit{Highlights:} " + _escape("; ".join(edu["highlights"]))
        education_block.append(line)

    projects_block: list[str] = []
    for proj in resume.projects:
        name_p = _escape(proj.get("name", ""))
        bullets = proj.get("description", []) or []
        projects_block.append(
            "\\textbf{" + name_p + "}\n"
            "\\begin{itemize}[leftmargin=*,nosep,topsep=2pt]\n"
            + "".join("\\item " + _escape(b) + "\n" for b in bullets)
            + "\\end{itemize}"
        )

    research = ", ".join(_escape(s) for s in (resume.research_interests or []))
    languages = ", ".join(
        _escape(f"{l['language']} ({l['proficiency']})") for l in (resume.languages or [])
    )

    return (
        "\\documentclass[11pt,a4paper]{article}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage[margin=0.6in]{geometry}\n"
        "\\usepackage{enumitem}\n"
        "\\usepackage{xcolor}\n"
        "\\pagestyle{empty}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\setlength{\\parskip}{0pt}\n"
        "\\begin{document}\n"
        "\\begin{center}\n"
        f"{{\\LARGE\\bfseries {name}}}\\\\[4pt]\n"
        f"{contact}\n"
        "\\end{center}\n"
        "\\section*{Professional Summary}\n"
        f"{summary}\n\n"
        "\\section*{Technical Skills}\n"
        f"{skills_block}\n\n"
        "\\section*{Professional Experience}\n"
        + "\n".join(experience_block) + "\n\n"
        + "\\section*{Education}\n"
        + "\n".join(education_block) + "\n\n"
        + "\\section*{Projects}\n"
        + "\n".join(projects_block) + "\n\n"
        + "\\section*{Research Interests}\n"
        + (research + "\n\n" if research else "")
        + "\\section*{Languages}\n"
        + languages + "\n"
        "\\end{document}\n"
    )


def build_draft_resume(ctx: PipelineContext) -> ResumeContent:
    """Construct :class:`ResumeContent` from the pipeline context.

    Used by the orchestrator just before the critic loop. Combines the
    rewritten bullets with the legacy profile's education / skills /
    languages / research interests.
    """
    profile = ctx.profile
    resume = ResumeContent(
        name=profile.name,
        contact=profile.contact,
        summary=ctx.summary or "",
        skills=_select_skills(ctx),
        experience=_build_experience_entries(ctx),
        education=[e.model_dump() for e in profile.education],
        projects=_build_project_entries(ctx),
        languages=[l.model_dump() for l in profile.languages],
        research_interests=_select_research_interests(ctx),
    )
    return resume


def _select_skills(ctx: PipelineContext) -> list[str]:
    """Pick the top skill categories by ATS keyword overlap."""
    skills_map = ctx.profile.technical_skills or {}
    if not skills_map:
        return []
    keywords = {kw.term.lower() for kw in ctx.ats_keywords}
    scored: list[tuple[float, str, list[str]]] = []
    for category, items in skills_map.items():
        score = sum(1 for s in items if any(k in s.lower() for k in keywords))
        scored.append((score, category, items))
    scored.sort(key=lambda t: t[0], reverse=True)
    label_map = {
        "programming_languages": "Programming Languages",
        "hpc_parallel": "HPC & Parallel Computing",
        "scientific_computing": "Scientific Computing",
        "machine_learning": "Machine Learning",
        "quantum_computing": "Quantum Computing",
        "software_engineering": "Software Engineering",
        "modeling_simulation": "Modeling & Simulation",
        "technical": "Technical Skills",
    }
    out: list[str] = []
    for _, cat, items in scored[:5]:
        label = label_map.get(cat, cat.replace("_", " ").title())
        out.append(f"{label}: {', '.join(items)}")
    return out


def _select_research_interests(ctx: PipelineContext) -> list[str]:
    interests = list(ctx.profile.research_interests or [])
    if not interests:
        return []
    keywords = {kw.term.lower() for kw in ctx.ats_keywords}
    scored: list[tuple[int, str]] = []
    for interest in interests:
        score = sum(1 for k in keywords if k in interest.lower())
        scored.append((score, interest))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [i for _, i in scored[:4] if _ > 0] or interests[:3]


def _experience_marker(exp) -> str | None:
    """Resolve the atom ``source_ref`` for a legacy ``ExperienceEntry``.

    Prefers the explicit ``source_ref_marker`` field added in M2; falls back
    to ``<company_slug>_<title_slug>`` for profiles that haven't been
    annotated yet.
    """
    if getattr(exp, "source_ref_marker", None):
        return exp.source_ref_marker
    return _slug(f"{exp.company}_{exp.title}")


def _build_experience_entries(ctx: PipelineContext) -> list[dict]:
    """Map the candidate's profile experience entries to use rewritten bullets where available.

    ``ctx.rewritten_bullets`` is keyed by atom ``source_ref`` (e.g.
    ``"work_no_border"``). Legacy ``ExperienceEntry`` carries an optional
    ``source_ref_marker`` that lets us look up matching rewritten bullets;
    unannotated entries fall back to the legacy ``description`` list.
    """
    out: list[dict] = []
    profile_markers: set[str] = set()
    for exp in ctx.profile.experience:
        marker = _experience_marker(exp)
        profile_markers.add(marker)
        bullets = ctx.rewritten_bullets.get(marker or "", []) if marker else []
        if not bullets:
            bullets = list(exp.description)
        out.append(
            {
                "title": exp.title,
                "company": exp.company,
                "location": exp.location or "",
                "period": exp.period,
                "description": bullets,
            }
        )
    # Synthesize entries for any rewritten_bullets keys that don't match a
    # legacy profile entry (forward-compat for new work entries).
    for source_ref, bullets in ctx.rewritten_bullets.items():
        if source_ref in profile_markers:
            continue
        out.append(
            {
                "title": source_ref.replace("_", " ").title(),
                "company": "",
                "location": "",
                "period": "",
                "description": bullets,
            }
        )
    return out


def _build_project_entries(ctx: PipelineContext) -> list[dict]:
    out: list[dict] = []
    by_name = {p.name: p for p in ctx.profile.projects}
    for source_ref, bullets in ctx.rewritten_project_bullets.items():
        # Try to find the project in the legacy profile.
        matched = None
        for name, p in by_name.items():
            if _slug(name) == _slug(source_ref):
                matched = p
                break
        if matched is not None:
            out.append({"name": matched.name, "description": bullets, "technologies": matched.technologies, "metrics": matched.metrics})
        else:
            out.append({"name": source_ref.replace("_", " ").title(), "description": bullets, "technologies": [], "metrics": []})
    if not out:
        # Fall back to the legacy projects verbatim.
        for p in ctx.profile.projects:
            out.append({"name": p.name, "description": list(p.description), "technologies": p.technologies, "metrics": p.metrics})
    return out


__all__ = ["LaTeXGenerator", "build_draft_resume"]
