"""Profile loader — single source of truth for reading ``profile/*.json``.

Replaces the duplicated loaders in ``src/main.py`` (lines 139-145) and
``src/matcher.py`` (lines 55-62). Both currently re-read the same JSON files
on every ``JobMatcher`` instantiation, which is wasteful and prone to drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from job_automation.config import PathsConfig
from job_automation.logging import get_logger
from job_automation.models.profile import Profile

logger = get_logger(__name__)

# Files we attempt to load, in merge order. Missing files are skipped with a
# warning; corrupt JSON aborts the load.
_PROFILE_FILES = (
    "master_resume.json",
    "experience.json",
    "skills.json",
    "projects.json",
)


def load_profile(paths: PathsConfig | None = None) -> Profile:
    """Read profile JSON files and return a validated :class:`Profile`.

    Files are merged into a single dict (later files override earlier ones,
    so ``projects.json`` can amend ``master_resume.json``). The dict is then
    validated by Pydantic — missing required fields raise ``ValidationError``.
    """
    if paths is None:
        from job_automation.config import load_config
        paths = load_config().paths

    profile_dir = Path(paths.profile_dir)
    merged: dict[str, object] = {}

    for filename in _PROFILE_FILES:
        file_path = profile_dir / filename
        if not file_path.exists():
            logger.warning("profile_file_missing", extra={"path": str(file_path)})
            continue
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error(
                "profile_file_invalid_json",
                extra={"path": str(file_path), "error": str(exc)},
            )
            raise
        if not isinstance(data, dict):
            logger.warning(
                "profile_file_not_object",
                extra={"path": str(file_path), "type": type(data).__name__},
            )
            continue
        merged.update(data)

    logger.info(
        "profile_loaded",
        extra={"files_merged": len(merged), "source_dir": str(profile_dir)},
    )
    return Profile.model_validate(merged)
