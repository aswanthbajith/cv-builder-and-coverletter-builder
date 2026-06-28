"""Engine exceptions — typed errors raised by M2 engines.

EngineError is the umbrella type. Subclasses carry semantic meaning the
orchestrator uses to decide retry vs fall-back vs abort:

- :class:`LLMUnavailable` — Gemini rate-limited or 5xx. Retry once, then
  fall back to deterministic output.
- :class:`GroundingViolation` — The LLM output contained metrics or facts
  not present in the source profile. Reject the bullet; orchestrator may
  re-prompt.
- :class:`CriticRejected` — The ResumeCritic rejected the draft. Triggers
  a re-loop via AchievementRewriter.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for all M2 engine errors.

    Catch this in the orchestrator to handle any engine failure with a
    single except clause. Subclasses are for finer-grained control.
    """

    def __init__(self, message: str, *, engine: str | None = None) -> None:
        super().__init__(message)
        self.engine = engine


class LLMUnavailable(EngineError):
    """Raised when the LLM call fails after retries are exhausted."""


class GroundingViolation(EngineError):
    """Raised when the LLM output fails the grounding check.

    ``violations`` is the list of problematic substrings (metrics, project
    names, technologies) detected as not grounded in the source profile.
    """

    def __init__(
        self,
        message: str,
        *,
        engine: str | None = None,
        violations: list[str] | None = None,
    ) -> None:
        super().__init__(message, engine=engine)
        self.violations = list(violations or [])


class CriticRejected(EngineError):
    """Raised when the ResumeCritic returns a 'reject' verdict.

    The orchestrator catches this, decides whether to loop (if iterations
    remain), and ships a best-effort draft if iterations are exhausted.
    """


__all__ = ["CriticRejected", "EngineError", "GroundingViolation", "LLMUnavailable"]