"""Console entry point for the job-automation pipeline.

M1 ships a thin shim that delegates to the legacy ``src/main.py`` so existing
runs keep working. M3 will replace this with a real :class:`Pipeline` that
dispatches via Celery.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the legacy src/ importable from the installed entry point. This stays
# in place until M3 lands.
_LEGACY_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_LEGACY_SRC) not in sys.path:
    sys.path.insert(0, str(_LEGACY_SRC))


def main() -> int:
    """Run the legacy pipeline. Returns the process exit code."""
    from job_automation.config import load_config
    from job_automation.logging import configure_logging

    configure_logging(load_config().logging)

    # Delegate to the legacy script's main(). Importing at call time so that
    # pytest --collect-only doesn't pull it in.
    from main import main as legacy_main  # type: ignore[import-not-found]

    return int(legacy_main() or 0)


if __name__ == "__main__":
    sys.exit(main())