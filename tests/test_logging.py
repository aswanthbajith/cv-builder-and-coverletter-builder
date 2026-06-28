"""Logging tests — context filter, JSON formatter, idempotence."""

from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from job_automation.config import LoggingConfig
from job_automation.logging import (
    configure_logging,
    get_logger,
    log_context,
)


@pytest.fixture
def captured() -> StringIO:
    return StringIO()


@pytest.fixture
def attached_stream(captured: StringIO):
    """Attach a fresh stream handler with the ContextFilter.

    The fixture deliberately bypasses :func:`configure_logging` so test runs
    don't pollute the global root logger. Mirrors the production handler
    setup closely enough to exercise the filter + formatter interaction.
    """
    from job_automation.logging import ContextFilter, _ColorFormatter

    handler = logging.StreamHandler(captured)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_ColorFormatter(colored=False))
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    yield handler, captured
    root.removeHandler(handler)
    root.setLevel(old_level)


class TestLogContext:
    def test_context_attached_to_records(
        self, attached_stream: tuple[logging.Handler, StringIO]
    ) -> None:
        _, buf = attached_stream
        log = get_logger("ctx_test")

        # Without context — no extras.
        log.info("bare")
        # With context.
        with log_context(run_id="abc", job_id=42):
            log.info("scoped")

        out = buf.getvalue()
        assert "bare" in out
        assert "scoped" in out
        assert "run_id=abc" in out
        assert "job_id=42" in out
        assert "run_id" not in out.split("bare")[1].split("\n")[0]

    def test_nested_context(self, attached_stream) -> None:
        _, buf = attached_stream
        log = get_logger("nested_test")
        with log_context(run_id="outer"), log_context(job_id=42):
            log.info("inside")
        line = buf.getvalue().splitlines()[-1]
        assert "run_id=outer" in line
        assert "job_id=42" in line

    def test_context_restored_on_exit(self) -> None:
        with log_context(run_id="x"):
            pass
        # After exit, context is empty — just smoke-check no exception.


class TestJsonFormatter:
    def test_json_output_parses(self) -> None:
        # Use a private handler construction for the unit test.
        from job_automation.logging import _JsonFormatter

        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        record.run_id = "abc"
        out = _JsonFormatter().format(record)
        parsed = json.loads(out)
        assert parsed["message"] == "hello world"
        assert parsed["run_id"] == "abc"
        assert parsed["level"] == "INFO"


class TestConfigureLogging:
    def test_idempotent_does_not_stack_handlers(self) -> None:
        """Calling configure_logging repeatedly doesn't double-stack handlers.

        We count StreamHandler instances (one StreamHandler per type per root).
        If configure_logging were not idempotent, the count would grow.
        """

        root = logging.getLogger()

        def _count_stream_handlers() -> int:
            return sum(1 for h in root.handlers if isinstance(h, logging.StreamHandler))

        baseline = _count_stream_handlers()
        configure_logging(LoggingConfig(file_enabled=False))
        after_first = _count_stream_handlers()
        configure_logging(LoggingConfig(file_enabled=False))
        after_second = _count_stream_handlers()
        configure_logging(LoggingConfig(file_enabled=False))
        after_third = _count_stream_handlers()
        # configure_logging may have added at most one StreamHandler.
        assert after_first - baseline <= 1
        # And it must not have added any more on subsequent calls.
        assert after_second == after_first
        assert after_third == after_first

    def test_get_logger_namespaces(self) -> None:
        log = get_logger("foo")
        assert log.name == "job_automation.foo"
        log2 = get_logger("job_automation.foo")
        assert log2.name == "job_automation.foo"
        assert log is log2
