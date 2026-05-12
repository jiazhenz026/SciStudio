"""Smoke tests for the T-ECA-101 Phase 1 module scaffold.

These tests verify only the *shape* of the scaffold — imports load,
Protocols are structurally conformed to, the exception hierarchy is
wired correctly, enum values are stable, and every stub raises
:class:`NotImplementedError` so a downstream agent cannot mistakenly
call a silent no-op.

Behavioural tests for each subsystem ship with their respective
implementation tickets (T-ECA-102..110, T-ECA-204).
"""

from __future__ import annotations

import importlib

import pytest

_AGENT_SUBMODULES: tuple[str, ...] = (
    "scieasy.ai.agent",
    "scieasy.ai.agent.binary_discovery",
    "scieasy.ai.agent.claude_code",
    "scieasy.ai.agent.errors",
    "scieasy.ai.agent.permission",
    "scieasy.ai.agent.provider",
    "scieasy.ai.agent.session",
    "scieasy.ai.agent.stream_json",
    "scieasy.ai.agent.system_prompt",
    "scieasy.ai.agent.transcript",
)


def test_module_imports_clean() -> None:
    """Every module under ``scieasy.ai.agent`` must import without side effects."""
    for name in _AGENT_SUBMODULES:
        importlib.import_module(name)


def test_protocols_runtime_checkable() -> None:
    """``ClaudeCodeProvider`` must structurally implement :class:`AgentProvider`."""
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider
    from scieasy.ai.agent.provider import AgentProvider

    assert isinstance(ClaudeCodeProvider, type)
    assert ClaudeCodeProvider.name == "claude-code"
    assert ClaudeCodeProvider.binary_name == "claude"

    # Structural attribute checks — Protocol drift detection.
    for attr in ("name", "binary_name", "discover", "start_session"):
        assert hasattr(ClaudeCodeProvider, attr), f"ClaudeCodeProvider missing {attr}"

    # AgentProvider Protocol declares its required attributes.
    # ClassVars live in ``__annotations__``, methods in ``dir()``.
    proto_annotations = AgentProvider.__annotations__
    assert "name" in proto_annotations, "AgentProvider Protocol missing 'name' classvar"
    assert "binary_name" in proto_annotations, "AgentProvider Protocol missing 'binary_name' classvar"
    for attr in ("discover", "start_session"):
        assert attr in dir(AgentProvider), f"AgentProvider Protocol missing method {attr}"


def test_exception_hierarchy() -> None:
    """All custom exceptions descend from :class:`AgentError`; MCP errors form a sub-tree."""
    from scieasy.ai.agent import errors

    leaves: tuple[type[BaseException], ...] = (
        errors.AgentNotInstalledError,
        errors.AgentNotLoggedInError,
        errors.AgentLaunchError,
        errors.AgentSessionError,
        errors.AgentStreamError,
        errors.PermissionDeniedError,
        errors.PermissionTimeoutError,
        errors.MCPError,
        errors.MCPToolNotFoundError,
        errors.MCPInvalidInputError,
        errors.MCPInternalError,
        errors.MCPAtomicityError,
    )

    for cls in leaves:
        assert issubclass(cls, errors.AgentError)
        # Every error is constructible with a message argument.
        instance = cls("test")
        assert isinstance(instance, errors.AgentError)
        assert str(instance) == "test"

    # MCP sub-tree.
    mcp_leaves: tuple[type[errors.MCPError], ...] = (
        errors.MCPToolNotFoundError,
        errors.MCPInvalidInputError,
        errors.MCPInternalError,
        errors.MCPAtomicityError,
    )
    for cls in mcp_leaves:
        assert issubclass(cls, errors.MCPError)


def test_permission_mode_values() -> None:
    """``PermissionMode`` string values are stable; they appear in on-disk session metadata."""
    from scieasy.ai.agent.provider import PermissionMode

    assert PermissionMode.STRICT.value == "strict"
    assert PermissionMode.BYPASS.value == "bypass"
    assert {m.value for m in PermissionMode} == {"strict", "bypass"}


def test_auto_approve_native_tools_set() -> None:
    """The canonical native-tool whitelist contains the eight names from spec §5 T-ECA-110."""
    from scieasy.ai.agent.permission import AUTO_APPROVE_NATIVE_TOOLS

    expected: frozenset[str] = frozenset(
        {
            "Read",
            "Glob",
            "Grep",
            "WebSearch",
            "TodoWrite",
            "NotebookRead",
            "BashOutput",
            "KillShell",
        }
    )
    assert expected == AUTO_APPROVE_NATIVE_TOOLS
    assert isinstance(AUTO_APPROVE_NATIVE_TOOLS, frozenset)
    assert len(AUTO_APPROVE_NATIVE_TOOLS) == 8


def test_stubs_raise_not_implemented() -> None:
    """Every stub method/function must raise :class:`NotImplementedError`.

    This proves the stubs are wired into the module surface (not silent
    no-ops) and that downstream agents who skip ahead get an immediate,
    loud failure.
    """
    from pathlib import Path

    from scieasy.ai.agent.binary_discovery import find_binary
    from scieasy.ai.agent.claude_code import ClaudeCodeProvider
    from scieasy.ai.agent.permission import PermissionPolicy
    from scieasy.ai.agent.provider import PermissionMode
    from scieasy.ai.agent.session import AgentSessionManager
    from scieasy.ai.agent.stream_json import parse_event
    from scieasy.ai.agent.system_prompt import compose_system_prompt
    from scieasy.ai.agent.transcript import TranscriptWriter

    # T-ECA-102 has implemented `find_binary`; it now returns Path | None
    # rather than raising. Skeleton coverage for binary_discovery is
    # owned by tests/ai/test_binary_discovery.py.
    result = find_binary("definitely-not-a-real-binary-xyz-123")
    assert result is None or isinstance(result, Path)

    # T-ECA-103 has implemented `parse_event`; empty bytes now raise
    # AgentStreamError, not NotImplementedError. Full coverage lives in
    # tests/ai/test_stream_json.py.
    from scieasy.ai.agent.errors import AgentStreamError

    with pytest.raises(AgentStreamError):
        parse_event(b"")

    with pytest.raises(NotImplementedError):
        compose_system_prompt(Path("/tmp"))

    with pytest.raises(NotImplementedError):
        ClaudeCodeProvider.discover()

    with pytest.raises(NotImplementedError):
        ClaudeCodeProvider().start_session(
            project_dir=Path("/tmp"),
            system_prompt="",
            mcp_config={},
            resume_session_id=None,
            permission_mode=PermissionMode.STRICT,
        )

    policy = PermissionPolicy(PermissionMode.STRICT)
    assert policy.mode is PermissionMode.STRICT
    with pytest.raises(NotImplementedError):
        policy.should_auto_approve("Read", {})

    manager = AgentSessionManager()
    assert AgentSessionManager.DEFAULT_CONCURRENT_CAP == 5
    with pytest.raises(NotImplementedError):
        manager.get_session(Path("/tmp"), "chat-1")

    writer = TranscriptWriter(Path("/tmp/transcript.jsonl"))
    assert writer.path == Path("/tmp/transcript.jsonl")
    with pytest.raises(NotImplementedError):
        writer.close()


def test_no_third_party_sdk_imports() -> None:
    """No agent submodule may import ``anthropic`` or ``openai`` SDKs."""
    import sys

    for name in _AGENT_SUBMODULES:
        importlib.import_module(name)

    forbidden = {"anthropic", "openai"}
    # Walk the modules that were actually loaded by importing the agent
    # package, not the entire interpreter state, to avoid false
    # positives from unrelated test infrastructure.
    loaded_via_agent = {mod_name for mod_name in sys.modules if mod_name.startswith("scieasy.ai.agent")}
    for mod_name in loaded_via_agent:
        module = sys.modules[mod_name]
        for attr_name in dir(module):
            value = getattr(module, attr_name, None)
            if value is None:
                continue
            value_module = getattr(value, "__module__", "")
            top = value_module.split(".", 1)[0] if value_module else ""
            assert top not in forbidden, f"{mod_name}.{attr_name} resolves into forbidden SDK {top!r}"
