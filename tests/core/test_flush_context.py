"""Tests for flush_context — module-level output directory context."""

from __future__ import annotations

from scistudio.core.storage.flush_context import clear, get_output_dir, set_output_dir


class TestFlushContext:
    """flush_context module — set, get, clear."""

    def teardown_method(self) -> None:
        """Ensure context is cleared after each test."""
        clear()

    def test_default_is_none(self) -> None:
        clear()
        assert get_output_dir() is None

    def test_set_and_get(self) -> None:
        set_output_dir("/tmp/test_output")
        assert get_output_dir() == "/tmp/test_output"

    def test_clear(self) -> None:
        set_output_dir("/tmp/test_output")
        clear()
        assert get_output_dir() is None
