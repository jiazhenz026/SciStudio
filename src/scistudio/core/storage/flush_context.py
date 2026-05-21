"""Flush context -- module-level storage for auto-flush output directory.

Used by subprocess workers (single-threaded) to provide the output directory
to Block._auto_flush() without passing it through the call stack.
"""

from __future__ import annotations

_output_dir: str | None = None


def set_output_dir(path: str) -> None:
    """Set the output directory for auto-flush persistence."""
    global _output_dir
    _output_dir = path


def get_output_dir() -> str | None:
    """Return the current output directory, or None if not set."""
    return _output_dir


def clear() -> None:
    """Reset the output directory to None."""
    global _output_dir
    _output_dir = None
