"""Legacy package shim.

The new installable package lives at ``src/job_automation``. This file keeps
the old ``python src/main.py`` and ``python -m unittest tests/test_automation.py``
entry points working during the M1 → M2 migration window. The import is a
one-way street — the legacy engines read from ``job_automation.config`` but
the new package does not re-export the old ``Config`` singleton.

This shim is scheduled for removal in M3 once the Celery-based entry point
becomes the canonical way to run the pipeline.
"""

from __future__ import annotations

# Re-export the legacy modules so ``from <module> import <name>`` works the
# same way it did before M1.
from job_automation import (  # noqa: F401  (re-export)
    config as _new_config,
    logging as _new_logging,
)