"""Tests for :func:`scistudio.utils.logging.configure_logging` (#827).

Validates that the previous ``NotImplementedError`` stub is now a
working adapter on :func:`scistudio.utils.event_logger.install_default_handler`.
"""

from __future__ import annotations

import logging

import pytest

from scistudio.utils.logging import configure_logging


@pytest.fixture(autouse=True)
def _clean_root_handlers() -> None:
    """Snapshot + restore root handlers around each test.

    ``configure_logging`` installs a handler on the root logger when
    none are present; without this fixture a stray handler would leak
    between tests and break log capture in the rest of the suite.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    try:
        for handler in saved_handlers:
            root.removeHandler(handler)
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_configure_logging_installs_root_handler() -> None:
    """A fresh root logger gets a single ``StreamHandler`` after configure.

    pytest's log-cli plugin may already have a handler installed; clear
    them so the test exercises the "no handler present" install path.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    configure_logging("INFO")
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert root.level == logging.INFO


def test_configure_logging_accepts_integer_level() -> None:
    configure_logging(logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError):
        configure_logging("NOTREAL")


def test_configure_logging_json_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SCISTUDIO_LOG_JSON=1`` switches the formatter to JSON.

    pytest's log-cli plugin can leave its own ``ColoredLevelFormatter``
    handler attached at test entry. ``install_default_handler`` skips
    when any handler is already present, so the test removes them
    right before the call to give the JSON formatter a chance to land.
    """
    monkeypatch.setenv("SCISTUDIO_LOG_JSON", "1")

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    configure_logging("INFO")

    formatter_class_names = {h.formatter.__class__.__name__ for h in root.handlers if h.formatter is not None}
    assert "_JsonLineFormatter" in formatter_class_names


def test_configure_logging_is_idempotent_for_handlers() -> None:
    """A second call does not stack a second handler on the root logger."""
    configure_logging("INFO")
    first_count = len(logging.getLogger().handlers)
    configure_logging("INFO")
    assert len(logging.getLogger().handlers) == first_count
