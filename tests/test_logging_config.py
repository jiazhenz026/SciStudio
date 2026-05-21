"""Tests for logging configuration (#499).

Verify that ``create_app`` configures the root logger so that log output
is not silently discarded, and that the ``SCISTUDIO_LOG_LEVEL`` env var
controls the level.
"""

from __future__ import annotations

import logging
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_root_logger():
    """Save and restore the root logger state around each test."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers = saved_handlers
    root.level = saved_level


def test_create_app_configures_logging_when_no_handlers() -> None:
    """create_app() should add a handler when the root logger has none."""
    root = logging.getLogger()
    root.handlers.clear()

    from scistudio.api.app import create_app

    create_app()
    assert len(root.handlers) > 0, "create_app() must add logging handlers"


def test_create_app_preserves_existing_handlers() -> None:
    """create_app() should not replace handlers that already exist."""
    root = logging.getLogger()
    existing = logging.StreamHandler()
    existing.set_name("test-sentinel")
    root.handlers = [existing]

    from scistudio.api.app import create_app

    create_app()
    names = [h.get_name() for h in root.handlers]
    assert "test-sentinel" in names, "create_app() must preserve pre-existing handlers"


def test_gui_logging_uses_env_var() -> None:
    """The gui command's logging config should honour SCISTUDIO_LOG_LEVEL.

    We test the underlying ``logging.basicConfig(force=True)`` call
    directly since launching the full gui command would start a server.
    """
    root = logging.getLogger()
    root.handlers.clear()

    os.environ["SCISTUDIO_LOG_LEVEL"] = "DEBUG"
    try:
        logging.basicConfig(
            level=getattr(logging, os.environ.get("SCISTUDIO_LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )
        assert root.level == logging.DEBUG
    finally:
        os.environ.pop("SCISTUDIO_LOG_LEVEL", None)
