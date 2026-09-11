"""ADR-055 Spec 2 (#2279) — workspace inspect and author tools.

Inspect tools run directly against a stub context. Author tools run through the
real WebMCP bridge (``POST /api/webmcp/call`` on an app with its lifespan), so
the production MCPContext adapter, the shared write path in
``scistudio.api.runtime._file_writes``, and the ``file.changed`` events are the
real ones (spec §4.4: registry-level, no browser).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp import _context, tools_authoring, tools_workspace
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, MCPServer, mcp
from scistudio.ai.agent.mcp.tools_workflow.read import (
    list_blocks_called,
    mark_list_blocks_called,
    reset_list_blocks_called,
)

_INSPECT_TOOLS = {"list_directory", "get_file_info", "search_files", "read_file"}
_AUTHOR_TOOLS = {"write_file", "create_directory", "patch_file", "move_path", "delete_path"}
_EXTERNAL_TOOLS = {
    *_INSPECT_TOOLS,
    *_AUTHOR_TOOLS,
    "get_agent_context",
    "run_command",
    "list_commands",
    "get_command_status",
    "cancel_command",
}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@dataclass
class _StubContext:
    _project_dir: Path | None = None
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture(autouse=True)
def _fresh_list_blocks_state() -> Iterator[None]:
    """Each test starts as a freshly started backend would."""
    reset_list_blocks_called()
    yield
    reset_list_blocks_called()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text("# A\nhello workflow\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "raw.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    return root


@pytest.fixture
def stub_ctx(project: Path) -> Iterator[_StubContext]:
    context = _StubContext(_project_dir=project)
    _context.set_context(context)
    yield context
    _context.set_context(None)


# ---------------------------------------------------------------------------
# Inspect tools (stub context).
# ---------------------------------------------------------------------------


def test_list_directory_resolves_relative_paths_against_the_project(stub_ctx: _StubContext) -> None:
    result = _run(tools_workspace.list_directory(path="."))
    assert result.status == "ok"
    by_name = {entry.name: entry for entry in result.entries}
    assert by_name["notes"].type == "directory"
    assert by_name["notes"].path == "notes"
    # Directories first.
    assert result.entries[0].type == "directory"


def test_list_directory_reports_truncation(stub_ctx: _StubContext, project: Path) -> None:
    many = project / "many"
    many.mkdir()
    for index in range(5):
        (many / f"f{index}.txt").write_text("x", encoding="utf-8")
    result = _run(tools_workspace.list_directory(path="many", max_entries=2))
    assert len(result.entries) == 2
    assert result.total_entries == 5
    assert result.truncated is True


def test_inspect_reads_absolute_paths_outside_the_project(stub_ctx: _StubContext, tmp_path: Path) -> None:
    """#2279 decision 2: inspect tools read anything the backend user can read, in place."""
    shared = tmp_path / "shared-datasets"
    shared.mkdir()
    dataset = shared / "dataset.txt"
    dataset.write_bytes(b"server-resident data\n")  # bytes: no newline translation on Windows

    result = _run(tools_workspace.read_file(path=str(dataset)))
    assert result.status == "ok"
    assert result.content == "server-resident data\n"
    assert result.path == os.path.realpath(dataset)  # absolute, not project-relative
    listing = _run(tools_workspace.list_directory(path=str(shared)))
    assert [entry.name for entry in listing.entries] == ["dataset.txt"]
    # Used in place: nothing was copied into the project.
    assert not (Path(stub_ctx.project_dir or "") / "dataset.txt").exists()


def test_relative_path_without_a_project_is_refused_but_absolute_works(tmp_path: Path) -> None:
    target = tmp_path / "loose.txt"
    target.write_bytes(b"loose\n")
    _context.set_context(_StubContext(_project_dir=None))
    try:
        refused = _run(tools_workspace.read_file(path="loose.txt"))
        absolute = _run(tools_workspace.read_file(path=str(target)))
    finally:
        _context.set_context(None)
    assert refused.status == "refused"
    assert refused.refusal is not None and refused.refusal.code == "no_active_project"
    assert absolute.status == "ok" and absolute.content == "loose\n"


class _CountingFile:
    """File wrapper that counts every byte pulled from disk."""

    def __init__(self, path: Path, counter: dict[str, int]) -> None:
        self._fh = open(path, "rb")  # noqa: SIM115 - closed by __exit__/close
        self._counter = counter

    def __enter__(self) -> _CountingFile:
        return self

    def __exit__(self, *exc: object) -> None:
        self._fh.close()

    def close(self) -> None:
        self._fh.close()

    def fileno(self) -> int:
        return self._fh.fileno()

    def seek(self, *args: Any) -> int:
        return self._fh.seek(*args)

    def readinto(self, buffer: Any) -> int:
        got = self._fh.readinto(buffer) or 0
        self._counter["bytes"] += got
        return got

    def read(self, size: int = -1) -> bytes:
        assert size >= 0, "an unbounded read() would materialize the whole file"
        data = self._fh.read(size)
        self._counter["bytes"] += len(data)
        return data

    def readline(self, size: int = -1) -> bytes:
        assert size >= 0, "an unbounded readline() could materialize the whole file"
        data = self._fh.readline(size)
        self._counter["bytes"] += len(data)
        return data


def test_read_file_is_bounded_while_streaming(
    stub_ctx: _StubContext, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AS2 / SC-002: a file 4x the cap never has more than cap + probe byte read."""
    cap = tools_workspace.READ_DEFAULT_LIMIT_BYTES
    size = 4 * cap + 123
    (project / "big.txt").write_bytes(b"a" * size)
    counter = {"bytes": 0}
    monkeypatch.setattr(tools_workspace, "_open_binary", lambda path: _CountingFile(path, counter))

    result = _run(tools_workspace.read_file(path="big.txt"))
    assert result.status == "ok"
    assert result.bytes_returned == cap
    assert len(result.content) == cap
    assert result.truncated is True
    assert result.total_size_bytes == size
    assert result.next_offset == cap
    assert counter["bytes"] <= cap + 1


def test_read_file_continuation_reassembles_non_ascii_text(stub_ctx: _StubContext, project: Path) -> None:
    text = "é中a\n" * 20_000
    (project / "unicode.txt").write_bytes(text.encode("utf-8"))
    pieces: list[str] = []
    offset = 0
    for _ in range(1000):
        result = _run(tools_workspace.read_file(path="unicode.txt", offset=offset, limit=4099))
        assert result.status == "ok"
        pieces.append(result.content)
        if not result.truncated:
            assert result.next_offset is None
            break
        assert result.next_offset is not None and result.next_offset > offset
        offset = result.next_offset
    joined = "".join(pieces)
    # Compared as a flag: a failing diff of two ~100 KB strings would stall pytest.
    matches = joined == text
    assert matches, f"reassembled {len(joined)} chars, expected {len(text)}"


def test_read_at_exactly_the_limit_is_unambiguous(stub_ctx: _StubContext, project: Path) -> None:
    (project / "exact.txt").write_bytes(b"b" * 1000)
    (project / "over.txt").write_bytes(b"b" * 1001)
    exact = _run(tools_workspace.read_file(path="exact.txt", limit=1000))
    over = _run(tools_workspace.read_file(path="over.txt", limit=1000))
    assert exact.truncated is False and exact.next_offset is None and exact.total_size_bytes == 1000
    assert over.truncated is True and over.next_offset == 1000 and over.total_size_bytes == 1001


def test_read_past_the_end_and_huge_limits_do_not_error(stub_ctx: _StubContext, project: Path) -> None:
    past = _run(tools_workspace.read_file(path="notes/a.md", offset=10_000))
    assert past.status == "ok" and past.content == "" and past.truncated is False
    clamped = _run(tools_workspace.read_file(path="notes/a.md", limit=10**9))
    assert clamped.status == "ok"
    assert clamped.limit_applied == tools_workspace.READ_MAX_LIMIT_BYTES


def test_binary_file_is_refused_with_a_base64_fallback(stub_ctx: _StubContext, project: Path) -> None:
    payload = bytes(range(256)) * 4
    (project / "blob.bin").write_bytes(payload)
    refused = _run(tools_workspace.read_file(path="blob.bin"))
    assert refused.status == "refused"
    assert refused.refusal is not None and refused.refusal.code == "binary_content"
    raw = _run(tools_workspace.read_file(path="blob.bin", limit=10, encoding="base64"))
    assert raw.status == "ok"
    assert base64.b64decode(raw.content) == payload[:10]
    assert raw.truncated is True and raw.total_size_bytes == len(payload)


def test_get_file_info_reports_whether_author_tools_may_change_a_path(stub_ctx: _StubContext) -> None:
    note = _run(tools_workspace.get_file_info(path="notes/a.md"))
    data = _run(tools_workspace.get_file_info(path="data/raw.csv"))
    assert note.exists and note.type == "file" and note.within_project
    assert note.writable_by_author_tools is True and note.looks_binary is False
    assert data.writable_by_author_tools is False
    assert data.author_tools_note and "data/" in data.author_tools_note


def test_search_files_by_name_and_content_is_bounded(stub_ctx: _StubContext, project: Path) -> None:
    src = project / "src"
    src.mkdir()
    for index in range(30):
        (src / f"mod{index:02d}.py").write_text(f"# module {index}\nNEEDLE = {index}\n", encoding="utf-8")
    (src / "blob.py").write_bytes(b"\x00\x01NEEDLE")

    hits = _run(tools_workspace.search_files(path="src", name_pattern="*.py", content="needle", max_results=5))
    assert hits.status == "ok"
    assert len(hits.hits) == 5
    assert hits.truncated is True
    assert all(hit.line == 2 and hit.path.startswith("src/") for hit in hits.hits)

    everything = _run(tools_workspace.search_files(path="src", name_pattern="*.py", content="NEEDLE", max_results=200))
    assert len(everything.hits) == 30
    assert any("binary" in note for note in everything.notes)

    names = _run(tools_workspace.search_files(path=".", name_pattern="a.md"))
    assert [hit.path for hit in names.hits] == ["notes/a.md"]
    assert names.hits[0].line is None


def test_search_rejects_an_invalid_regex(stub_ctx: _StubContext) -> None:
    result = _run(tools_workspace.search_files(path=".", content="(unclosed", regex=True))
    assert result.status == "refused"
    assert result.refusal is not None and result.refusal.code == "invalid_regex"


def test_non_ascii_and_native_separator_paths(tmp_path: Path) -> None:
    root = tmp_path / "项目 é"
    folder = root / "数据 notes"
    folder.mkdir(parents=True)
    (folder / "说明.txt").write_bytes("内容 ✓\n".encode())
    _context.set_context(_StubContext(_project_dir=root))
    try:
        listing = _run(tools_workspace.list_directory(path="数据 notes"))
        native = _run(tools_workspace.read_file(path=str(Path("数据 notes") / "说明.txt")))
        absolute = _run(tools_workspace.read_file(path=str(folder / "说明.txt")))
    finally:
        _context.set_context(None)
    assert [entry.name for entry in listing.entries] == ["说明.txt"]
    assert listing.entries[0].path == "数据 notes/说明.txt"
    assert native.content == "内容 ✓\n" and native.path == "数据 notes/说明.txt"
    assert absolute.content == "内容 ✓\n"


def test_author_tools_refuse_without_the_shared_write_path(stub_ctx: _StubContext, project: Path) -> None:
    """FR-005: never a bare write — a context without project_files cannot author."""
    result = _run(tools_workspace.write_file(path="notes/new.md", content="x"))
    assert result.status == "refused"
    assert result.refusal is not None and result.refusal.code == "write_path_unavailable"
    assert not (project / "notes" / "new.md").exists()


# ---------------------------------------------------------------------------
# Author tools through the real bridge.
# ---------------------------------------------------------------------------


@dataclass
class _Bridge:
    client: TestClient
    root: Path

    @property
    def project_id(self) -> str:
        return self.client.app.state.runtime.active_project.id  # type: ignore[attr-defined, no-any-return]

    def call(self, tool: str, /, **arguments: Any) -> dict[str, Any]:
        response = self.client.post(
            "/api/webmcp/call",
            headers={"X-SciStudio-WebMCP-Token": self.client.app.state.webmcp_session_token},  # type: ignore[attr-defined]
            json={"name": tool, "arguments": arguments, "projectId": self.project_id},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["isError"] is False, body
        return body["structuredContent"]  # type: ignore[no-any-return]


@pytest.fixture
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Bridge]:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    from scistudio.api import runtime as runtime_module
    from scistudio.api.app import create_app

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/projects/", json={"name": "Workspace Tools", "description": "", "path": str(parent)}
        )
        assert response.status_code == 200, response.text
        yield _Bridge(client=client, root=Path(response.json()["path"]))


@pytest.fixture
def file_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from scistudio.engine import events as events_module

    seen: list[dict[str, Any]] = []
    original = events_module.EventBus.emit

    async def _spy(self: Any, event: Any) -> Any:
        if event.event_type == "file.changed":
            seen.append(dict(event.data or {}))
        return await original(self, event)

    monkeypatch.setattr(events_module.EventBus, "emit", _spy)
    return seen


def test_write_file_uses_the_shared_helper_and_emits_file_changed(
    bridge: _Bridge, file_events: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """SC-003: the write passes through the shared helper and reaches the event bus."""
    from scistudio.api.runtime import _file_writes

    helper_calls: list[Path] = []
    original = _file_writes.write_project_file

    async def _spy(runtime: Any, **kwargs: Any) -> Any:
        helper_calls.append(kwargs["target"])
        return await original(runtime, **kwargs)

    monkeypatch.setattr(_file_writes, "write_project_file", _spy)

    result = bridge.call("write_file", path="notes/new.md", content="# New\n", create_parents=True)
    assert result["status"] == "ok"
    assert result["kind"] == "created"
    assert isinstance(result["state_version"], int)
    assert (bridge.root / "notes" / "new.md").read_text(encoding="utf-8") == "# New\n"
    assert len(helper_calls) == 1
    event = next(e for e in file_events if e["entity_id"] == "notes/new.md")
    assert event["source"] == "agent"
    assert event["kind"] == "created"
    assert event["changed_by"] == "mcp.write_file"
    assert event["version"] == result["state_version"]
    assert event["project_id"] == bridge.project_id


def test_write_based_on_a_stale_version_is_an_explicit_conflict(bridge: _Bridge) -> None:
    """AS3: a file changed on disk since version N rejects a write based on N."""
    bridge.call("write_file", path="notes/c.md", content="first\n", create_parents=True)
    version = bridge.call("get_file_info", path="notes/c.md")["state_version"]
    target = bridge.root / "notes" / "c.md"
    target.write_text("external edit\n", encoding="utf-8")
    later = target.stat().st_mtime + 5
    os.utime(target, (later, later))

    stale = bridge.call("write_file", path="notes/c.md", content="agent\n", expected_state_version=version)
    assert stale["status"] == "conflict"
    assert stale["refusal"]["code"] == "stale_version"
    assert stale["expected_state_version"] == version
    assert stale["current_state_version"] > version
    assert target.read_text(encoding="utf-8") == "external edit\n"

    fresh = bridge.call("get_file_info", path="notes/c.md")["state_version"]
    ok = bridge.call("write_file", path="notes/c.md", content="agent\n", expected_state_version=fresh)
    assert ok["status"] == "ok" and ok["state_version"] > fresh

    exists = bridge.call("write_file", path="notes/c.md", content="again\n", mode="create")
    assert exists["status"] == "conflict" and exists["refusal"]["code"] == "already_exists"


def test_patch_file_replaces_exactly_once_and_keeps_line_endings(bridge: _Bridge) -> None:
    target = bridge.root / "notes" / "crlf.txt"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"alpha\r\nbeta\r\nalpha two\r\n")

    ambiguous = bridge.call("patch_file", path="notes/crlf.txt", old_text="alpha", new_text="A")
    assert ambiguous["status"] == "refused" and ambiguous["refusal"]["code"] == "patch_target_ambiguous"
    missing = bridge.call("patch_file", path="notes/crlf.txt", old_text="gamma", new_text="G")
    assert missing["status"] == "refused" and missing["refusal"]["code"] == "patch_target_not_found"

    patched = bridge.call("patch_file", path="notes/crlf.txt", old_text="beta", new_text="BETA")
    assert patched["status"] == "ok" and patched["replacements"] == 1
    assert target.read_bytes() == b"alpha\r\nBETA\r\nalpha two\r\n"


def test_author_blacklist_mirrors_the_provisioned_hooks(bridge: _Bridge) -> None:
    """#2279 decision 3: workflows/*.yaml and data/ are refused as source or target."""
    root = bridge.root
    (root / "workflows").mkdir(exist_ok=True)
    (root / "workflows" / "main.yaml").write_text("workflow: {}\n", encoding="utf-8")
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "raw.txt").write_text("raw\n", encoding="utf-8")
    bridge.call("write_file", path="notes/a.md", content="a\n", create_parents=True)

    def _refused(name: str, code: str, **arguments: Any) -> dict[str, Any]:
        result = bridge.call(name, **arguments)
        assert result["status"] == "refused", (name, arguments, result)
        assert result["refusal"]["code"] == code, (name, arguments, result)
        return result

    yaml = _refused("write_file", "protected_workflow_yaml", path="workflows/main.yaml", content="x")
    assert {"write_workflow", "update_block_config"} <= set(yaml["refusal"]["use_instead"])
    _refused("write_file", "protected_workflow_yaml", path="workflows/sub/other.yml", content="x", create_parents=True)
    _refused("move_path", "protected_workflow_yaml", path="workflows/main.yaml", destination="workflows/renamed.yaml")
    _refused("delete_path", "protected_workflow_yaml", path="workflows", recursive=True)
    data = _refused("write_file", "protected_data_dir", path="data/new.csv", content="x")
    assert data["refusal"]["use_instead"] == ["run_workflow"]
    _refused("write_file", "protected_data_dir", path="DATA/upper.csv", content="x")
    _refused("create_directory", "protected_data_dir", path="data/new_dir")
    _refused("move_path", "protected_data_dir", path="notes/a.md", destination="data/a.md")
    _refused("move_path", "protected_data_dir", path="data/raw.txt", destination="notes/raw.txt")
    _refused("delete_path", "protected_data_dir", path="data/raw.txt")

    # Nothing changed on disk.
    assert (root / "workflows" / "main.yaml").read_text(encoding="utf-8") == "workflow: {}\n"
    assert (root / "data" / "raw.txt").exists()
    assert (root / "notes" / "a.md").exists()
    assert not (root / "data" / "a.md").exists()
    # Non-yaml files under workflows/ are ordinary files.
    assert bridge.call("write_file", path="workflows/README.md", content="notes\n")["status"] == "ok"


def test_author_tools_are_confined_to_the_project(bridge: _Bridge, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    escaped = bridge.call("write_file", path=str(outside), content="x")
    assert escaped["status"] == "refused" and escaped["refusal"]["code"] == "outside_project"
    traversal = bridge.call("write_file", path="../escape.txt", content="x")
    assert traversal["status"] == "refused" and traversal["refusal"]["code"] == "outside_project"
    assert not outside.exists()
    assert not (bridge.root.parent / "escape.txt").exists()
    root_delete = bridge.call("delete_path", path=".", recursive=True)
    assert root_delete["status"] == "refused" and root_delete["refusal"]["code"] == "project_root"


def test_block_writes_require_list_blocks_once_per_backend_lifetime(bridge: _Bridge, tmp_path: Path) -> None:
    """Hook parity (a): refused until list_blocks ran; any transport marks it; restart resets it."""
    first = bridge.call("write_file", path="blocks/probe_block.py", content="X = 1\n", create_parents=True)
    assert first["status"] == "refused" and first["refusal"]["code"] == "list_blocks_required"
    assert first["refusal"]["use_instead"] == ["list_blocks"]
    assert not (bridge.root / "blocks" / "probe_block.py").exists()

    bridge.call("list_blocks")
    assert list_blocks_called()
    assert (
        bridge.call("write_file", path="blocks/probe_block.py", content="X = 1\n", create_parents=True)["status"]
        == "ok"
    )

    # A backend restart forgets the call.
    reset_list_blocks_called()
    again = bridge.call("write_file", path="blocks/other_block.py", content="X = 2\n")
    assert again["status"] == "refused" and again["refusal"]["code"] == "list_blocks_required"

    # list_blocks through the LOCAL socket transport marks it too.
    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=bridge.root)
    listed = _run(
        server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_blocks"}})
    )
    assert "result" in listed
    assert bridge.call("write_file", path="blocks/other_block.py", content="X = 2\n")["status"] == "ok"

    # A move that creates a block file is a block write as well.
    reset_list_blocks_called()
    bridge.call("write_file", path="notes/staged.py", content="X = 3\n", create_parents=True)
    moved = bridge.call("move_path", path="notes/staged.py", destination="blocks/staged.py")
    assert moved["status"] == "refused" and moved["refusal"]["code"] == "list_blocks_required"


def test_scaffold_block_rule_applies_through_the_bridge_only(bridge: _Bridge) -> None:
    """Hook parity (a) for scaffold_block: bridge calls are gated; the local transport is unchanged."""
    bridged = bridge.call("scaffold_block", name="bridged_block", category="process")
    assert bridged["status"] == "refused"
    assert bridged["refusal"]["code"] == "list_blocks_required"
    assert not (bridge.root / "blocks" / "bridged_block.py").exists()

    # Local transport (no bridge marker): still writes without list_blocks.
    local = _run(
        tools_authoring.scaffold_block(name="local_block", category="process", input_ports=None, output_ports=None)
    )
    assert local.status == "ok"
    assert (bridge.root / "blocks" / "local_block.py").is_file()
    assert list_blocks_called() is False

    bridge.call("list_blocks")
    allowed = bridge.call("scaffold_block", name="bridged_block", category="process")
    assert allowed["status"] == "ok"
    assert (bridge.root / "blocks" / "bridged_block.py").is_file()


def test_block_writes_carry_port_type_warnings(bridge: _Bridge) -> None:
    """Hook parity (b): generic DataObject / empty accepted_types -> non-blocking warnings."""
    mark_list_blocks_called()
    generic = bridge.call(
        "write_file",
        path="blocks/generic_ports.py",
        content=(
            'PORTS = [InputPort(name="image", accepted_types=[DataObject]), OutputPort(name="out", accepted_types=[])]\n'
        ),
        create_parents=True,
    )
    assert generic["status"] == "ok"
    assert len(generic["warnings"]) == 2
    assert any("DataObject" in warning and "'image'" in warning for warning in generic["warnings"])
    assert any("accepted_types=[]" in warning for warning in generic["warnings"])

    concrete = bridge.call(
        "write_file",
        path="blocks/concrete_ports.py",
        content='PORTS = [InputPort(name="image", accepted_types=[Image])]\n',
    )
    assert concrete["status"] == "ok" and concrete["warnings"] == []

    elsewhere = bridge.call(
        "write_file",
        path="notes/not_a_block.py",
        content='PORTS = [InputPort(name="image", accepted_types=[DataObject])]\n',
        create_parents=True,
    )
    assert elsewhere["warnings"] == []


def test_move_and_delete_emit_file_events(bridge: _Bridge, file_events: list[dict[str, Any]]) -> None:
    bridge.call("write_file", path="notes/m.md", content="m\n", create_parents=True)
    file_events.clear()

    moved = bridge.call("move_path", path="notes/m.md", destination="notes/renamed.md")
    assert moved["status"] == "ok" and moved["kind"] == "moved"
    assert moved["affected_paths"] == ["deleted:notes/m.md", "created:notes/renamed.md"]
    assert [(e["entity_id"], e["kind"]) for e in file_events] == [
        ("notes/m.md", "deleted"),
        ("notes/renamed.md", "created"),
    ]
    assert not (bridge.root / "notes" / "m.md").exists()

    file_events.clear()
    deleted = bridge.call("delete_path", path="notes/renamed.md")
    assert deleted["status"] == "ok"
    assert [(e["entity_id"], e["kind"]) for e in file_events] == [("notes/renamed.md", "deleted")]

    assert bridge.call("create_directory", path="scratch")["status"] == "ok"
    bridge.call("write_file", path="scratch/one.txt", content="1\n")
    bridge.call("write_file", path="scratch/two.txt", content="2\n")
    not_empty = bridge.call("delete_path", path="scratch")
    assert not_empty["status"] == "conflict" and not_empty["refusal"]["code"] == "directory_not_empty"
    file_events.clear()
    removed = bridge.call("delete_path", path="scratch", recursive=True)
    assert removed["status"] == "ok"
    assert sorted(e["entity_id"] for e in file_events) == ["scratch/one.txt", "scratch/two.txt"]
    assert not (bridge.root / "scratch").exists()


def test_external_tools_are_bridge_only_with_mutation_from_tags(bridge: _Bridge, tmp_path: Path) -> None:
    """FR-003: audience:external on every new tool, verified in both catalogues."""
    registry = {tool.name: tool for tool in _run(mcp.list_tools())}
    for name in _EXTERNAL_TOOLS:
        assert AUDIENCE_EXTERNAL_TAG in set(registry[name].tags or ()), name

    catalogue = bridge.client.get(
        "/api/webmcp/tools",
        headers={"X-SciStudio-WebMCP-Token": bridge.client.app.state.webmcp_session_token},  # type: ignore[attr-defined]
    ).json()
    by_name = {entry["name"]: entry for entry in catalogue["tools"]}
    assert set(by_name) >= _EXTERNAL_TOOLS
    for name in _INSPECT_TOOLS | {"get_agent_context", "list_commands", "get_command_status"}:
        assert by_name[name]["mutation"] == "read", name
    for name in _AUTHOR_TOOLS | {"run_command", "cancel_command"}:
        assert by_name[name]["mutation"] == "write", name

    server = MCPServer(socket_path=tmp_path / "mcp.sock", project_dir=bridge.root)
    local = _run(server.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    local_names = {tool["name"] for tool in local["result"]["tools"]}
    assert not (_EXTERNAL_TOOLS & local_names)
    assert "list_blocks" in local_names


def test_author_tool_logs_carry_no_contents_or_paths(bridge: _Bridge, caplog: pytest.LogCaptureFixture) -> None:
    """FR-012: operation identifiers and outcomes only."""
    caplog.set_level(logging.DEBUG)
    bridge.call("write_file", path="notes/secret-path-7f3a.md", content="SECRET-CONTENT-91b2", create_parents=True)
    bridge.call("read_file", path="notes/secret-path-7f3a.md")
    for record in caplog.records:
        message = record.getMessage()
        assert "SECRET-CONTENT-91b2" not in message, record.name
        if record.name.startswith(("scistudio.ai.agent.mcp", "scistudio.api.routes.webmcp")):
            assert "secret-path-7f3a" not in message, (record.name, message)
