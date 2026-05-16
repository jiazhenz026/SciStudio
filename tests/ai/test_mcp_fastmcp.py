"""FastMCP parity scaffold (ADR-040 §3.1, S40a skeleton).

These tests assert the FastMCP-backed MCP server matches the ADR-040
contract once I40a Phase 2a implementation lands. Every test is
``@pytest.mark.skip(reason=...)`` in this skeleton phase — I40a flips
each to running as the corresponding behavior is wired up.

The scaffold pre-declares the parity properties the audit phase
(A40-skel) will verify against:

* 26 tools are discoverable via ``mcp.list_tools()``.
* Every write-class tool's result model has a ``next_step: str`` field.
* ``scaffold_block`` has the widened ADR-040 §3.2a signature with
  ``input_ports`` + ``output_ports`` dict args and a ``warnings`` field.
* ``inputSchema`` is FastMCP-generated (not the ADR-033-era
  ``additionalProperties: true`` stub).
* Soft-validation warnings fire on generic-``DataObject`` ports and
  unregistered type names per §3.2a.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): wire FastMCP list_tools().")
def test_fastmcp_lists_26_tools() -> None:
    """ADR-040 §3.1: 26 tools discoverable via mcp.list_tools()."""
    from scieasy.ai.agent.mcp.server import mcp

    tools = mcp.list_tools()
    assert len(tools) == 26


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): write-class next_step parity.")
def test_write_class_tools_have_next_step() -> None:
    """ADR-040 §3.1: every write-class tool's result model has next_step: str."""
    # Write-class tools: write_workflow, run_workflow, cancel_run,
    # finish_ai_block, scaffold_block, reload_blocks, run_block_tests,
    # update_block_config.
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): §3.2a widened signature.")
def test_scaffold_block_signature_widened() -> None:
    """ADR-040 §3.2a (manifest §8.6): scaffold_block accepts input_ports + output_ports dicts."""
    from scieasy.ai.agent.mcp.tools_authoring import scaffold_block

    sig = scaffold_block.__signature__  # type: ignore[attr-defined]
    params = sig.parameters
    assert "input_ports" in params
    assert "output_ports" in params


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): §3.2a warnings on DataObject ports.")
def test_scaffold_block_warns_on_generic_dataobject_port() -> None:
    """ADR-040 §3.2a: warning text fires when a port uses generic DataObject."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): §3.2a warnings on unregistered type.")
def test_scaffold_block_warns_on_unregistered_type() -> None:
    """ADR-040 §3.2a: warning text fires when a port type isn't in TypeRegistry."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): inputSchema rejects malformed args.")
def test_input_schema_rejects_malformed_call() -> None:
    """ADR-040 §3.1: FastMCP-generated inputSchema rejects calls before reaching the tool body."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): finish_ai_block error union.")
def test_finish_ai_block_returns_union_of_ok_or_error() -> None:
    """ADR-035 §3.5 + ADR-040 §3.1: finish_ai_block returns FinishAIBlockOK | FinishAIBlockError discriminated union."""
    raise NotImplementedError("skeleton")
