"""Legacy configuration module — superseded by ``job_automation.config``.

Kept only so existing imports (``from config import config``) raise a clear
error instead of silently loading a duplicate singleton. Will be removed in
M3.
"""

raise ImportError(
    "src/config.py has been replaced by job_automation.config. "
    "Update imports to `from job_automation.config import load_config`."
)
