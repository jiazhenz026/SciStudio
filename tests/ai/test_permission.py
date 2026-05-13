"""Tests for the T-ECA-110 permission policy + pending-decision registry."""

from __future__ import annotations

import asyncio

import pytest

from scieasy.ai.agent import permission as permission_module
from scieasy.ai.agent.permission import (
    AUTO_APPROVE_NATIVE_TOOLS,
    PermissionPolicy,
    consume_pending_decision,
    register_pending_decision,
    signal_decision,
)
from scieasy.ai.agent.provider import PermissionMode


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure each test starts with an empty pending-decision registry."""
    permission_module._reset_registry_for_tests()
    yield
    permission_module._reset_registry_for_tests()


# ---------------------------------------------------------------------------
# PermissionPolicy.should_auto_approve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(AUTO_APPROVE_NATIVE_TOOLS))
def test_policy_auto_approves_read_only_native_tools_in_strict_mode(tool_name: str) -> None:
    policy = PermissionPolicy(PermissionMode.STRICT)
    assert policy.should_auto_approve(tool_name, {}) is True


@pytest.mark.parametrize("tool_name", ["Edit", "Write", "Bash", "WebFetch", "NotebookEdit"])
def test_policy_requires_approval_for_write_tools_in_strict_mode(tool_name: str) -> None:
    policy = PermissionPolicy(PermissionMode.STRICT)
    assert policy.should_auto_approve(tool_name, {"file_path": "/x"}) is False


@pytest.mark.parametrize(
    "tool_name",
    ["Read", "Edit", "Bash", "mcp__scieasy__write_workflow", "Anything"],
)
def test_policy_auto_approves_everything_in_bypass_mode(tool_name: str) -> None:
    policy = PermissionPolicy(PermissionMode.BYPASS)
    assert policy.should_auto_approve(tool_name, {}) is True


def test_policy_auto_approves_mcp_read_tools_in_strict_mode() -> None:
    """T-ECA-110 closeout (#779): SciEasy MCP read tools auto-approve."""
    from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY

    policy = PermissionPolicy(PermissionMode.STRICT)
    read_tools = [entry for entry in TOOL_REGISTRY if entry.mutation == "read"]
    assert read_tools, "expected at least one read-classified MCP tool"
    for entry in read_tools:
        prefixed = f"mcp__scieasy__{entry.name}"
        assert policy.should_auto_approve(prefixed, {}) is True, f"expected MCP read tool {prefixed!r} to auto-approve"


def test_policy_requires_approval_for_mcp_write_tools_in_strict_mode() -> None:
    """T-ECA-110 closeout (#779): SciEasy MCP write tools still escalate."""
    from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY

    policy = PermissionPolicy(PermissionMode.STRICT)
    write_tools = [entry for entry in TOOL_REGISTRY if entry.mutation == "write"]
    assert write_tools, "expected at least one write-classified MCP tool"
    for entry in write_tools:
        prefixed = f"mcp__scieasy__{entry.name}"
        assert policy.should_auto_approve(prefixed, {}) is False, (
            f"expected MCP write tool {prefixed!r} to require approval"
        )


def test_policy_fails_closed_for_unknown_mcp_tool() -> None:
    """T-ECA-110 closeout (#779): unknown MCP tool name falls through to ask."""
    policy = PermissionPolicy(PermissionMode.STRICT)
    assert policy.should_auto_approve("mcp__scieasy__not_a_real_tool", {}) is False


def test_policy_does_not_auto_approve_non_scieasy_mcp_tools() -> None:
    """T-ECA-110 closeout (#779): MCP tools from third-party servers always escalate."""
    policy = PermissionPolicy(PermissionMode.STRICT)
    # Even if the bare name happens to match a SciEasy read tool, a
    # different server prefix must still require approval — we have
    # no contract with foreign MCP servers about read-vs-write.
    assert policy.should_auto_approve("mcp__other__list_blocks", {}) is False


# ---------------------------------------------------------------------------
# Pending-decision registry: register / signal / consume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_returns_unique_id_and_event() -> None:
    rid1, ev1 = register_pending_decision()
    rid2, ev2 = register_pending_decision()
    assert rid1 != rid2
    assert isinstance(ev1, asyncio.Event)
    assert isinstance(ev2, asyncio.Event)
    assert not ev1.is_set()
    assert not ev2.is_set()


@pytest.mark.asyncio
async def test_register_with_explicit_id_uses_it() -> None:
    rid, ev = register_pending_decision("test-id-42")
    assert rid == "test-id-42"
    assert isinstance(ev, asyncio.Event)


@pytest.mark.asyncio
async def test_signal_then_consume_round_trip() -> None:
    rid, ev = register_pending_decision()
    assert not ev.is_set()
    ok = signal_decision(rid, "approve")
    assert ok is True
    assert ev.is_set()
    payload = consume_pending_decision(rid)
    assert payload == {"decision": "approve"}


@pytest.mark.asyncio
async def test_signal_with_reason_propagates() -> None:
    rid, _ = register_pending_decision()
    signal_decision(rid, "deny", reason="user clicked deny")
    payload = consume_pending_decision(rid)
    assert payload == {"decision": "deny", "reason": "user clicked deny"}


@pytest.mark.asyncio
async def test_signal_returns_false_for_unknown_id() -> None:
    assert signal_decision("does-not-exist", "approve") is False


@pytest.mark.asyncio
async def test_consume_returns_none_when_id_unknown() -> None:
    assert consume_pending_decision("does-not-exist") is None


@pytest.mark.asyncio
async def test_consume_is_idempotent_pop() -> None:
    rid, _ = register_pending_decision()
    signal_decision(rid, "approve")
    assert consume_pending_decision(rid) == {"decision": "approve"}
    # Second consume returns None — the entry is gone.
    assert consume_pending_decision(rid) is None


@pytest.mark.asyncio
async def test_signal_unblocks_awaited_event() -> None:
    """End-to-end async behaviour: a wait_for on the event resolves when signaled."""
    rid, event = register_pending_decision()

    async def signaller() -> None:
        # Yield control so the awaiter starts waiting first.
        await asyncio.sleep(0.01)
        signal_decision(rid, "approve")

    await asyncio.gather(
        asyncio.wait_for(event.wait(), timeout=1.0),
        signaller(),
    )
    payload = consume_pending_decision(rid)
    assert payload == {"decision": "approve"}


@pytest.mark.asyncio
async def test_event_times_out_if_never_signaled() -> None:
    """A pending decision that is never signaled fails the wait."""
    _, event = register_pending_decision()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(event.wait(), timeout=0.05)
