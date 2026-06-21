"""Tests for per-run diagnostic logging (#1741, scistudio.engine.run_logging)."""

from __future__ import annotations

import contextlib
import json
import logging

import pytest

from scistudio.engine import run_logging
from scistudio.engine.run_logging import _RunFilter, run_log_context


@pytest.fixture(autouse=True)
def _isolate_root_logging():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.setLevel(logging.DEBUG)
    yield
    for handler in list(root.handlers):
        if handler not in saved_handlers:
            root.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()
    root.setLevel(saved_level)


def test_run_log_context_captures_records(tmp_path):
    with run_log_context("run-xyz", project_root=tmp_path) as path:
        assert path is not None
        logging.getLogger("scistudio.engine.test").info("inside the run")
        logging.getLogger("scistudio.engine.test").error("a failure", exc_info=False)

    text = path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    messages = {r["message"]: r for r in records}
    assert "inside the run" in messages
    assert messages["inside the run"]["run_id"] == "run-xyz"
    assert "a failure" in messages


def test_run_log_file_under_project_logs_dir(tmp_path):
    with run_log_context("run-1", project_root=tmp_path) as path:
        pass
    assert path.parent == tmp_path / ".scistudio" / "logs"
    assert path.name == "run-run-1.log"


def test_run_filter_matches_only_its_run():
    run_filter = _RunFilter("run-a")
    rec_a = logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None)
    rec_a.run_id = "run-a"
    rec_b = logging.LogRecord("x", logging.INFO, "f", 1, "m", None, None)
    rec_b.run_id = "run-b"
    assert run_filter.filter(rec_a) is True
    assert run_filter.filter(rec_b) is False


def test_run_id_unsafe_chars_sanitized(tmp_path):
    with run_log_context("../evil id", project_root=tmp_path) as path:
        pass
    assert path.parent == tmp_path / ".scistudio" / "logs"
    assert "/" not in path.name and path.name.startswith("run-")


def test_handler_detached_after_context(tmp_path):
    before = len(logging.getLogger().handlers)
    with run_log_context("run-q", project_root=tmp_path):
        during = len(logging.getLogger().handlers)
    after = len(logging.getLogger().handlers)
    assert during == before + 1
    assert after == before
    assert run_logging.run_id_var.get() is None
