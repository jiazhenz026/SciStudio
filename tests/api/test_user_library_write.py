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
import os
import sys
import tempfile
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
    move_from: dict[str, str] | None = None,
) -> httpx.Response:
    body: dict[str, object] = {"content": content}
    if overwrite is not None:
        body["overwrite"] = overwrite
    if move_from is not None:
        body["move_from"] = move_from
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
# FR-007 — the containment rules that had no test that would fail without them
# ---------------------------------------------------------------------------
#
# A coverage run over ``routes/user_library.py`` found four containment rules
# with zero executed lines: deleting any of them would have failed nothing
# (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P2-5). Rule 4 in
# particular *works* — the audit executed it by hand — but nothing in the suite
# reached it, because every input the other tests supply is caught by an
# earlier rule. These reach each one directly.


def test_a_link_to_a_deeper_directory_inside_the_root_is_refused(client: TestClient) -> None:
    """Rule 4: the file must land *directly* in the root, not merely inside it.

    This is the one case that passes the ``commonpath`` containment check and
    must still be refused — a link whose own name is a bare filename and whose
    resolution is a directory nested deeper *within* the same root. The
    existing linked-directory test escapes the root and exits at the earlier
    comparison, so it never reaches this rule.
    """
    root = user_blocks_dir()
    inner = root / "inner" / "sub"
    inner.mkdir(parents=True, exist_ok=True)
    _link_to_directory(root / "deep.py", inner)

    response = _put(client, target="blocks", filename="deep.py", overwrite=True)
    assert response.status_code == 403, response.text
    assert "directly in the target directory" in response.json()["detail"]
    assert list(inner.glob("*.py")) == []


def test_a_containment_comparison_that_cannot_be_made_is_treated_as_an_escape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``commonpath`` raises rather than returning for paths on different drives.

    The module docstring names that case, but no request can reach it: an
    absolute or drive-qualified filename is refused several rules earlier, so
    the branch is unreachable from the endpoint's own inputs. Driving it
    directly is the only way to assert that a comparison which *cannot be made*
    is refused rather than surfacing as a 500.
    """

    def _raise(_paths: object) -> str:
        raise ValueError("paths don't have the same drive")

    monkeypatch.setattr("os.path.commonpath", _raise)

    response = _put(client, target="blocks", filename="ordinary.py")
    assert response.status_code == 403, response.text
    assert "escapes the user library root" in response.json()["detail"]


@pytest.mark.parametrize("filename", [".", ".."])
def test_a_bare_dot_filename_is_refused_as_traversal(client: TestClient, filename: str) -> None:
    """``..`` alone carries no separator, so it needs its own rule."""
    response = _put(client, target="blocks", filename=filename)
    assert response.status_code == 403, response.text
    assert "traversal" in response.json()["detail"].lower()


@pytest.mark.parametrize("filename", ["ev\x00il.py", "evil\n.py", "evil\tx.py"])
def test_control_characters_in_a_filename_are_refused(client: TestClient, filename: str) -> None:
    """An embedded NUL passed every path rule and then broke the write.

    ``os.replace`` raises ``ValueError`` for it — not ``OSError`` — so it
    escaped the cleanup handler, left the temp file behind permanently, and
    surfaced as an unhandled 500 (P2-2). Refusing control characters up front
    is the rule; the broadened cleanup below is the belt.
    """
    response = _put(client, target="blocks", filename=filename)
    assert response.status_code in (400, 403), response.text
    # Refused before any filesystem access, so the root is not even created.
    assert not user_blocks_dir().exists() or list(user_blocks_dir().iterdir()) == []


@pytest.mark.parametrize("filename", ["NUL.py", "CON.py", "com1.py", "LPT3.py", "aux.py"])
def test_a_windows_reserved_device_name_is_refused(client: TestClient, filename: str) -> None:
    """Whether Win32 resolves ``NUL.py`` to the device is build-dependent (P3-3).

    Refused on every platform, so a library written on POSIX does not become
    unusable — or a device write — when the same directory is opened on
    Windows.
    """
    response = _put(client, target="blocks", filename=filename)
    assert response.status_code == 403, response.text
    assert "reserved device name" in response.json()["detail"]


@pytest.mark.parametrize("filename", ["SHOUT.PY", "mixed.Py"])
def test_an_uppercase_python_extension_is_refused(client: TestClient, filename: str) -> None:
    """A ``.PY`` file means two different things on two platforms (P3-2).

    Windows ``glob("*.py")`` matches it, so it is a live drop-in there and dead
    on POSIX. The product declines to create one rather than creating a file
    whose behaviour depends on the host.
    """
    assert _put(client, target="blocks", filename=filename).status_code == 415


def test_a_dot_leading_filename_is_refused(client: TestClient) -> None:
    """A hidden drop-in is one the user cannot find in order to delete it."""
    response = _put(client, target="blocks", filename=".hidden.py")
    assert response.status_code == 403, response.text
    assert "start with a dot" in response.json()["detail"]


def test_content_over_the_editor_cap_is_refused(client: TestClient) -> None:
    """The 413 rule, which nothing exercised."""
    from scistudio.api.routes.projects import ADR036_FILE_SIZE_CAP_BYTES

    oversized = "x" * (ADR036_FILE_SIZE_CAP_BYTES + 1)
    response = _put(client, target="blocks", filename="huge.py", content=oversized)
    assert response.status_code == 413, response.text
    assert not (user_blocks_dir() / "huge.py").exists()


def test_a_directory_standing_where_the_file_would_go_is_refused(client: TestClient) -> None:
    """The 400 rule, on both the read and the write half."""
    (user_blocks_dir() / "adir.py").mkdir(parents=True, exist_ok=True)

    write = _put(client, target="blocks", filename="adir.py", overwrite=True)
    assert write.status_code == 400, write.text
    assert "directory" in write.json()["detail"]

    read = _get(client, target="blocks", filename="adir.py")
    assert read.status_code == 400, read.text


# ---------------------------------------------------------------------------
# FR-007 — the temp file the atomic write goes through
# ---------------------------------------------------------------------------


def test_the_write_temp_file_is_not_itself_a_dropin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Atomicity of the destination name is not enough on its own.

    The temp file has to share the destination directory for the landing step
    to be atomic, and that directory is globbed for ``*.py`` and executed on
    every scan — so a ``.py`` temp file is a second drop-in that a palette
    refresh concurrent with a save can import half-written, and a real
    ``BlockRegistry.scan()`` was shown to execute one (P2-2). Asserted from
    inside the write, which is the only moment the file exists. The spy is on
    ``os.link`` because that is what lands a *new* file: the destination name
    has to appear already complete, which is the property an exclusive create
    followed by a write would not have.
    """
    seen: list[list[str]] = []
    real_link = os.link

    def _spy(src: str, dst: object) -> None:
        seen.append(sorted(entry.name for entry in user_blocks_dir().glob("*.py")))
        real_link(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr("scistudio.api.routes.user_library.os.link", _spy)

    assert _put(client, target="blocks", filename="atomic.py", content=PROBE_BLOCK).status_code == 200

    assert seen == [[]], "no .py file may exist in the scanned directory while the write is in flight"
    assert sorted(entry.name for entry in user_blocks_dir().glob("*.py")) == ["atomic.py"]


def test_a_write_that_fails_outside_oserror_leaves_nothing_behind(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cleanup used to be ``except OSError`` and leaked on anything else.

    A leaked temp file is caller-controlled content sitting in a directory the
    scan reads, under a name the user can find in neither the palette nor the
    product's own file listing.
    """

    def _raise(_src: str, _dst: object) -> None:
        raise ValueError("embedded null character in dst")

    monkeypatch.setattr("scistudio.api.routes.user_library.os.link", _raise)

    response = _put(client, target="blocks", filename="doomed.py", content=PROBE_BLOCK)
    assert response.status_code == 500, response.text
    assert list(user_blocks_dir().iterdir()) == [], "the temp file must not survive the failure"


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


def test_a_writer_that_arrives_after_the_probe_is_not_overwritten(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-008 must survive a second *writer*, not only a second request.

    FR-065 put the API process and the standalone MCP bridge on the same
    ``~/.scistudio``, so "does this exist" and "write it" are two moments with
    another process free to run in between — a path this spec created. A
    check-then-``os.replace`` sequence destroys whatever landed in that window
    even though the request carried ``overwrite=false``, which is the silent
    overwrite FR-008 forbids.

    The interleaving is constructed rather than raced: the competing file
    appears after the existence probe has already answered "absent", which is
    the one ordering that matters, and it appears on every run.
    """
    landed = user_blocks_dir() / "contested.py"
    rival = "written by the other process\n"
    real_mkstemp = tempfile.mkstemp

    def _mkstemp_then_lose_the_race(*, prefix: str, suffix: str, dir: str) -> tuple[int, str]:
        result = real_mkstemp(prefix=prefix, suffix=suffix, dir=dir)
        landed.write_text(rival, encoding="utf-8")
        return result

    monkeypatch.setattr("scistudio.api.routes.user_library.tempfile.mkstemp", _mkstemp_then_lose_the_race)

    response = _put(client, target="blocks", filename="contested.py", content=PROBE_BLOCK)

    assert response.status_code == 409, response.text
    assert "contested.py" in response.json()["detail"]
    assert landed.read_text(encoding="utf-8") == rival, "the other writer's file must survive"
    assert sorted(entry.name for entry in user_blocks_dir().iterdir()) == ["contested.py"], (
        "the refused write must leave no temp file behind"
    )


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


# ---------------------------------------------------------------------------
# FR-017 — the write consumes the project file it was given
# ---------------------------------------------------------------------------


def _project_id(client: TestClient) -> str:
    """The open project's id, however the listing happens to be shaped."""
    payload = client.get("/api/projects/").json()
    entries = payload["projects"] if isinstance(payload, dict) else payload
    return str(entries[0]["id"])


def test_a_named_source_is_removed_after_the_write(
    client: TestClient,
    opened_project: Path,
) -> None:
    """Promotion moves: the library copy lands, and then the original goes."""
    source = opened_project / "types" / "moved_probe.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("x = 1\n", encoding="utf-8")

    response = _put(
        client,
        target="types",
        filename="moved_probe.py",
        move_from={"project_id": _project_id(client), "path": "types/moved_probe.py"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert Path(body["moved_from"]) == source
    assert body["move_error"] is None
    assert not source.exists()
    assert (user_types_dir() / "moved_probe.py").exists()


def test_no_source_named_leaves_everything_alone(
    client: TestClient,
    opened_project: Path,
) -> None:
    """The new-file flow creates rather than promotes, and removes nothing."""
    bystander = opened_project / "types" / "bystander.py"
    bystander.parent.mkdir(parents=True, exist_ok=True)
    bystander.write_text("x = 1\n", encoding="utf-8")

    body = _put(client, target="types", filename="created_probe.py").json()

    assert body["moved_from"] is None
    assert body["move_error"] is None
    assert bystander.exists()


def test_an_already_absent_source_is_not_an_error(
    client: TestClient,
    opened_project: Path,
) -> None:
    """ "Gone" is the move's goal, so finding it gone is success, not failure."""
    response = _put(
        client,
        target="types",
        filename="absent_probe.py",
        move_from={"project_id": _project_id(client), "path": "types/never_existed.py"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["move_error"] is None
    assert (user_types_dir() / "absent_probe.py").exists()


def test_an_unknown_project_is_reported_rather_than_failing_the_write(
    client: TestClient,
) -> None:
    """A removal failure never fails the request.

    The library copy is on disk, so the promotion happened; a 4xx here would
    tell the caller nothing did. The outcome degrades to a copy and says so,
    which is what the UI turns into a warning.
    """
    body = _put(
        client,
        target="types",
        filename="orphan_probe.py",
        move_from={"project_id": "no-such-project", "path": "types/x.py"},
    ).json()

    assert body["moved_from"] is None
    assert "could not resolve" in (body["move_error"] or "")
    assert (user_types_dir() / "orphan_probe.py").exists()


@pytest.mark.parametrize("path", ["../../secrets.py", r"..\..\secrets.py"])
def test_a_traversing_source_path_is_refused_by_the_shared_resolver(
    client: TestClient,
    opened_project: Path,
    path: str,
) -> None:
    """The removal reuses the project endpoints' sandbox rather than restating it.

    A second containment check is a second thing to get wrong, so this asserts
    the shared one is really reached: the escape is refused, and the write still
    succeeds and is reported as a copy.
    """
    body = _put(
        client,
        target="types",
        filename="sandboxed_probe.py",
        move_from={"project_id": _project_id(client), "path": path},
    ).json()

    assert body["moved_from"] is None
    assert body["move_error"]
    assert (user_types_dir() / "sandboxed_probe.py").exists()
