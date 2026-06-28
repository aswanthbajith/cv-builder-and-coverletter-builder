"""Structured logging with correlation IDs.

Design goals:

- **Stdlib only** — no new runtime dependencies. M3 (Celery) integrates via
  Celery's signal hooks that emit records into this module's handlers.
- **Correlation IDs via ``contextvars``** — works across threads (we copy the
  context at task submission) and ``asyncio`` (the same ``ContextVar``
  resolves per-task in Celery's asyncio support).
- **Idempotent configuration** — :func:`configure_logging` is safe to call
  from CLI boot, Celery worker boot, and pytest fixtures.
- **Two output formats** — JSON for production (12-factor log shipping),
  colored console for development. Selected via ``LoggingConfig.format``.
"""

from __future__ import annotations

import contextvars
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from job_automation.config import LoggingConfig

# ContextVar holding the active correlation context. Defaults to empty dict so
# `.get(None)` callers don't crash on a missing key. Read by ContextFilter.
_log_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "job_automation_log_context", default={}
)


class ContextFilter(logging.Filter):
    """Inject bound context (run_id, job_id, …) onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        for key, value in _log_context.get().items():
            # Don't clobber fields the caller already set explicitly.
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — avoids the python-json-logger dependency."""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        payload: dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _ColorFormatter(logging.Formatter):
    """ANSI-colored formatter for interactive terminals."""

    _COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[1;31m",
    }
    _RESET = "\033[0m"

    def __init__(self, colored: bool) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        self._colored = colored

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if self._colored and record.levelname in self._COLORS:
            message = (
                f"{self._COLORS[record.levelname]}{message}{self._RESET}"
            )
        # Append bound context fields inline, e.g.  [run_id=abc job_id=42]
        extras = " ".join(
            f"{k}={v}"
            for k, v in record.__dict__.items()
            if k not in self._RESERVED_LOGRECORD_ATTRS and not k.startswith("_")
        )
        if extras:
            message = f"{message} [{extras}]"
        return message

    # Attributes defined on every LogRecord — used to skip non-context fields.
    _RESERVED_LOGRECORD_ATTRS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }


_CONFIGURED = False


def configure_logging(config: LoggingConfig | None = None) -> None:
    """Install handlers for the root logger. Idempotent.

    Safe to call repeatedly — subsequent calls only adjust level and replace
    the formatter on existing handlers; they do not stack handlers.

    Implementation note: ``ContextFilter`` is attached to every **handler**,
    not to the root ``Logger``. Python's logging does not run logger-level
    filters on records that arrive via propagation — only handler-level
    filters see those records. We want the filter to run regardless of which
    sub-logger emitted the message, so we wire it on the handler.
    """
    global _CONFIGURED
    if config is None:
        # Lazy import to avoid a circular dependency at module import time.
        from job_automation.config import load_config
        config = load_config().logging

    root = logging.getLogger()
    root.setLevel(config.level)

    formatter: logging.Formatter
    if config.format == "json":
        formatter = _JsonFormatter()
    else:
        formatter = _ColorFormatter(colored=config.colored)

    # Stream handler (stdout)
    stream_handler = _ensure_handler(root, logging.StreamHandler(sys.stdout))
    stream_handler.setFormatter(formatter)
    _ensure_context_filter(stream_handler)

    # File handler (optional, only on first configuration)
    if config.file_enabled and not _CONFIGURED:
        log_path = _resolve_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        _ensure_context_filter(file_handler)
        root.addHandler(file_handler)

    _CONFIGURED = True


def _ensure_handler(
    root: logging.Logger, target: logging.Handler
) -> logging.Handler:
    """Return an existing handler of the same type, or add ``target``."""
    for handler in root.handlers:
        if type(handler) is type(target):
            return handler
    root.addHandler(target)
    return target


def _ensure_context_filter(handler: logging.Handler) -> None:
    """Attach the context filter to a handler if not already present."""
    if not any(isinstance(f, ContextFilter) for f in handler.filters):
        handler.addFilter(ContextFilter())


def _resolve_log_path() -> Path:
    """Find the log file path from the (possibly unset) config."""
    from job_automation.config import load_config
    return load_config().paths.log_file


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``job_automation`` namespace.

    All loggers in the new package should be obtained via this helper so
    they share the ``ContextFilter`` installed on the root logger.
    """
    if not name.startswith("job_automation"):
        name = f"job_automation.{name}"
    return logging.getLogger(name)


@contextmanager
def log_context(**fields: Any) -> Iterator[dict[str, Any]]:
    """Bind ``fields`` to all log records emitted inside the block.

    Example::

        with log_context(run_id="abc", job_id=42):
            logger.info("processing job")  # record has run_id=abc job_id=42

    Nested contexts inherit and override; exiting restores the previous
    binding. Implementation uses ``ContextVar`` so it propagates correctly
    to threads spawned via ``concurrent.futures`` (when using
    ``ContextVar.copy_context().run(...)``) and to asyncio tasks.
    """
    token = _log_context.set({**_log_context.get(), **fields})
    try:
        yield _log_context.get()
    finally:
        _log_context.reset(token)


__all__ = [
    "ContextFilter",
    "configure_logging",
    "get_logger",
    "log_context",
]