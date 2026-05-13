"""Tests for ``scieasy mcp-bridge`` standalone mode (#787).

These tests spawn the bridge as a subprocess with no backend running
and verify it spins up an in-process MCP server, answers
``tools/list``, and exits cleanly on stdin EOF.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# We rely on ``scieasy`` being on PATH (editable install). When it's
# not, skip — these tests are integration-flavoured.
_SCIEASY_BIN = "scieasy.exe" if sys.platform == "win32" else "scieasy"


def _has_scieasy() -> bool:
    """Return True if the scieasy console script is callable."""
    from shutil import which

    return which("scieasy") is not None


pytestmark = pytest.mark.skipif(
    not _has_scieasy(),
    reason="scieasy console script not installed; run `pip install -e .` first",
)


def _bridge_env(project_dir: Path) -> dict[str, str]:
    """Build an env that points the bridge at *project_dir*."""
    env = dict(os.environ)
    env["SCIEASY_PROJECT_DIR"] = str(project_dir)
    # Force standalone path by pointing the bridge at a non-existent
    # explicit socket — but we also need to bypass the explicit-socket
    # guard, so we leave SCIEASY_PROJECT_DIR set and just rely on no
    # backend running.
    return env


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal SciEasy project layout under *tmp_path*."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text(
        "project:\n  name: test\n  version: 0.1.0\n",
        encoding="utf-8",
    )
    for sub in ("workflows", "blocks", "data/raw"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    return project


@pytest.mark.timeout(60)
def test_standalone_bridge_serves_tools_list_and_exits_on_eof(tmp_path: Path) -> None:
    """Send tools/list on stdin, get back 25 tools, then EOF should close."""
    project = _make_project(tmp_path)

    proc = subprocess.Popen(
        [_SCIEASY_BIN, "mcp-bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_bridge_env(project),
    )

    # Send initialize then tools/list, then close stdin to signal EOF.
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write((json.dumps(init_req) + "\n").encode("utf-8"))
        proc.stdin.write((json.dumps(list_req) + "\n").encode("utf-8"))
        proc.stdin.flush()
        proc.stdin.close()
        # Read two response lines.
        out_init = proc.stdout.readline().decode("utf-8")
        out_list = proc.stdout.readline().decode("utf-8")
    except Exception:
        proc.kill()
        raise

    rc = proc.wait(timeout=20)
    stderr = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", errors="replace")
    assert rc == 0, f"bridge exited with {rc}; stderr:\n{stderr}"

    init_resp = json.loads(out_init)
    list_resp = json.loads(out_list)

    assert init_resp.get("result", {}).get("serverInfo", {}).get("name") == "scieasy-mcp", init_resp
    tools = list_resp.get("result", {}).get("tools")
    assert isinstance(tools, list), list_resp
    # 25 registered tools per ADR-033 §3 D2.2.
    assert len(tools) == 25, f"expected 25 tools, got {len(tools)}: {[t.get('name') for t in tools]}"
    names = {t["name"] for t in tools}
    # Spot-check a few canonical names from each category.
    assert {"list_blocks", "validate_workflow", "scaffold_block", "preview_data", "search_docs"} <= names


@pytest.mark.timeout(30)
def test_standalone_bridge_falls_back_when_no_project_dir(tmp_path: Path) -> None:
    """Bridge should still serve tools/list even without SCIEASY_PROJECT_DIR."""
    env = dict(os.environ)
    env.pop("SCIEASY_PROJECT_DIR", None)
    # Make sure cwd is somewhere without a project.yaml — pytest tmp_path is
    # a clean dir by construction.
    proc = subprocess.Popen(
        [_SCIEASY_BIN, "mcp-bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
        env=env,
    )
    try:
        assert proc.stdin is not None
        assert proc.stdout is not None
        proc.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
        proc.stdin.flush()
        proc.stdin.close()
        out_line = proc.stdout.readline().decode("utf-8")
    except Exception:
        proc.kill()
        raise

    rc = proc.wait(timeout=15)
    stderr = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", errors="replace")
    assert rc == 0, f"bridge exited with {rc}; stderr:\n{stderr}"

    resp = json.loads(out_line)
    tools = resp["result"]["tools"]
    assert len(tools) == 25
