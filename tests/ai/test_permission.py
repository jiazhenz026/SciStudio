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


def test_policy_does_not_auto_approve_mcp_tools_in_strict_v1() -> None:
    """Phase-1 v1: MCP tools always escalate. Phase 2 will refine."""
    policy = PermissionPolicy(PermissionMode.STRICT)
    assert policy.should_auto_approve("mcp__scieasy__read_workflow", {}) is False
    assert policy.should_auto_approve("mcp__scieasy__write_workflow", {}) is False


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
