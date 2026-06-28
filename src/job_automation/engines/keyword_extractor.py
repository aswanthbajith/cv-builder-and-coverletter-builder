"""ATSKeywordExtractor — produce weighted keyword list from job + company.

Deterministic. Pulls keywords from:
- The job text (job_title, job_description, required_skills, preferred_qualifications).
- The company profile (focus_areas, technologies, terminology).
- The job analysis themes.

Weighting:
- required_skills tokens → 1.0
- job_description tokens (after stopword filter) → 0.7
- company technologies → 0.6
- company terminology → 0.5
- inferred themes → 0.4

Tokens are normalized (lowercase, deduped, stemmed-ish via simple suffix
stripping). No LLM call.
"""

from __future__ import annotations

import re
from collections import Counter

from job_automation.engines.base import PipelineContext
from job_automation.logging import get_logger
from job_automation.models.analysis import ATSKeyword

logger = get_logger(__name__)

# English stopwords short enough to keep in-code. Larger lists belong in a
# dedicated stopwords module — kept inline here for clarity.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
        "the", "to", "was", "were", "will", "with", "this", "these", "those",
        "you", "your", "we", "our", "us", "i", "me", "my", "they", "their",
        "he", "she", "his", "her", "them", "but", "if", "not", "so", "do",
        "does", "did", "doing", "would", "should", "could", "can", "may",
        "might", "must", "shall", "than", "then", "there", "here", "when",
        "where", "why", "how", "all", "any", "both", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "only", "own", "same",
        "too", "very", "just", "into", "out", "up", "down", "over", "under",
        "again", "further", "once", "also", "across", "after", "before",
        "above", "below", "between", "through", "during", "until", "while",
        "about", "against", "among", "around", "is", "are", "was", "were",
        "been", "being", "have", "has", "had", "do", "does", "did",
        "should", "would", "could", "ought", "am", "let",
    }
)

_TERM_RE = re.compile(r"[A-Za-z0-9+#./\-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TERM_RE.findall(text or "") if t]


def _bigrams(tokens: list[str]) -> list[str]:
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


class ATSKeywordExtractor:
    """Deterministic keyword extractor."""

    name = "keyword_extractor"
    timeout_s = 5.0
    requires = frozenset({"job", "job_analysis", "company_profile"})
    produces = frozenset({"ats_keywords"})

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        job = ctx.job
        company = ctx.company_profile
        analysis = ctx.job_analysis

        scored: Counter[str] = Counter()

        # required skills — highest weight.
        for tok in _tokenize(job.required_skills or ""):
            if tok in _STOPWORDS or len(tok) < 2:
                continue
            scored[tok] = max(scored[tok], 1.0)
        # Two-word phrases from required skills.
        for phrase in _bigrams(_tokenize(job.required_skills or "")):
            if all(p not in _STOPWORDS for p in phrase.split()):
                scored[phrase] = max(scored[phrase], 1.0)

        # job description — 0.7 weight, capped at 5 occurrences.
        desc_tokens = [t for t in _tokenize(job.job_description) if t not in _STOPWORDS]
        counts = Counter(desc_tokens)
        for tok, count in counts.items():
            if len(tok) < 2:
                continue
            scored[tok] = max(scored[tok], min(0.7, 0.3 + 0.1 * count))
        for phrase in _bigrams(desc_tokens):
            if all(p not in _STOPWORDS for p in phrase.split()):
                scored[phrase] = max(scored[phrase], 0.7)

        # company profile — 0.6 weight.
        if company is not None:
            for tok in company.technologies:
                for t in _tokenize(tok):
                    scored[t] = max(scored[t], 0.6)
            for tok in company.terminology:
                for t in _tokenize(tok):
                    scored[t] = max(scored[t], 0.5)

        # analysis themes — 0.4 weight.
        if analysis is not None:
            for theme in analysis.themes:
                for t in _tokenize(theme):
                    scored[t] = max(scored[t], 0.4)

        # Convert to ATSKeyword objects. Sort by weight desc.
        keywords: list[ATSKeyword] = []
        for term, weight in scored.most_common():
            if weight <= 0:
                continue
            if weight >= 0.9:
                source = "job"
            elif weight >= 0.55:
                source = "company"
            else:
                source = "inferred"
            keywords.append(ATSKeyword(term=term, weight=round(weight, 3), source=source))

        ctx.ats_keywords = keywords
        logger.info("keywords_extracted", extra={"count": len(keywords)})
        return ctx


__all__ = ["ATSKeywordExtractor"]


# Exposed constant — handy for tests to compare stopword behavior.
_TEST_STOPWORDS = _STOPWORDS
