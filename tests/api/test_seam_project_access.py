"""ADR-055 identity seam — project access for an edition (issue #2328).

``scistudio.api.seam`` gives an edition's routes and MCP tools a public way to
reach the project, as thin wrappers over the internals the workspace tools
already use:

* ``active_project_root(app)`` — the open project's root, or ``None``;
* ``ToolRefusal`` — raised inside a tool, it becomes a Spec 1 ``isError``
  result carrying its message and the workspace tools' refusal shape, also
  across the WebMCP bridge, which withholds other exceptions' text;
* ``check_author_path`` — project confinement plus the Spec 2 author
  blacklist, refusing with the author tools' own codes;
* ``write_project_file`` — bytes through the editor's shared write path,
  confined to the project;
* ``add_upload_listener`` — hears every staged upload complete or be
  discarded; a failing listener never breaks the upload.

Each is exercised at the root mount and under ``/user/alice/scistudio``.
Route paths are neutral fixtures (``/api/test-edition/...``).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from fastmcp.exceptions import ToolError
from mcp.types import CallToolResult

from scistudio.api import app as app_module
from scistudio.api.app import create_app
from scistudio.api.routes import data as data_routes
from scistudio.api.seam import (
    ToolRefusal,
    UploadEvent,
    active_project_root,
    add_upload_listener,
    check_author_path,
    mcp,
    write_project_file,
)
from tests.api.seam_contract import PREFIXED_MOUNT

MOUNTS = pytest.mark.parametrize("mount_prefix", ["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])
TOKEN_HEADER = "X-SciStudio-WebMCP-Token"
REFUSE_TOOL = "seam_fixture_refuse"
AUTHOR_TOOL = "seam_fixture_author_check"


# ---------------------------------------------------------------------------
# Fixtures and helpers.
# ---------------------------------------------------------------------------


@pytest.fixture()
def projects_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated home; returns the directory new projects are created in."""
    from scistudio.api import runtime as runtime_module

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: None)
    parent = tmp_path / "projects"
    parent.mkdir()
    return parent


def _open_project(client: TestClient, mount_prefix: str, parent: Path) -> Path:
    response = client.post(
        f"{mount_prefix}/api/projects/",
        json={"name": "Seam Project", "description": "", "path": str(parent)},
    )
    assert response.status_code == 200, response.text
    return Path(os.path.realpath(response.json()["path"]))


def _edition_router() -> APIRouter:
    """An edition route that writes the request body through the seam."""
    router = APIRouter()

    @router.post("/api/test-edition/write")
    async def write(path: str, request: Request) -> JSONResponse:
        try:
            written = await write_project_file(request.app, path, await request.body())
        except ToolRefusal as refusal:
            return JSONResponse({"code": refusal.code, "message": refusal.message}, status_code=409)
        return JSONResponse({"path": str(written)})

    return router


@pytest.fixture()
def seam_tools() -> Iterator[dict[str, Any]]:
    """Register fixture tools on the shared registry, then remove them.

    The registry must return to its baseline afterwards: other suites assert
    the exact tool count.
    """
    state: dict[str, Any] = {}

    @mcp.tool(name=REFUSE_TOOL, tags={"category:testing", "read"})
    def _refuse() -> dict[str, Any]:
        raise ToolRefusal("The edition refused this call.", code="fixture_refused", use_instead=["other_tool"])

    @mcp.tool(name=AUTHOR_TOOL, tags={"category:testing", "read"})
    def _author_check(path: str) -> dict[str, Any]:
        root = active_project_root(state["app"])
        assert root is not None
        return {"path": str(check_author_path(root, path))}

    try:
        yield state
    finally:
        mcp.local_provider.remove_tool(REFUSE_TOOL)
        mcp.local_provider.remove_tool(AUTHOR_TOOL)


def _bridge_call(client: TestClient, mount_prefix: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    token = client.app.state.webmcp_session_token  # type: ignore[attr-defined]
    response = client.post(
        f"{mount_prefix}/api/webmcp/call",
        headers={TOKEN_HEADER: token},
        json={"name": name, "arguments": arguments},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# ---------------------------------------------------------------------------
# active_project_root.
# ---------------------------------------------------------------------------


def test_active_project_root_is_none_before_startup() -> None:
    assert active_project_root(FastAPI()) is None


@MOUNTS
def test_active_project_root_follows_the_open_project(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app()
    with TestClient(app, root_path=mount_prefix) as client:
        assert active_project_root(app) is None
        project = _open_project(client, mount_prefix, projects_dir)
        assert active_project_root(app) == project


# ---------------------------------------------------------------------------
# check_author_path.
# ---------------------------------------------------------------------------


def test_check_author_path_returns_the_resolved_path(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    expected = Path(os.path.realpath(root)) / "scripts" / "analyze.py"
    assert check_author_path(root, "scripts/analyze.py") == expected
    assert check_author_path(str(root), "scripts/../scripts/analyze.py") == expected
    assert check_author_path(root, str(expected)) == expected


@pytest.mark.parametrize(
    ("rel_path", "code"),
    [
        ("../escape.txt", "outside_project"),
        ("data/raw/scan.csv", "protected_data_dir"),
        ("DATA/raw/scan.csv", "protected_data_dir"),
        ("workflows/main.yaml", "protected_workflow_yaml"),
        ("workflows/nested/other.yml", "protected_workflow_yaml"),
        ("", "empty_path"),
        (".", "project_root"),
    ],
)
def test_check_author_path_refuses_with_the_author_tools_codes(tmp_path: Path, rel_path: str, code: str) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(ToolRefusal) as refused:
        check_author_path(root, rel_path)
    assert refused.value.code == code
    assert refused.value.message


def test_check_author_path_refuses_an_absolute_path_elsewhere(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(ToolRefusal) as refused:
        check_author_path(root, str(tmp_path / "elsewhere.txt"))
    assert refused.value.code == "outside_project"


def test_a_data_refusal_names_the_tool_that_owns_the_surface(tmp_path: Path) -> None:
    with pytest.raises(ToolRefusal) as refused:
        check_author_path(tmp_path, "data/raw/scan.csv")
    assert refused.value.use_instead == ("run_workflow",)


def test_tool_refusal_is_a_tool_error_with_a_message() -> None:
    refusal = ToolRefusal("No.", code="nope", use_instead=["x"])
    assert isinstance(refusal, ToolError)
    assert (str(refusal), refusal.code, refusal.use_instead) == ("No.", "nope", ("x",))
    with pytest.raises(ValueError):
        ToolRefusal("  ")


# ---------------------------------------------------------------------------
# ToolRefusal inside a tool.
# ---------------------------------------------------------------------------


def test_a_refusal_is_an_error_result_on_the_local_transport(seam_tools: dict[str, Any]) -> None:
    result = asyncio.run(mcp.call_tool(REFUSE_TOOL, {}))
    wire = result.to_mcp_result()
    assert isinstance(wire, CallToolResult)
    assert wire.isError is True
    assert wire.structuredContent == {
        "status": "refused",
        "refusal": {
            "code": "fixture_refused",
            "message": "The edition refused this call.",
            "use_instead": ["other_tool"],
        },
    }


@MOUNTS
def test_refusals_cross_the_webmcp_bridge_as_error_results(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch, seam_tools: dict[str, Any], mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app()
    seam_tools["app"] = app
    with TestClient(app, root_path=mount_prefix) as client:
        _open_project(client, mount_prefix, projects_dir)

        refused = _bridge_call(client, mount_prefix, REFUSE_TOOL, {})
        assert refused["isError"] is True
        # The message crosses the bridge, unlike an ordinary exception's text.
        assert refused["content"] == [{"type": "text", "text": "The edition refused this call."}]
        assert refused["structuredContent"]["refusal"]["code"] == "fixture_refused"

        blacklisted = _bridge_call(client, mount_prefix, AUTHOR_TOOL, {"path": "data/raw/scan.csv"})
        assert blacklisted["isError"] is True
        assert blacklisted["structuredContent"]["status"] == "refused"
        assert blacklisted["structuredContent"]["refusal"]["code"] == "protected_data_dir"

        escaped = _bridge_call(client, mount_prefix, AUTHOR_TOOL, {"path": "../escape.txt"})
        assert escaped["isError"] is True
        assert escaped["structuredContent"]["refusal"]["code"] == "outside_project"

        allowed = _bridge_call(client, mount_prefix, AUTHOR_TOOL, {"path": "notes/plan.md"})
        assert allowed["isError"] is False


# ---------------------------------------------------------------------------
# write_project_file.
# ---------------------------------------------------------------------------


@MOUNTS
def test_write_project_file_uses_the_shared_write_path(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app(routers=[_edition_router()])
    payload = b"\x00\xff binary, not UTF-8 \xfe"
    with TestClient(app, root_path=mount_prefix) as client:
        project = _open_project(client, mount_prefix, projects_dir)
        url = f"{mount_prefix}/api/test-edition/write"

        first = client.post(url, params={"path": "results/new/scan.bin"}, content=payload)
        assert first.status_code == 200, first.text
        written = Path(first.json()["path"])
        assert written == project / "results" / "new" / "scan.bin"
        assert written.read_bytes() == payload
        # The editor's write path tracks the file's state version.
        files = app.state.runtime.project_files
        version = files.state_version(written)
        assert isinstance(version, int)

        assert client.post(url, params={"path": "results/new/scan.bin"}, content=b"again").status_code == 200
        assert written.read_bytes() == b"again"
        assert files.state_version(written) > version

        # No author blacklist here: an edition may place a transferred file under data/.
        assert client.post(url, params={"path": "data/raw/uploaded.csv"}, content=b"a,b\n").status_code == 200


@MOUNTS
def test_write_project_file_refusals(projects_dir: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app(routers=[_edition_router()])
    with TestClient(app, root_path=mount_prefix) as client:
        url = f"{mount_prefix}/api/test-edition/write"
        closed = client.post(url, params={"path": "notes/a.txt"}, content=b"x")
        assert closed.status_code == 409
        assert closed.json()["code"] == "no_active_project"

        project = _open_project(client, mount_prefix, projects_dir)
        escaped = client.post(url, params={"path": "../escape.bin"}, content=b"x")
        assert escaped.status_code == 409
        assert escaped.json()["code"] == "outside_project"
        assert not (project.parent / "escape.bin").exists()

        (project / "a-directory").mkdir()
        directory = client.post(url, params={"path": "a-directory"}, content=b"x")
        assert directory.status_code == 409
        assert directory.json()["code"] == "is_directory"


def test_write_project_file_takes_bytes_only() -> None:
    with pytest.raises(TypeError):
        asyncio.run(write_project_file(FastAPI(), "notes/a.txt", "text"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# add_upload_listener.
# ---------------------------------------------------------------------------


@MOUNTS
def test_upload_listeners_hear_a_completed_upload(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app()
    heard: list[tuple[str, UploadEvent]] = []

    def plain(event: UploadEvent) -> None:
        heard.append(("plain", event))

    async def coroutine(event: UploadEvent) -> None:
        await asyncio.sleep(0)
        heard.append(("coroutine", event))

    def failing(event: UploadEvent) -> None:
        raise RuntimeError("a broken listener")

    add_upload_listener(app, failing)
    add_upload_listener(app, plain)
    add_upload_listener(app, coroutine)
    body = b"a,b\n1,2\n"
    with TestClient(app, root_path=mount_prefix) as client:
        project = _open_project(client, mount_prefix, projects_dir)
        response = client.post(f"{mount_prefix}/api/data/upload", files={"file": ("sample.csv", body, "text/csv")})
    assert response.status_code == 200, response.text
    event = UploadEvent(path="data/raw/sample.csv", size=len(body), status="completed")
    assert heard == [("plain", event), ("coroutine", event)], "a failing listener stops no other listener"
    assert (project / "data" / "raw" / "sample.csv").read_bytes() == body


@MOUNTS
def test_upload_listeners_hear_a_discarded_upload(
    projects_dir: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    monkeypatch.setattr(data_routes, "MAX_UPLOAD_SIZE", 4)
    app = create_app()
    heard: list[UploadEvent] = []
    add_upload_listener(app, heard.append)
    with TestClient(app, root_path=mount_prefix) as client:
        project = _open_project(client, mount_prefix, projects_dir)
        response = client.post(
            f"{mount_prefix}/api/data/upload", files={"file": ("big.csv", b"0123456789", "text/csv")}
        )
    assert response.status_code == 413
    assert [(event.path, event.status) for event in heard] == [("data/raw/big.csv", "discarded")]
    assert heard[0].size > 4
    assert not (project / "data" / "raw" / "big.csv").exists()


def test_an_upload_listener_can_be_removed(projects_dir: Path) -> None:
    app = create_app()
    heard: list[UploadEvent] = []
    remove = add_upload_listener(app, heard.append)
    remove()
    remove()  # removing twice is harmless
    with TestClient(app) as client:
        _open_project(client, "", projects_dir)
        response = client.post("/api/data/upload", files={"file": ("sample.csv", b"a\n", "text/csv")})
    assert response.status_code == 200
    assert heard == []


def test_add_upload_listener_takes_a_callable() -> None:
    with pytest.raises(TypeError):
        add_upload_listener(FastAPI(), "not callable")  # type: ignore[arg-type]
