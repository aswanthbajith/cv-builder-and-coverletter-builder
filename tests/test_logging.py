"""Logging tests — context filter, JSON formatter, idempotence."""

from __future__ import annotations

import json
import logging
import re
from io import StringIO

import pytest

from job_automation.logging import (
    configure_logging,
    get_logger,
    log_context,
)
from job_automation.config import LoggingConfig


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
        handler, buf = attached_stream
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
        with log_context(run_id="outer"):
            with log_context(job_id=42):
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
        cfg = LoggingConfig(level="DEBUG", format="json", file_enabled=False)
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
    def test_idempotent(
        self,
        attached_stream: tuple[logging.Handler, StringIO],
    ) -> None:
        """Calling configure_logging twice doesn't double-stack handlers."""
        root = logging.getLogger()
        before = len(root.handlers)
        configure_logging(LoggingConfig(file_enabled=False))
        after = len(root.handlers)
        configure_logging(LoggingConfig(file_enabled=False))
        assert after == before + 1  # first call adds the stream handler
        # Second call must not add another.
        configure_logging(LoggingConfig(file_enabled=False))
        assert len(root.handlers) == after

    def test_get_logger_namespaces(self) -> None:
        log = get_logger("foo")
        assert log.name == "job_automation.foo"
        log2 = get_logger("job_automation.foo")
        assert log2.name == "job_automation.foo"
        assert log is log2