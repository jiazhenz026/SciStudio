"""Unit tests for :mod:`scieasy.ai.agent.config_files` (T-ECA-108)."""

from __future__ import annotations

import json
from pathlib import Path

from scieasy.ai.agent.config_files import (
    write_hook_config,
    write_mcp_config,
)
from scieasy.ai.agent.provider import PermissionMode

# ---------------------------------------------------------------------------
# mcp.json
# ---------------------------------------------------------------------------


def test_write_mcp_config_creates_scieasy_dir(tmp_path: Path) -> None:
    """``.scieasy/`` is auto-created if missing."""
    assert not (tmp_path / ".scieasy").exists()
    result = write_mcp_config(tmp_path, "chat-abc")
    assert result.exists()
    assert result == tmp_path / ".scieasy" / "mcp.json"


def test_write_mcp_config_roundtrip(tmp_path: Path) -> None:
    """The written JSON is valid and contains the SciEasy MCP server stanza."""
    result = write_mcp_config(tmp_path, "chat-abc")
    data = json.loads(result.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    server = data["mcpServers"]["scieasy"]
    assert server["command"] == "scieasy"
    assert server["args"] == ["mcp-bridge"]
    assert server["env"]["SCIEASY_CHAT_ID"] == "chat-abc"
    assert server["env"]["SCIEASY_PROJECT_DIR"] == str(tmp_path.resolve())


def test_write_mcp_config_byte_stable_idempotent(tmp_path: Path) -> None:
    """Calling twice with identical inputs produces byte-identical output."""
    first = write_mcp_config(tmp_path, "chat-xyz")
    bytes_1 = first.read_bytes()
    second = write_mcp_config(tmp_path, "chat-xyz")
    bytes_2 = second.read_bytes()
    assert bytes_1 == bytes_2


def test_write_mcp_config_lf_newlines_only(tmp_path: Path) -> None:
    """No CRLF in the output regardless of host OS — critical for diff-stability."""
    result = write_mcp_config(tmp_path, "chat-abc")
    raw = result.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_write_mcp_config_sorted_keys(tmp_path: Path) -> None:
    """Key ordering is deterministic (sorted)."""
    result = write_mcp_config(tmp_path, "chat-abc")
    text = result.read_text(encoding="utf-8")
    # Top-level only has "mcpServers" so check the env block.
    chat_id_idx = text.index("SCIEASY_CHAT_ID")
    proj_dir_idx = text.index("SCIEASY_PROJECT_DIR")
    assert chat_id_idx < proj_dir_idx, "env keys should be sorted alphabetically"


def test_write_mcp_config_distinct_chat_ids_differ(tmp_path: Path) -> None:
    """Different chat_id values produce different file contents."""
    write_mcp_config(tmp_path, "chat-one")
    one = (tmp_path / ".scieasy" / "mcp.json").read_text(encoding="utf-8")
    write_mcp_config(tmp_path, "chat-two")
    two = (tmp_path / ".scieasy" / "mcp.json").read_text(encoding="utf-8")
    assert one != two
    assert "chat-one" in one
    assert "chat-two" in two


# ---------------------------------------------------------------------------
# claude-hooks.json
# ---------------------------------------------------------------------------


def test_write_hook_config_strict_registers_pretooluse(tmp_path: Path) -> None:
    """Strict mode registers the PreToolUse hook pointing at ``scieasy hook-bridge``."""
    result = write_hook_config(tmp_path, PermissionMode.STRICT)
    data = json.loads(result.read_text(encoding="utf-8"))
    pre = data["hooks"]["PreToolUse"]
    assert isinstance(pre, list) and len(pre) == 1
    entry = pre[0]
    assert entry["matcher"] == ""
    inner = entry["hooks"]
    assert isinstance(inner, list) and len(inner) == 1
    assert inner[0] == {"command": "scieasy hook-bridge", "type": "command"}


def test_write_hook_config_bypass_has_empty_hooks(tmp_path: Path) -> None:
    """Bypass mode writes an empty ``hooks`` dict — no PreToolUse registration."""
    result = write_hook_config(tmp_path, PermissionMode.BYPASS)
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data == {"hooks": {}}


def test_write_hook_config_creates_scieasy_dir(tmp_path: Path) -> None:
    """``.scieasy/`` is auto-created for the hooks file too."""
    assert not (tmp_path / ".scieasy").exists()
    result = write_hook_config(tmp_path, PermissionMode.STRICT)
    assert result.exists()
    assert result == tmp_path / ".scieasy" / "claude-hooks.json"


def test_write_hook_config_byte_stable_idempotent(tmp_path: Path) -> None:
    """Calling twice with identical inputs is byte-identical."""
    write_hook_config(tmp_path, PermissionMode.STRICT)
    first = (tmp_path / ".scieasy" / "claude-hooks.json").read_bytes()
    write_hook_config(tmp_path, PermissionMode.STRICT)
    second = (tmp_path / ".scieasy" / "claude-hooks.json").read_bytes()
    assert first == second


def test_write_hook_config_strict_vs_bypass_differ(tmp_path: Path) -> None:
    """Strict and bypass modes produce different files."""
    write_hook_config(tmp_path, PermissionMode.STRICT)
    strict_bytes = (tmp_path / ".scieasy" / "claude-hooks.json").read_bytes()
    write_hook_config(tmp_path, PermissionMode.BYPASS)
    bypass_bytes = (tmp_path / ".scieasy" / "claude-hooks.json").read_bytes()
    assert strict_bytes != bypass_bytes


def test_write_hook_config_lf_newlines_only(tmp_path: Path) -> None:
    """No CRLF in the output."""
    result = write_hook_config(tmp_path, PermissionMode.STRICT)
    raw = result.read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


def test_both_writers_coexist(tmp_path: Path) -> None:
    """Writing both files in succession leaves both intact."""
    write_mcp_config(tmp_path, "c1")
    write_hook_config(tmp_path, PermissionMode.STRICT)
    assert (tmp_path / ".scieasy" / "mcp.json").exists()
    assert (tmp_path / ".scieasy" / "claude-hooks.json").exists()


def test_existing_scieasy_dir_not_clobbered(tmp_path: Path) -> None:
    """Pre-existing ``.scieasy/`` content is preserved."""
    scieasy = tmp_path / ".scieasy"
    scieasy.mkdir()
    keepfile = scieasy / "settings.json"
    keepfile.write_text('{"keep": true}\n', encoding="utf-8")
    write_mcp_config(tmp_path, "c1")
    write_hook_config(tmp_path, PermissionMode.BYPASS)
    assert keepfile.exists()
    assert json.loads(keepfile.read_text(encoding="utf-8")) == {"keep": True}


def test_expected_mcp_payload_exact(tmp_path: Path) -> None:
    """Snapshot of the exact mcp.json content for forward-compat detection."""
    write_mcp_config(tmp_path, "snap-id")
    text = (tmp_path / ".scieasy" / "mcp.json").read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert parsed == {
        "mcpServers": {
            "scieasy": {
                "args": ["mcp-bridge"],
                "command": "scieasy",
                "env": {
                    "SCIEASY_CHAT_ID": "snap-id",
                    "SCIEASY_PROJECT_DIR": str(tmp_path.resolve()),
                },
            }
        }
    }


def test_expected_hook_payload_strict_exact(tmp_path: Path) -> None:
    """Snapshot of the exact strict-mode claude-hooks.json content."""
    write_hook_config(tmp_path, PermissionMode.STRICT)
    parsed = json.loads((tmp_path / ".scieasy" / "claude-hooks.json").read_text(encoding="utf-8"))
    assert parsed == {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [{"command": "scieasy hook-bridge", "type": "command"}],
                }
            ]
        }
    }
