"""Grounding check — prevents the LLM from inventing facts.

Every LLM-generated bullet / summary / project description passes through
:func:`validate_grounding` before acceptance. The check enforces:

- Every metric (numeric + unit) in the output must appear in the source.
- Every named technology / library / tool in the output must appear in
  the source's technologies list.
- Project / employer names must match the source.

If grounding fails for >50% of bullets, the engine re-prompts the LLM with
the source text appended and a "do not invent" instruction. If grounding
fails again, the engine ships the original bullet unchanged —
truthfulness > variation.

This module is deliberately stateless and deterministic so it can be
unit-tested without mocking the LLM.
"""

from __future__ import annotations

import re
from typing import Iterable

from job_automation.logging import get_logger
from job_automation.models.atomic import AtomicExperience

logger = get_logger(__name__)

# Common units that mark a metric token.
_METRIC_UNITS = (
    "x", "%", "ms", "s", "sec", "min", "minute", "minutes",
    "hours", "hour", "days", "weeks", "months", "years",
    "MB", "GB", "TB", "KB",
    "Hz", "kHz", "MHz", "GHz", "THz",
    "V", "A", "W", "kW", "MW", "J", "kJ",
    "rpm", "fps",
    "k", "M", "B",
)

_METRIC_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:" + "|".join(re.escape(u) for u in _METRIC_UNITS) + r")\b",
    re.IGNORECASE,
)

# Simple numeric-metric pattern: any number attached to an alphabetic word
# that looks like a metric (e.g. "30k entities", "5 features per sprint").
_GENERIC_NUMBER_RE = re.compile(
    r"\b(\d+(?:\.\d+)?[kKmMbB]?)\s+([a-z][a-z\-]+)\b",
    re.IGNORECASE,
)


def _source_text(atom: AtomicExperience) -> str:
    """Concatenate every grounded field of an atom into one searchable string."""
    parts = [
        atom.title,
        atom.context,
        atom.details,
        atom.outcome,
        " ".join(atom.technologies),
        " ".join(atom.metrics),
    ]
    return " ".join(parts).lower()


def _extract_metrics(text: str) -> list[str]:
    """Extract metric-shaped substrings from the candidate output."""
    seen: list[str] = []
    for m in _METRIC_RE.finditer(text):
        seen.append(m.group(0).lower().strip())
    for m in _GENERIC_NUMBER_RE.finditer(text):
        seen.append(m.group(0).lower().strip())
    return seen


def _extract_tech_terms(text: str, known_techs: Iterable[str]) -> list[str]:
    """Find known technology names that appear in ``text``.

    Returns the list of tech terms (lowercased) that the candidate used but
    aren't in the source's allowed set.
    """
    haystack = text.lower()
    return [t.lower() for t in known_techs if t.lower() in haystack]


def validate_grounding(
    rewritten: str,
    source: AtomicExperience | Iterable[AtomicExperience],
) -> list[str]:
    """Return a list of ungrounded substrings in ``rewritten``.

    Empty list = fully grounded. Each violation is the substring that
    could not be matched to the source. Used by ``AchievementRewriter``
    to reject hallucinated content.
    """
    if isinstance(source, AtomicExperience):
        sources = [source]
    else:
        sources = list(source)

    combined_source = " ".join(_source_text(s) for s in sources)
    violations: list[str] = []

    # 1. Numeric metrics must appear in the source.
    for metric in _extract_metrics(rewritten):
        if metric not in combined_source:
            violations.append(metric)

    # 2. Technologies must appear in the source. Build the union of source
    # techs and look for any unknown term that looks like a technology
    # (capitalized, includes a hyphen, or is in the candidate's known
    # tech list). We err on the side of false positives so the LLM cannot
    # sneak in tools the candidate didn't use.
    source_techs: set[str] = set()
    for s in sources:
        source_techs.update(t.lower() for t in s.technologies)

    # Detect tokens that look like technology names in the rewritten text:
    # capitalized words or hyphenated tokens.
    candidate_terms = set()
    for tok in re.findall(r"\b[A-Z][A-Za-z0-9]*\b|\b[A-Za-z]+[-][A-Za-z0-9]+\b", rewritten):
        candidate_terms.add(tok.lower())
    for term in candidate_terms:
        # Skip if the term is in the source's techs or is a common English word.
        if term in source_techs:
            continue
        # Heuristic: only flag capitalized tokens that are not in the
        # source. We allow lowercase techs (e.g. "python") to be checked
        # explicitly via known-tech list below.
        if not _looks_like_technology(term):
            continue
        violations.append(term)

    # 3. Known-tech detection: explicitly flag any common tech name in the
    # rewrite that isn't in the source.
    for tech in _extract_tech_terms(rewritten, _COMMON_TECH_VOCAB):
        if tech not in source_techs:
            violations.append(tech)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            deduped.append(v)
    return deduped


def _looks_like_technology(token: str) -> bool:
    """Heuristic: does this lowercase token look like a technology name?"""
    # Single-letter capitals (e.g. "C", "R") are ambiguous and skipped.
    if len(token) <= 1:
        return False
    # Common English words that happen to be capitalized at sentence start.
    if token in {
        "the", "and", "for", "with", "from", "this", "that", "into",
        "using", "each", "every", "all", "any", "some", "one", "two",
        "new", "best", "first", "last", "next", "top", "low",
        "implemented", "ported", "built", "used", "achieved", "improved",
        "developed", "optimized", "created", "designed", "delivered",
        "enabled", "reduced", "increased", "supported", "deployed",
    }:
        return False
    return True


# A small list of common tech keywords. Kept short on purpose — anything
# more elaborate risks false positives on English words. Expand as needed.
_COMMON_TECH_VOCAB: tuple[str, ...] = (
    "python", "java", "javascript", "typescript", "c++", "rust", "go", "ruby",
    "numpy", "pandas", "scipy", "matplotlib", "jupyter",
    "pytorch", "tensorflow", "scikit-learn",
    "qiskit", "cirq",
    "mpi", "openmp", "cuda", "cupy", "numba",
    "docker", "kubernetes", "singularity",
    "git", "github", "gitlab",
    "aws", "azure", "gcp",
    "slurm", "hdf5",
    "react", "vue", "angular",
    "vitest", "pytest", "junit",
    "sql", "mongodb", "postgresql",
)


def grounding_failure_ratio(
    rewritten_bullets: list[str],
    sources: Iterable[AtomicExperience],
) -> float:
    """Fraction of bullets that fail grounding for at least one violation."""
    if not rewritten_bullets:
        return 0.0
    failed = 0
    for bullet in rewritten_bullets:
        if validate_grounding(bullet, sources):
            failed += 1
    return failed / len(rewritten_bullets)


__all__ = ["grounding_failure_ratio", "validate_grounding"]