"""ADR-036 §3.2 — file GET/PUT endpoint test stubs.

These tests are SKELETONS. Phase 2A implementation agent (I36a) deletes
the ``xfail`` marker from each one and fills in the body. The test plan
in each docstring captures exactly what to assert.

Why xfail (not skip):
  - xfail surfaces if a test passes unexpectedly (the implementation
    arrived without anyone updating the marker), which catches drift.
  - skip is silent.
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_happy_path() -> None:
    """GET /api/projects/{id}/file?path=blocks/foo.py returns content + mtime + size.

    Implementation steps for the test (I36a):
      1. Use the existing FastAPI test client fixture.
      2. Create a project with a known root containing ``blocks/foo.py``.
      3. GET the endpoint, assert 200, response.json() has ``content``,
         ``mtime``, ``size``, ``encoding == "utf-8"``.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_404_missing() -> None:
    """GET on a non-existent path returns 404."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_403_traversal() -> None:
    """GET with path="../../etc/passwd" returns 403 (path escapes project root)."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_415_extension() -> None:
    """GET on a .exe (or any non-allowlisted extension) returns 415."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_read_file_413_size() -> None:
    """GET on a > 10 MB file returns 413."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_happy_path() -> None:
    """PUT writes content atomically and returns updated mtime + size.

    Implementation steps for the test (I36a):
      1. PUT body={"content": "print('hello')\\n"}.
      2. Assert 200, response.json() has new mtime, size == 16.
      3. Read the file off disk, assert content matches exactly.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_atomic() -> None:
    """If the write fails mid-way, the destination retains the OLD content.

    Use ``monkeypatch.setattr("os.replace", raising_replace)`` to
    simulate failure after tempfile is written but before rename.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_self_write_suppression() -> None:
    """PUT calls ``mark_self_write(target)`` BEFORE the on-disk replace.

    Install a fake watcher via ``set_active_watcher``, capture the call
    order with timestamps, assert ``mark_self_write`` happened before the
    file's mtime advanced.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_413_size() -> None:
    """PUT with content > 10 MB returns 413 BEFORE touching disk.

    Verify by checking the destination file mtime has NOT advanced after
    the rejected request.
    """
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_403_traversal() -> None:
    """PUT with traversal path returns 403 and does not create files outside root."""
    raise NotImplementedError


@pytest.mark.xfail(reason="ADR-036 skeleton — implementation phase fills this in")
def test_write_file_415_extension() -> None:
    """PUT to a .exe path returns 415."""
    raise NotImplementedError
