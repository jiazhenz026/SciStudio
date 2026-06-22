"""Tests for the unified logging base (#1741, scistudio.utils.log_setup)."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from pathlib import Path

import pytest

from scistudio.utils import log_setup
from scistudio.utils.logging import configure_logging


@pytest.fixture(autouse=True)
def _isolate_root_logging():
    """Isolate root logger handlers + level around each test.

    Removes any pre-existing handlers (e.g. a scistudio file handler installed by
    another test or an import) before the test so ``install_file_logging`` is not
    a no-op, then restores the original handlers afterward.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for handler in saved_handlers:
        root.removeHandler(handler)
    yield
    for handler in list(root.handlers):
        if handler not in saved_handlers:
            root.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()
    for handler in saved_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(saved_level)


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def test_configure_logging_writes_jsonline_file(tmp_path):
    log_file = configure_logging("DEBUG", log_dir=tmp_path, log_to_file=True)
    assert log_file is not None and Path(log_file).parent == tmp_path

    logging.getLogger("scistudio.test").info("hello world")
    for handler in logging.getLogger().handlers:
        handler.flush()

    records = _read_jsonl(Path(log_file))
    assert any(r["message"] == "hello world" and r["level"] == "info" for r in records)


def test_correlation_and_run_id_injected(tmp_path):
    log_file = configure_logging("DEBUG", log_dir=tmp_path, log_to_file=True)
    token_req = log_setup.request_id_var.set("req-123")
    token_run = log_setup.run_id_var.set("run-abc")
    try:
        logging.getLogger("scistudio.test").warning("correlated")
    finally:
        log_setup.request_id_var.reset(token_req)
        log_setup.run_id_var.reset(token_run)
    for handler in logging.getLogger().handlers:
        handler.flush()

    records = _read_jsonl(Path(log_file))
    match = [r for r in records if r["message"] == "correlated"]
    assert match and match[0]["request_id"] == "req-123" and match[0]["run_id"] == "run-abc"


def test_resolve_log_dir_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("SCISTUDIO_BUNDLED", raising=False)
    monkeypatch.delenv("SCISTUDIO_LOG_DIR", raising=False)
    # explicit wins
    assert log_setup.resolve_log_dir(log_dir=tmp_path) == tmp_path
    # env next
    monkeypatch.setenv("SCISTUDIO_LOG_DIR", str(tmp_path / "env"))
    assert log_setup.resolve_log_dir() == tmp_path / "env"
    monkeypatch.delenv("SCISTUDIO_LOG_DIR")
    # project_root next
    assert log_setup.resolve_log_dir(project_root=tmp_path) == tmp_path / ".scistudio" / "logs"


def test_prune_old_logs(tmp_path):
    old = tmp_path / "scistudio-old.log"
    new = tmp_path / "scistudio-new.log"
    old.write_text("x", encoding="utf-8")
    new.write_text("y", encoding="utf-8")
    eight_days = time.time() - 8 * 86400
    os.utime(old, (eight_days, eight_days))

    removed = log_setup.prune_old_logs(tmp_path, days=7)
    assert removed == 1
    assert not old.exists() and new.exists()


def test_redact_sensitive():
    out = log_setup.redact_sensitive(
        {"api_key": "secret", "nested": {"password": "p", "ok": 1}, "items": [{"token": "t"}]}
    )
    assert out["api_key"] == "<redacted>"
    assert out["nested"]["password"] == "<redacted>"
    assert out["nested"]["ok"] == 1
    assert out["items"][0]["token"] == "<redacted>"


def test_log_call_sync(caplog):
    @log_setup.log_call
    def add(a, b):
        return a + b

    with caplog.at_level(logging.DEBUG):
        assert add(2, 3) == 5
    messages = [r.getMessage() for r in caplog.records]
    assert any("→" in m and "add" in m for m in messages)
    assert any("← " in m and "add" in m and "ok" in m for m in messages)


def test_log_call_logs_exception(caplog):
    @log_setup.log_call
    def boom():
        raise ValueError("nope")

    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError):
        boom()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors and any("boom" in r.getMessage() for r in errors)
    assert any(r.exc_info for r in errors)


def test_log_call_async(caplog):
    import asyncio

    @log_setup.log_call
    async def afetch(x):
        return x * 2

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(afetch(21)) == 42
    messages = [r.getMessage() for r in caplog.records]
    assert any("afetch" in m and "ok" in m for m in messages)


def test_install_file_logging_idempotent(tmp_path):
    first = configure_logging("INFO", log_dir=tmp_path, log_to_file=True)
    file_handlers_before = [h for h in logging.getLogger().handlers if getattr(h, "_scistudio_file_handler", False)]
    second = log_setup.install_file_logging(level=logging.INFO, log_dir=tmp_path)
    file_handlers_after = [h for h in logging.getLogger().handlers if getattr(h, "_scistudio_file_handler", False)]
    assert len(file_handlers_before) == 1 and len(file_handlers_after) == 1
    assert Path(first) == Path(second)
