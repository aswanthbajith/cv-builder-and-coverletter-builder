"""Atomic experience model — one specific thing the candidate did.

Each ``AtomicExperience`` is a reusable building block the resume-construction
pipeline retrieves, scores, and rewrites per job. Tagged with the role
families (``RoleFamily``) it can credibly fit; optional ``RewriteHint`` per
family provides role-specific phrasing so the LLM rewriter can vary bullets
across roles without inventing content.

This module is part of the M2 rebuild. It is additive: the legacy
``src/job_automation/models/profile.py`` models are unchanged.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

# Role families — used for retrieval scoring and bullet rewriting.
# Adjacency: hpc <-> quantum, software <-> data.
RoleFamily = Literal[
    "hpc",
    "quantum",
    "software",
    "research",
    "data",
    "mechanical",
    "general",
]

# Where the atom comes from. Drives grouping on the rendered resume
# (e.g. all atoms with source="work" and source_ref="no_border" collapse
# into one "Working Student at No Border" entry).
AtomSource = Literal[
    "project",
    "work",
    "coursework",
    "research",
    "publication",
    "achievement",
]

# Per M2 plan: "junior", "mid", "senior", "research". Junior is the default
# for student work; "research" is reserved for publication-grade work.
Seniority = Literal["junior", "mid", "senior", "research"]


class RewriteHint(BaseModel):
    """Role-family-specific phrasing override for an atomic experience.

    Used by ``AchievementRewriter`` to vary bullets across role families
    without fabricating content. If ``drop=True`` the atom is suppressed
    entirely for that family (e.g. battery thermal work is dropped for
    quantum-research roles).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    emphasis: str = Field(
        description="1-sentence rewrite leading with this role family's angle.",
    )
    lead_phrase: str | None = Field(
        default=None,
        description="Optional opening clause to prepend; if set, replaces the bullet's lead.",
    )
    drop: bool = Field(
        default=False,
        description="If True, suppress this atom for this role family.",
    )


class AtomicExperience(BaseModel):
    """One atomic experience — the smallest reusable unit of the candidate's
    career used by the resume-construction pipeline.

    The fields are deliberately rich: a rewriter with grounding check can
    only build a non-hallucinated bullet if the source text is dense enough
    that *every* plausible rewording maps back to a field here.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    # Identity
    id: str = Field(
        description="Stable slug, e.g. 'proj_lsim_vectorize_001'. Used as FK and dedup key.",
    )
    source: AtomSource
    source_ref: str = Field(
        description="FK to parent: project slug for source='project', "
        "employer slug for source='work', course slug for source='coursework', etc.",
    )

    # Body — every field is grounded. Do not include metrics or tech that
    # the candidate did not actually use; the grounding check rejects them.
    title: str = Field(description="Short label, 3–7 words.")
    action_verb: str = Field(description="Canonical verb: Implemented, Benchmarked, …")
    context: str = Field(description="1 sentence, ~20–40 words.")
    details: str = Field(description="1–3 sentences, technical specifics.")
    outcome: str = Field(description="1 sentence with metric when possible.")

    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(
        default_factory=list,
        description="Abstract competencies (parallel computing, technical writing, …).",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description='Extracted numerics, e.g. "30k entities", "4.2x speedup".',
    )
    domain_tags: list[str] = Field(
        default_factory=list,
        description="Content domains: HPC, Quantum, CFD, Battery, Thermal, …",
    )
    role_family_tags: list[RoleFamily] = Field(
        default_factory=list,
        description="Which role families this atom credibly fits.",
    )

    # Provenance
    seniority: Seniority = "junior"
    start: date | None = None
    end: date | None = None

    # Family-specific phrasing overrides. Empty dict means "no override".
    rewrites: dict[RoleFamily, RewriteHint] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embedding_text(self) -> str:
        """Concatenated string used for embedding-based retrieval.

        Stable across model versions — only the *content* changes when an
        atom is edited, not the schema. Keep this format identical across
        all atoms so cosine similarity is meaningful.
        """
        return (
            f"{self.action_verb} {self.title}. "
            f"{self.context} {self.details} {self.outcome}"
        )


class ScoredExperience(BaseModel):
    """An atomic experience with retrieval scores attached.

    Returned by ``KnowledgeRetriever.find_relevant_experiences``. The
    downstream engines consume ``experience`` and ``rewrite``; the score
    breakdown is logged for debugging and A/B comparison.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    experience: AtomicExperience
    score: float = Field(ge=0.0, le=1.0)
    keyword_score: float = Field(ge=0.0, le=1.0)
    semantic_score: float = Field(ge=0.0, le=1.0)
    role_family_score: float = Field(ge=0.0, le=1.0)
    rewrite: RewriteHint | None = Field(
        default=None,
        description="Selected rewrite hint for the matched role family, if any.",
    )


__all__ = [
    "AtomSource",
    "AtomicExperience",
    "RewriteHint",
    "RoleFamily",
    "ScoredExperience",
    "Seniority",
]
