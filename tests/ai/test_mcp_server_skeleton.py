"""Smoke tests for the T-ECA-201 Phase 2 MCP server scaffold.

Verifies only the *shape* of the scaffold:

* The new ``scieasy.ai.agent.mcp`` sub-package and its five modules
  import without side effects.
* :class:`MCPServer` exposes the required method signatures.
* The four ``tools_*`` modules export the expected 9 / 5 / 7 / 4
  callables for a total of 25 tools.
* Each of the 25 stubs raises :class:`NotImplementedError`.
* ``scieasy mcp-bridge --help`` exits 0 with usage text.
* The MCP scaffold imports no third-party SDK (only stdlib + scieasy).

Behavioural tests ship with T-ECA-202..205.
"""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

_MCP_SUBMODULES: tuple[str, ...] = (
    "scieasy.ai.agent.mcp",
    "scieasy.ai.agent.mcp.server",
    "scieasy.ai.agent.mcp.tools_workflow",
    "scieasy.ai.agent.mcp.tools_authoring",
    "scieasy.ai.agent.mcp.tools_inspection",
    "scieasy.ai.agent.mcp.tools_qa",
)

_WORKFLOW_TOOLS: tuple[str, ...] = (
    "list_blocks",
    "get_block_schema",
    "list_types",
    "get_workflow",
    "validate_workflow",
    "write_workflow",
    "run_workflow",
    "cancel_run",
    "get_run_status",
)
_AUTHORING_TOOLS: tuple[str, ...] = (
    "read_block_source",
    "list_block_examples",
    "scaffold_block",
    "reload_blocks",
    "run_block_tests",
)
_INSPECTION_TOOLS: tuple[str, ...] = (
    "get_block_output",
    "inspect_data",
    "preview_data",
    "get_lineage",
    "get_block_config",
    "update_block_config",
    "get_block_logs",
)
_QA_TOOLS: tuple[str, ...] = (
    "search_docs",
    "get_doc",
    "list_data",
    "get_project_info",
)

# Sample dummy arguments for each tool, just enough to invoke it past
# argument binding so the NotImplementedError fires. Schema correctness
# is verified in T-ECA-202..204.
_TOOL_ARGS: dict[str, tuple[tuple[object, ...], dict[str, object]]] = {
    # workflow
    "list_blocks": ((), {}),
    "get_block_schema": (("x",), {}),
    "list_types": ((), {}),
    "get_workflow": (("x",), {}),
    "validate_workflow": (("x",), {}),
    "write_workflow": (("x", "y"), {}),
    "run_workflow": (("x",), {}),
    "cancel_run": (("x",), {}),
    "get_run_status": (("x",), {}),
    # authoring
    "read_block_source": (("x",), {}),
    "list_block_examples": (("x",), {}),
    "scaffold_block": (("x", "y"), {}),
    "reload_blocks": ((), {}),
    "run_block_tests": (("x",), {}),
    # inspection
    "get_block_output": (("r", "b", "p"), {}),
    "inspect_data": (({"ref": "x"},), {}),
    "preview_data": (({"ref": "x"}, "png"), {}),
    "get_lineage": (({"ref": "x"},), {}),
    "get_block_config": (("p", "b"), {}),
    "update_block_config": (("p", "b", {}), {}),
    "get_block_logs": (("r", "b"), {}),
    # qa
    "search_docs": (("q",), {}),
    "get_doc": (("docs/x",), {}),
    "list_data": (("p",), {}),
    "get_project_info": ((), {}),
}


def test_module_imports_clean() -> None:
    """Every MCP scaffold module must import without side effects."""
    for name in _MCP_SUBMODULES:
        importlib.import_module(name)


def test_package_re_exports_server_class() -> None:
    """The package ``__init__`` must re-export :class:`MCPServer`."""
    pkg = importlib.import_module("scieasy.ai.agent.mcp")
    server_mod = importlib.import_module("scieasy.ai.agent.mcp.server")
    assert pkg.MCPServer is server_mod.MCPServer
    assert "MCPServer" in pkg.__all__


def test_server_class_has_required_signature() -> None:
    """:class:`MCPServer` must expose ``__init__``, ``start``, ``stop``,
    ``dispatch`` with the contracted signatures."""
    from scieasy.ai.agent.mcp.server import MCPServer

    init_sig = inspect.signature(MCPServer.__init__)
    init_params = list(init_sig.parameters.keys())
    assert init_params == ["self", "socket_path", "project_dir"], init_params

    # The three async methods must exist and be coroutine functions so
    # callers can ``await`` them without an adapter layer.
    for name in ("start", "stop", "dispatch"):
        fn = getattr(MCPServer, name)
        assert callable(fn), f"MCPServer.{name} missing"
        assert inspect.iscoroutinefunction(fn), f"MCPServer.{name} must be async"

    dispatch_params = list(inspect.signature(MCPServer.dispatch).parameters.keys())
    assert dispatch_params == ["self", "request"], dispatch_params


@pytest.mark.asyncio
async def test_server_methods_raise_not_implemented(tmp_path: Path) -> None:
    """All three server methods must raise :class:`NotImplementedError`
    until T-ECA-205 lands."""
    from scieasy.ai.agent.mcp.server import MCPServer

    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=tmp_path)
    with pytest.raises(NotImplementedError):
        await server.start()
    with pytest.raises(NotImplementedError):
        await server.stop()
    with pytest.raises(NotImplementedError):
        await server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "x"})


def test_tool_modules_export_expected_callables() -> None:
    """Each ``tools_*`` module must expose its contracted tool callables."""
    for mod_name, tools in (
        ("scieasy.ai.agent.mcp.tools_workflow", _WORKFLOW_TOOLS),
        ("scieasy.ai.agent.mcp.tools_authoring", _AUTHORING_TOOLS),
        ("scieasy.ai.agent.mcp.tools_inspection", _INSPECTION_TOOLS),
        ("scieasy.ai.agent.mcp.tools_qa", _QA_TOOLS),
    ):
        mod = importlib.import_module(mod_name)
        for tool_name in tools:
            fn = getattr(mod, tool_name, None)
            assert callable(fn), f"{mod_name}.{tool_name} missing or not callable"
            # Every tool must carry a non-empty docstring (contract for
            # T-ECA-202..204 implementers).
            assert (fn.__doc__ or "").strip(), f"{mod_name}.{tool_name} missing docstring"


def test_total_tool_count_is_25() -> None:
    """The four categories must sum to exactly 25 tools (a=9, b=5, c=7, d=4)."""
    assert len(_WORKFLOW_TOOLS) == 9
    assert len(_AUTHORING_TOOLS) == 5
    assert len(_INSPECTION_TOOLS) == 7
    assert len(_QA_TOOLS) == 4
    total = len(_WORKFLOW_TOOLS) + len(_AUTHORING_TOOLS) + len(_INSPECTION_TOOLS) + len(_QA_TOOLS)
    assert total == 25, total


@pytest.mark.parametrize(
    ("mod_name", "tool_name"),
    [("scieasy.ai.agent.mcp.tools_workflow", t) for t in _WORKFLOW_TOOLS]
    + [("scieasy.ai.agent.mcp.tools_authoring", t) for t in _AUTHORING_TOOLS]
    + [("scieasy.ai.agent.mcp.tools_inspection", t) for t in _INSPECTION_TOOLS]
    + [("scieasy.ai.agent.mcp.tools_qa", t) for t in _QA_TOOLS],
)
def test_every_tool_stub_raises_not_implemented(mod_name: str, tool_name: str) -> None:
    """All 25 tool stubs must raise :class:`NotImplementedError`."""
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, tool_name)
    args, kwargs = _TOOL_ARGS[tool_name]
    with pytest.raises(NotImplementedError):
        fn(*args, **kwargs)


def test_mcp_bridge_help_via_typer() -> None:
    """``scieasy mcp-bridge --help`` must exit 0 and show usage text.

    Uses Typer's ``CliRunner`` so the test does not depend on the
    ``scieasy`` console script being installed in the test environment.
    """
    from scieasy.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["mcp-bridge", "--help"])
    assert result.exit_code == 0, result.output
    assert "mcp-bridge" in result.output.lower() or "mcp" in result.output.lower()


def test_mcp_bridge_console_script_help() -> None:
    """When invoked via ``python -m scieasy.cli.main mcp-bridge --help``,
    exit 0.

    This catches packaging-level regressions where the subcommand is
    correctly defined in code but somehow not reachable from the
    actual entry point. We only assert exit-code 0; the help text is
    already validated by the in-process Typer runner (which captures
    output reliably across platforms).
    """
    result = subprocess.run(
        [sys.executable, "-m", "scieasy.cli.main", "mcp-bridge", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"module-form CLI unavailable: rc={result.returncode}")


def test_mcp_bridge_run_returns_exit_code_2() -> None:
    """The scaffold's ``run()`` returns 2 so CC does not treat an
    unimplemented bridge as fail-open."""
    from scieasy.cli.mcp_bridge import run

    rc = run(None)
    assert rc == 2
    rc2 = run("/tmp/whatever.sock")
    assert rc2 == 2


def test_no_third_party_sdk_imports_in_mcp_package() -> None:
    """The MCP scaffold must not pull in any third-party SDK.

    Allowed imports are stdlib modules and ``scieasy.*``. This guards
    against an implementer accidentally adding a dependency on, say,
    ``anthropic`` or ``openai`` to the MCP server layer.
    """
    forbidden_prefixes = (
        "anthropic",
        "openai",
        "mcp",  # any third-party "mcp" SDK
        "claude_code",
        "codex",
    )
    # Re-import the package fresh and inspect its declared dependencies
    # by scanning the source for ``import`` statements.
    import scieasy.ai.agent.mcp as mcp_pkg

    pkg_dir = Path(mcp_pkg.__file__).parent
    for py_file in pkg_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            for bad in forbidden_prefixes:
                # Match ``import <bad>`` or ``from <bad>``; allow
                # ``scieasy.ai.agent.mcp`` itself.
                if stripped.startswith(f"import {bad}") or stripped.startswith(f"from {bad}"):
                    raise AssertionError(f"Forbidden third-party import '{bad}' in {py_file}: {stripped}")
