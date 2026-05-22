"""Behavior tests for ``ai_pty._websocket`` (issue #1432).

A single focused smoke test on the WS handler — the bulk of the
WebSocket integration coverage stays in
``tests/api/test_ai_pty.py``. This file pins ``_wait_exit_code`` so
the helper's no-impl / no-popen fallback path is unit-tested in
isolation post-split.
"""

from __future__ import annotations

from scistudio.api.routes.ai_pty.websocket import _wait_exit_code


class _StubPty:
    """Bare object that exposes neither ``_impl`` nor ``_popen``.

    The original ``ai_pty.py`` used :func:`getattr` with default
    ``None`` to handle this case so the helper never blocks. We keep
    the same shape so the split preserves the fall-back behaviour.
    """


def test_wait_exit_code_returns_minus_one_without_impl_or_popen() -> None:
    """No ``_impl`` and no ``_popen`` → ``-1`` (the sentinel)."""
    assert _wait_exit_code(_StubPty()) == -1


def test_wait_exit_code_reads_impl_exit_status() -> None:
    """When ``_impl.exitstatus`` is populated (Windows PtyProcess), return it."""

    class _ImplWithStatus:
        exitstatus = 7

    class _PtyWithImpl:
        _impl = _ImplWithStatus()

    assert _wait_exit_code(_PtyWithImpl()) == 7


def test_wait_exit_code_falls_back_to_popen_returncode() -> None:
    """POSIX path: ``Popen.returncode`` is read when ``_impl`` is missing."""

    class _PopenWithCode:
        returncode = 42

    class _PtyWithPopen:
        _popen = _PopenWithCode()

    assert _wait_exit_code(_PtyWithPopen()) == 42


def test_wait_exit_code_swallows_attribute_lookup_failures() -> None:
    """Any exception on the lookup path resolves to ``-1`` — best-effort."""

    class _Boom:
        @property
        def _impl(self) -> object:
            raise RuntimeError("attribute boom")

    assert _wait_exit_code(_Boom()) == -1
