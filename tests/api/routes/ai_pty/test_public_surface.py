"""Public surface preservation test for the ai_pty sub-package (issue #1432).

The original ``src/scistudio/api/routes/ai_pty.py`` (757 LOC) was split
into a sub-package as part of the backend god-file refactor (umbrella
#1427). External consumers — both production code
(``scistudio.api.app``, ``scistudio.api.ws``,
``scistudio.engine.pty_control``) and the existing tests under
``tests/api/test_ai_pty*.py`` — import symbols directly from
``scistudio.api.routes.ai_pty``. This file asserts every one of those
symbols is still resolvable on the package, so any future refactor
that removes one will fail loudly here.
"""

from __future__ import annotations

import inspect

import pytest


def test_public_router_symbols_preserved() -> None:
    """All previously-importable public symbols are still on the package.

    Sourced from a pre-refactor audit of every
    ``from scistudio.api.routes.ai_pty import ...`` statement in the
    repository (src + tests).
    """
    from scistudio.api.routes import ai_pty

    public_symbols = [
        "router",
        "MAX_ACTIVE_PTYS",
        "broadcast_ai_pty_message",
        "get_block_run_id_for_tab",
        "get_run_dir_for_block_run",
        "open_engine_initiated_tab",
        "register_ai_pty_subscriber",
        "unregister_ai_pty_subscriber",
    ]
    missing = [name for name in public_symbols if not hasattr(ai_pty, name)]
    assert not missing, f"Missing public symbols on ai_pty package: {missing}"


def test_module_private_monkeypatch_seams_preserved() -> None:
    """Mutable seams that the existing test suite monkeypatches on the package.

    These are private (leading underscore) but the test contract relies
    on them being attribute-resolvable on
    ``scistudio.api.routes.ai_pty``. Listed seams sourced from
    ``tests/api/test_ai_pty*.py`` and
    ``scistudio.api.app.lifespan``.
    """
    from scistudio.api.routes import ai_pty

    monkeypatch_seams = [
        "_spawn",  # tests/api/test_ai_pty*.py
        "_active_ptys",  # tests/api/test_ai_pty*.py
        "_active_lock",
        "_engine_tab_to_run",  # tests/api/test_ai_pty_audit_fixes.py
        "_engine_run_to_run_dir",  # tests/api/test_ai_pty_audit_fixes.py
        "_ai_pty_subscribers",
        "_ai_pty_subscribers_lock",
        "_VALID_PROVIDERS",
        "_ensure_ipc_token",  # scistudio.api.app.lifespan
    ]
    missing = [name for name in monkeypatch_seams if not hasattr(ai_pty, name)]
    assert not missing, f"Missing monkeypatch seams on ai_pty package: {missing}"


def test_router_paths_match_pre_refactor() -> None:
    """The three FastAPI route paths must remain unchanged.

    Wire-protocol freeze (ADR-034 + ADR-035 §3.10): a path change would
    break every connected frontend and every AI Block worker.
    """
    from scistudio.api.routes import ai_pty

    paths = sorted(getattr(route, "path", "") for route in ai_pty.router.routes)
    assert paths == [
        "/api/ai/pty/internal/notify",
        "/api/ai/pty/internal/request-tab",
        "/api/ai/pty/{tab_id}",
    ]


def test_spawn_signature_unchanged() -> None:
    """``_spawn`` test seam must keep the exact kwargs the fakes use.

    Tests call ``_spawn(provider=..., project_dir=..., dangerous=...,
    extra_env=...)``; a signature drift would make the fake replacement
    accept wrong arguments and mask real bugs.
    """
    from scistudio.api.routes.ai_pty import _spawn

    sig = inspect.signature(_spawn)
    assert list(sig.parameters) == ["provider", "project_dir", "dangerous", "extra_env"]
    for name in ("provider", "project_dir", "dangerous", "extra_env"):
        assert sig.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_open_engine_initiated_tab_signature_unchanged() -> None:
    """Engine-initiated tab open public signature is part of the IPC contract.

    Worker subprocesses serialise the call via the
    ``POST /api/ai/pty/internal/request-tab`` endpoint; a signature
    drift would silently corrupt the AI Block control plane.
    """
    from scistudio.api.routes.ai_pty import open_engine_initiated_tab

    sig = inspect.signature(open_engine_initiated_tab)
    assert list(sig.parameters) == [
        "title",
        "spawn_argv",
        "cwd",
        "initial_stdin",
        "block_run_id",
        "permission_mode",
        "run_dir_path",
    ]
    for name in sig.parameters:
        assert sig.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize(
    ("submodule_name", "expected_symbol"),
    [
        ("engine", "open_engine_initiated_tab"),
        ("engine", "_provider_from_argv"),
        ("internal_routes", "_ensure_ipc_token"),
        ("internal_routes", "_check_ipc_token"),
        ("subscribers", "broadcast_ai_pty_message"),
        ("validation", "_validate_project_dir"),
        ("websocket", "pty_endpoint"),
        ("websocket", "_wait_exit_code"),
        ("websocket", "_send_error"),
    ],
)
def test_sub_module_layout_resolves(submodule_name: str, expected_symbol: str) -> None:
    """Sub-module layout assertion — guards the decomposition shape.

    The refactor's intent was to keep each sub-module narrow and < 750
    LOC; downstream callers should never reach into a sub-module
    directly, but the layout itself is a contract for ongoing
    maintenance and audit. If a future change collapses everything back
    into ``__init__.py`` (defeating the decomposition), this test fails.
    """
    import importlib

    module = importlib.import_module(f"scistudio.api.routes.ai_pty.{submodule_name}")
    assert hasattr(module, expected_symbol), (
        f"Expected {expected_symbol!r} in scistudio.api.routes.ai_pty.{submodule_name}"
    )
