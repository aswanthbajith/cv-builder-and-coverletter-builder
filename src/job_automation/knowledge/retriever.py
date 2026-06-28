"""Retrieval over the knowledge graph.

The retriever returns :class:`ScoredExperience` lists ranked by a combined
score that mixes semantic similarity, keyword overlap, and role-family
match. The job analyzer and experience selector consume this output.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Iterable

from job_automation.logging import get_logger
from job_automation.models.atomic import (
    AtomicExperience,
    RewriteHint,
    RoleFamily,
    ScoredExperience,
)
from job_automation.models.job import Job

if TYPE_CHECKING:
    from job_automation.knowledge.graph import KnowledgeGraph

logger = get_logger(__name__)

# Role-family adjacency matrix for partial-match scoring.
# Pairs get 0.5 instead of 0 when neither tag matches directly.
_ADJACENT_FAMILIES: dict[RoleFamily, frozenset[RoleFamily]] = {
    "hpc": frozenset({"quantum", "data", "software"}),
    "quantum": frozenset({"hpc", "research"}),
    "software": frozenset({"data", "general"}),
    "research": frozenset({"quantum", "general"}),
    "data": frozenset({"hpc", "software"}),
    "mechanical": frozenset({"research", "general"}),
    "general": frozenset({"software", "research"}),
}

# Role-archetype detection keywords (deterministic, pre-LLM).
# Used by ``detect_role_family`` as a fast path before any LLM call.
_ROLE_KEYWORDS: dict[RoleFamily, tuple[str, ...]] = {
    "hpc": ("hpc", "high performance", "mpi", "openmp", "cuda", "gpu", "cluster", "slurm"),
    "quantum": ("quantum", "qiskit", "cirq", "vqe", "qaoa", "quantum algorithm"),
    "software": ("software engineer", "backend", "frontend", "full stack", "developer", "devops"),
    "research": ("research", "thesis", "publication", "phd", "doctoral", "research engineer"),
    "data": ("data scientist", "data engineer", "machine learning", "ml engineer", "analytics"),
    "mechanical": ("mechanical", "thermal", "cfd", "fea", "battery", "fluid dynamics", "ansys"),
}


def detect_role_family(job: Job) -> RoleFamily:
    """Heuristically classify a job into a :class:`RoleFamily`.

    Returns the family with the highest keyword count in the job text,
    falling back to ``"general"`` on ties or zero matches. Deterministic;
    does not call the LLM. Used as a fast path before LLM-based analysis.
    """
    haystack = " ".join(
        [
            job.job_title,
            job.job_description,
            job.required_skills or "",
            job.preferred_qualifications or "",
        ]
    ).lower()

    counts: Counter[RoleFamily] = Counter()
    for family, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw in haystack:
                counts[family] += 1

    if not counts:
        return "general"
    top = counts.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return "general"
    return top[0][0]


def _normalize(text: str) -> set[str]:
    """Tokenize and lowercase a string into a set of word tokens."""
    return {tok for tok in re.findall(r"[a-z0-9+#./\-]+", text.lower()) if len(tok) > 1}


def _keyword_overlap_score(atom: AtomicExperience, query_tokens: set[str]) -> float:
    """Jaccard-style overlap of atom tech/skills/metrics vs query tokens."""
    atom_tokens: set[str] = set()
    for tech in atom.technologies:
        atom_tokens.update(_normalize(tech))
    for skill in atom.skills:
        atom_tokens.update(_normalize(skill))
    for metric in atom.metrics:
        atom_tokens.update(_normalize(metric))
    atom_tokens.update(_normalize(atom.title))
    atom_tokens.update(_normalize(atom.context))
    atom_tokens.update(_normalize(atom.details))
    atom_tokens.update(_normalize(atom.outcome))
    if not atom_tokens or not query_tokens:
        return 0.0
    overlap = atom_tokens & query_tokens
    return min(1.0, len(overlap) / max(8, len(atom_tokens) ** 0.5))


def _role_family_score(atom: AtomicExperience, detected: RoleFamily) -> float:
    """1.0 for direct match, 0.5 for adjacent family, 0.0 otherwise."""
    if detected in atom.role_family_tags:
        return 1.0
    if detected in _ADJACENT_FAMILIES and _ADJACENT_FAMILIES[detected] & set(atom.role_family_tags):
        return 0.5
    return 0.0


def _recency_bonus(atom: AtomicExperience) -> float:
    """+0.05 if the atom has an ``end`` within the last 24 months from 2026-06-28."""
    if atom.end is None:
        return 0.0
    # Anchor date matches the plan's example cutoff; future-tense skills
    # without an end get no bonus. The 24-month window keeps it generous.
    anchor_year = 2026
    months = (anchor_year - atom.end.year) * 12 + (6 - atom.end.month)
    if months <= 24:
        return 0.05
    return 0.0


def find_relevant_experiences(
    job: Job,
    graph: "KnowledgeGraph",
    *,
    top_k: int = 12,
    role_family: RoleFamily | None = None,
    query_text: str | None = None,
) -> list[ScoredExperience]:
    """Return the ``top_k`` most relevant atoms for ``job``.

    Scoring (per the M2 plan):
        final = 0.45 * semantic
              + 0.35 * keyword
              + 0.20 * role_family
              + recency_bonus   (≤ 0.05)
              + skill_overlap_bonus (≤ 0.10)

    If no embedding index is attached to ``graph``, semantic scores fall back
    to 0 — keyword + role-family still produce a useful ranking.
    """
    detected = role_family or detect_role_family(job)
    text_query = query_text or " ".join(
        [
            job.job_title,
            job.job_description,
            job.required_skills or "",
            job.preferred_qualifications or "",
        ]
    )
    query_tokens = _normalize(text_query)

    # Semantic: ask the FAISS index for the top 50 nearest atoms to the
    # job text. We rerank below with keyword + role-family.
    semantic_scores: dict[str, float] = {}
    if graph.embedding_index is not None:
        for exp_id, sim in graph.embedding_index.search(text_query, top_k=50):
            # Cosine is in [-1, 1]; clamp to [0, 1] for blending.
            semantic_scores[exp_id] = max(0.0, min(1.0, sim))

    scored: list[ScoredExperience] = []
    for atom in graph.experiences:
        sem = semantic_scores.get(atom.id, 0.0)
        kw = _keyword_overlap_score(atom, query_tokens)
        rf = _role_family_score(atom, detected)
        recency = _recency_bonus(atom)
        # Bonus for direct skill match — count atoms whose technologies
        # overlap with the job's required skills (capped at 0.10).
        required_tokens = _normalize(job.required_skills or "")
        if required_tokens:
            tech_tokens: set[str] = set()
            for tech in atom.technologies:
                tech_tokens.update(_normalize(tech))
            skill_overlap = len(tech_tokens & required_tokens)
            skill_bonus = min(0.10, 0.05 * skill_overlap)
        else:
            skill_bonus = 0.0

        final = 0.45 * sem + 0.35 * kw + 0.20 * rf + recency + skill_bonus
        rewrite = atom.rewrites.get(detected) if detected in atom.rewrites else None
        if rewrite is not None and rewrite.drop:
            # Skip atoms explicitly dropped for this family.
            continue
        scored.append(
            ScoredExperience(
                experience=atom,
                score=round(min(1.0, final), 4),
                keyword_score=round(kw, 4),
                semantic_score=round(sem, 4),
                role_family_score=round(rf, 4),
                rewrite=rewrite,
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_k]


def group_by_source_ref(scored: Iterable[ScoredExperience]) -> dict[str, list[ScoredExperience]]:
    """Group scored atoms by their parent source (project / employer).

    Used by ``ExperienceSelector`` to bundle atoms belonging to the same
    source ``ExperienceEntry`` / ``ProjectEntry`` for resume rendering.
    """
    grouped: dict[str, list[ScoredExperience]] = {}
    for s in scored:
        grouped.setdefault(s.experience.source_ref, []).append(s)
    return grouped


__all__ = [
    "detect_role_family",
    "find_relevant_experiences",
    "group_by_source_ref",
]