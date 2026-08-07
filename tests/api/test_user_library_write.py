"""The user library write path — the second door (ADR-053 §4, §14).

``docs/specs/adr-053-personal-tool-library.md`` §2.3 and FR-006 to FR-010,
issue #1996. Until this endpoint existed nothing in the product could put a
file in ``~/.scistudio/blocks/`` or ``~/.scistudio/types/``; reaching them
needed a file manager.

§14 calls this "the highest-risk surface in the spec" because it is the first
write path in the product whose target is outside every project root. Its
constraint is the **inverse** of the project endpoint's, not a relaxation of
it, so this file attacks it as an attacker would: traversal, absolute and
drive-relative paths, differing Windows drives, symlink escape, nested
subdirectories, non-Python extensions, and silent overwrite. FR-009 is pinned
by the same file, because "we added a second door" is only true while the first
one is still shut.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime
from scistudio.core.dropins import user_blocks_dir, user_types_dir

PROBE_BLOCK = '''\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class WrittenProbe(Block):
    """Block written through the user library endpoint."""

    type_name: ClassVar[str] = "test.written_probe"
    name: ClassVar[str] = "written_probe"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}
'''

PROBE_TYPE = '''\
from scistudio.core.types.base import DataObject


class WrittenProbeType(DataObject):
    """Type written through the user library endpoint."""
'''


def _put(
    client: TestClient,
    *,
    target: str,
    filename: str,
    content: str = "x = 1\n",
    overwrite: bool | None = None,
) -> httpx.Response:
    body: dict[str, object] = {"content": content}
    if overwrite is not None:
        body["overwrite"] = overwrite
    return client.put(
        "/api/user-library/file",
        params={"target": target, "filename": filename},
        json=body,
    )


def _get(client: TestClient, *, target: str, filename: str) -> httpx.Response:
    return client.get("/api/user-library/file", params={"target": target, "filename": filename})


# ---------------------------------------------------------------------------
# FR-006 — both targets, chosen by the caller
# ---------------------------------------------------------------------------


def test_write_lands_in_the_user_blocks_directory(client: TestClient) -> None:
    response = _put(client, target="blocks", filename="my_block.py", content=PROBE_BLOCK)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["target"] == "blocks"
    assert payload["kind"] == "created"
    landed = user_blocks_dir() / "my_block.py"
    assert Path(payload["path"]) == landed
    assert landed.read_text(encoding="utf-8") == PROBE_BLOCK


def test_write_lands_in_the_user_types_directory(client: TestClient) -> None:
    response = _put(client, target="types", filename="my_type.py", content=PROBE_TYPE)
    assert response.status_code == 200, response.text
    assert Path(response.json()["path"]) == user_types_dir() / "my_type.py"
    assert not (user_blocks_dir() / "my_type.py").exists()


def test_the_target_is_never_inferred_from_content(client: TestClient) -> None:
    """FR-006: a ``DataObject`` file goes to ``blocks`` if the caller says so.

    The endpoint does not read the file to decide where it belongs. Inference
    would make the destination depend on a parse the caller cannot see, which
    is exactly what FR-006 forbids.
    """
    assert _put(client, target="blocks", filename="looks_like_a_type.py", content=PROBE_TYPE).status_code == 200
    assert (user_blocks_dir() / "looks_like_a_type.py").exists()
    assert not (user_types_dir() / "looks_like_a_type.py").exists()


def test_an_unknown_target_is_rejected(client: TestClient) -> None:
    assert _put(client, target="workflows", filename="x.py").status_code == 422


# ---------------------------------------------------------------------------
# FR-007 — the inverse path constraint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename",
    [
        "../escaped.py",
        "../../escaped.py",
        "..\\escaped.py",
        "sub/nested.py",
        "sub\\nested.py",
        "/etc/passwd.py",
        "\\\\server\\share\\evil.py",
    ],
)
def test_traversal_and_paths_are_refused(client: TestClient, filename: str) -> None:
    """Anything that is not a bare filename is a 403, before any disk access."""
    response = _put(client, target="blocks", filename=filename)
    assert response.status_code == 403, response.text


@pytest.mark.skipif(sys.platform != "win32", reason="drive-relative paths are a Windows path semantic")
@pytest.mark.parametrize("filename", ["C:evil.py", "C:\\Windows\\evil.py", "Z:\\elsewhere\\evil.py"])
def test_windows_drive_paths_are_refused(client: TestClient, filename: str) -> None:
    """``C:evil.py`` is drive-relative and its ``Path.name`` looks innocent.

    The basename test alone would pass it, which is why the drive test is a
    separate condition rather than an implication of it.
    """
    assert _put(client, target="blocks", filename=filename).status_code == 403


def test_an_empty_filename_is_rejected(client: TestClient) -> None:
    assert _put(client, target="blocks", filename="").status_code == 400
    assert _put(client, target="blocks", filename="   ").status_code == 400


@pytest.mark.parametrize("filename", ["notes.txt", "archive.zip", "block.py.bak", "noextension"])
def test_only_python_files_are_accepted(client: TestClient, filename: str) -> None:
    """FR-007: both registries scan for ``.py``; nothing else is loadable there."""
    assert _put(client, target="blocks", filename=filename).status_code == 415


def test_a_symlink_escaping_the_library_is_refused(client: TestClient, tmp_path: Path) -> None:
    """Containment is compared on resolved real paths, never string prefixes."""
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.py"
    victim.write_text("original\n", encoding="utf-8")

    root = user_blocks_dir()
    root.mkdir(parents=True, exist_ok=True)
    try:
        (root / "escape.py").symlink_to(victim)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted in this environment")

    response = _put(client, target="blocks", filename="escape.py", content="pwned\n", overwrite=True)
    assert response.status_code == 403, response.text
    assert victim.read_text(encoding="utf-8") == "original\n"


def _link_to_directory(link: Path, target: Path) -> None:
    """Point *link* at directory *target*, or skip if the OS refuses.

    Creating a symlink on Windows needs a privilege CI agents and developer
    machines usually lack, but a **directory junction** does not and
    ``os.path.realpath`` follows it identically. Falling back to one keeps the
    escape case covered on the platform this repository is developed on rather
    than deferring it to Linux CI.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if sys.platform != "win32":
            pytest.skip("symlink creation is not permitted in this environment")
    import subprocess

    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not link.exists():
        pytest.skip("neither a symlink nor a directory junction can be created here")


def test_a_linked_subdirectory_cannot_smuggle_a_nested_write(client: TestClient, tmp_path: Path) -> None:
    """FR-007: the file must land *directly* in the target root.

    A nested path is already refused as "not a bare filename", so the case that
    matters is a link whose own name is a bare filename but whose resolution is
    a directory outside the root — the case a string-prefix comparison accepts.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    root = user_blocks_dir()
    root.mkdir(parents=True, exist_ok=True)
    _link_to_directory(root / "linked.py", outside)
    assert _put(client, target="blocks", filename="linked.py", overwrite=True).status_code == 403
    assert not (outside / "linked.py").exists()


# ---------------------------------------------------------------------------
# FR-008 — no silent overwrite
# ---------------------------------------------------------------------------


def test_an_existing_file_is_reported_not_overwritten(client: TestClient) -> None:
    assert _put(client, target="blocks", filename="dup.py", content="first\n").status_code == 200
    conflict = _put(client, target="blocks", filename="dup.py", content="second\n")
    assert conflict.status_code == 409, conflict.text
    assert "dup.py" in conflict.json()["detail"]
    assert (user_blocks_dir() / "dup.py").read_text(encoding="utf-8") == "first\n"


def test_overwrite_requires_an_explicit_opt_in(client: TestClient) -> None:
    assert _put(client, target="blocks", filename="dup.py", content="first\n").status_code == 200
    response = _put(client, target="blocks", filename="dup.py", content="second\n", overwrite=True)
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "modified"
    assert (user_blocks_dir() / "dup.py").read_text(encoding="utf-8") == "second\n"


# ---------------------------------------------------------------------------
# FR-031 — the existence probe
# ---------------------------------------------------------------------------


def test_the_probe_reports_absence_then_presence(client: TestClient) -> None:
    """404 means "safe to create", 200 means "exists" — the project probe's shape."""
    assert _get(client, target="blocks", filename="probe.py").status_code == 404
    assert _put(client, target="blocks", filename="probe.py", content="probe\n").status_code == 200
    found = _get(client, target="blocks", filename="probe.py")
    assert found.status_code == 200
    assert found.json()["content"] == "probe\n"
    # Each target is probed independently.
    assert _get(client, target="types", filename="probe.py").status_code == 404


def test_the_probe_refuses_the_same_paths_the_write_does(client: TestClient) -> None:
    assert _get(client, target="blocks", filename="../escaped.py").status_code == 403
    assert _get(client, target="blocks", filename="notes.txt").status_code == 415


# ---------------------------------------------------------------------------
# FR-009 — the first door is still shut
# ---------------------------------------------------------------------------


def test_the_project_endpoint_still_rejects_escaping_paths(client: TestClient, opened_project: Path) -> None:
    """This spec adds a second door; it does not widen the first (FR-009)."""
    project_id = client.get("/api/projects/").json()[0]["id"]
    for path in ("../escaped.py", "../../escaped.py"):
        response = client.put(
            f"/api/projects/{project_id}/file",
            params={"path": path},
            json={"content": "pwned\n"},
        )
        assert response.status_code == 403, (path, response.text)
    assert not (opened_project.parent / "escaped.py").exists()


def test_the_project_endpoint_cannot_reach_the_user_library(client: TestClient, opened_project: Path) -> None:
    """The user library sits outside every project root by construction."""
    project_id = client.get("/api/projects/").json()[0]["id"]
    relative = Path("..") / ".." / "home" / ".scistudio" / "blocks" / "smuggled.py"
    response = client.put(
        f"/api/projects/{project_id}/file",
        params={"path": str(relative)},
        json={"content": "pwned\n"},
    )
    assert response.status_code == 403
    assert not (user_blocks_dir() / "smuggled.py").exists()


# ---------------------------------------------------------------------------
# FR-010 — discoverable without a restart
# ---------------------------------------------------------------------------


def test_a_written_block_is_discoverable_without_a_restart(client: TestClient, runtime: ApiRuntime) -> None:
    """FR-010: the write refreshes every registry the event invalidated."""
    assert "test.written_probe" not in runtime.block_registry.all_specs()

    response = _put(client, target="blocks", filename="written_probe.py", content=PROBE_BLOCK)
    assert response.status_code == 200, response.text
    assert response.json()["registries_refreshed"] is True

    listing = client.get("/api/blocks/").json()["blocks"]
    written = {block["type_name"]: block for block in listing}
    assert "test.written_probe" in written
    # FR-019 support: the promoted block now reads as ``user``, so the frontend
    # hides the promotion action for it rather than offering a self-copy.
    assert written["test.written_probe"]["origin"] == "user"


def test_a_written_type_is_discoverable_without_a_restart(client: TestClient, runtime: ApiRuntime) -> None:
    assert "WrittenProbeType" not in runtime.type_registry.all_types()
    assert _put(client, target="types", filename="written_probe_type.py", content=PROBE_TYPE).status_code == 200
    assert "WrittenProbeType" in runtime.type_registry.all_types()


# ---------------------------------------------------------------------------
# FR-011 + FR-065 — promotion through the agent reaches the palette
# ---------------------------------------------------------------------------


def test_a_block_promoted_through_the_agent_appears_in_the_palette(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """FR-065's acceptance sentence, asserted literally.

    The app's lifespan installs a read-through adapter over the live
    ``ApiRuntime`` as the MCP context, so the registries the agent refreshes are
    the very ones ``GET /api/blocks/`` reads. That is what makes "without a
    restart" true on the desktop path; the standalone bridge's half is in
    ``tests/ai/test_mcp_tools_library.py``.
    """
    from scistudio.ai.agent.mcp import tools_library

    blocks_dir = opened_project / "blocks"
    blocks_dir.mkdir(parents=True, exist_ok=True)
    (blocks_dir / "agent_promoted.py").write_text(
        PROBE_BLOCK.replace("WrittenProbe", "AgentPromoted")
        .replace("test.written_probe", "test.agent_promoted")
        .replace('"written_probe"', '"agent_promoted"'),
        encoding="utf-8",
    )
    runtime.refresh_all_registries()

    palette = {block["type_name"]: block for block in client.get("/api/blocks/").json()["blocks"]}
    assert palette["test.agent_promoted"]["origin"] == "project"

    result = asyncio.run(tools_library.promote_to_user_library(block_type="test.agent_promoted"))
    assert Path(result.path) == user_blocks_dir() / "agent_promoted.py"

    # No restart, no explicit reload call: the palette request that follows the
    # tool call already sees the promoted block.
    refreshed = {block["type_name"]: block for block in client.get("/api/blocks/").json()["blocks"]}
    assert "test.agent_promoted" in refreshed
    assert (user_blocks_dir() / "agent_promoted.py").exists()
