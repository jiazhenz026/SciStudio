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
    """Mutable seams resolvable on the package.

    These are private (leading underscore) but the public-surface contract
    relies on them being attribute-resolvable on
    ``scistudio.api.routes.ai_pty`` (external readers + ``app.lifespan``).
    Round-4 no-cycles moved their *definitions* into the ``_state`` leaf;
    they are re-exported here, so they stay resolvable on the package. Note
    the test suite now *patches* them on ``ai_pty._state`` (see
    ``test_seams_resolve_to_state_leaf``), because that is where the route
    handlers read them at call time.
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


def test_seams_resolve_to_state_leaf() -> None:
    """Round-4 no-cycles: shared seams live in the ``_state`` leaf.

    The sub-modules used to read the shared state / ``_spawn`` seam back
    through ``from scistudio.api.routes import ai_pty as _pkg`` (a
    child -> parent import that closed an at-import cycle around the package
    facade). They now read the ``_state`` leaf instead. This test locks that:

    * the package re-exports are the *same objects* as the leaf's, so the
      public surface and in-place mutations are unaffected; and
    * no sub-module imports the package back as ``_pkg`` (the cycle edge).
    """
    import ast
    import importlib
    import pkgutil

    from scistudio.api.routes import ai_pty
    from scistudio.api.routes.ai_pty import _state

    # Re-export identity: patching/mutating either side is equivalent.
    for name in ("_spawn", "router", "_active_ptys", "_engine_tab_to_run", "MAX_ACTIVE_PTYS"):
        assert getattr(ai_pty, name) is getattr(_state, name), name

    # No sub-module re-introduces the child -> parent cycle edge. Use AST so a
    # docstring mentioning the old pattern does not trip the check.
    for mod_info in pkgutil.iter_modules(ai_pty.__path__):
        module = importlib.import_module(f"scistudio.api.routes.ai_pty.{mod_info.name}")
        tree = ast.parse(inspect.getsource(module))
        imports_package = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "scistudio.api.routes"
            and any(alias.name == "ai_pty" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not imports_package, f"{mod_info.name} imports the package back (re-introduces the cycle)"


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
    cols=..., rows=..., extra_env=..., prompt=...)``; a signature drift would
    make the fake replacement accept wrong arguments and mask real bugs.
    ``prompt`` was added in #1789 to deliver the AI Block prompt as a CLI arg.
    """
    from scistudio.api.routes.ai_pty import _spawn

    sig = inspect.signature(_spawn)
    assert list(sig.parameters) == [
        "provider",
        "project_dir",
        "dangerous",
        "cols",
        "rows",
        "extra_env",
        "prompt",
    ]
    for name in ("provider", "project_dir", "dangerous", "cols", "rows", "extra_env", "prompt"):
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
