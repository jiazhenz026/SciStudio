"""#2333 — the local MCP socket is owner-only whatever the umask, with a private fallback.

The local MCP transport has no authentication beyond the socket's file
permissions, so on POSIX:

* the socket is bound in an owner-only (0700) directory and set to 0600, even
  under a permissive umask such as 002;
* a project directory that is open to other users is left as it is, and the
  socket moves to the private per-user directory, which ``mcp.sock.path``
  names so ``scistudio mcp-bridge`` still finds it;
* the per-user directory (``$XDG_RUNTIME_DIR/scistudio``, else
  ``scistudio-<uid>`` under the temp dir) is private, and a hostile one is
  refused.

Windows binds TCP loopback (``mcp.sock.port``) instead, an assumption the
server module documents; only the pure directory rule runs there.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from scistudio.ai.agent.mcp import server as server_module
from scistudio.ai.agent.mcp.server import MCPServer, socket_dir_problem

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX Unix-socket permissions; Windows binds TCP loopback, as server.py documents",
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def _fake_stat(kind: int, mode: int, uid: int) -> os.stat_result:
    return os.stat_result((kind | mode, 0, 0, 1, uid, uid, 0, 0, 0, 0))


def test_socket_directory_rule() -> None:
    """The rule itself, on every platform, with explicit stat values."""
    assert socket_dir_problem(_fake_stat(stat.S_IFDIR, 0o700, 1000), uid=1000) is None
    open_dir = socket_dir_problem(_fake_stat(stat.S_IFDIR, 0o755, 1000), uid=1000)
    assert open_dir is not None and "mode 0755" in open_dir
    assert socket_dir_problem(_fake_stat(stat.S_IFDIR, 0o770, 1000), uid=1000) is not None
    foreign = socket_dir_problem(_fake_stat(stat.S_IFDIR, 0o700, 1001), uid=1000)
    assert foreign is not None and "not by the current user" in foreign
    link = socket_dir_problem(_fake_stat(stat.S_IFLNK, 0o777, 1000), uid=1000)
    assert link is not None and "symbolic link" in link


@pytest.fixture()
def short_dir() -> Iterator[Path]:
    """A short private base: pytest's ``tmp_path`` can overflow ``sun_path`` on macOS."""
    path = Path(tempfile.mkdtemp(prefix="sst-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def runtime_dir(short_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``XDG_RUNTIME_DIR`` at a private directory so the real one is never touched."""
    xdg = short_dir / "xdg"
    xdg.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    return xdg


@pytest.fixture()
def umask_002() -> Iterator[None]:
    previous = os.umask(0o002)
    try:
        yield
    finally:
        os.umask(previous)


@posix_only
@pytest.mark.usefixtures("runtime_dir", "umask_002")
def test_requested_directory_and_socket_are_owner_only_under_umask_002(short_dir: Path) -> None:
    project = short_dir / "proj"
    project.mkdir()
    requested = project / ".scistudio" / "mcp.sock"

    async def scenario() -> None:
        server = MCPServer(socket_path=requested, project_dir=project)
        await server.start()
        try:
            assert server.socket_path == requested
            assert _mode(requested.parent) == 0o700
            assert stat.S_ISSOCK(os.lstat(requested).st_mode)
            assert _mode(requested) == 0o600
            assert not (requested.parent / "mcp.sock.path").exists()
        finally:
            await server.stop()
        assert not requested.exists()

    asyncio.run(scenario())


@posix_only
@pytest.mark.usefixtures("umask_002")
def test_shared_project_directory_is_not_reused_and_the_bridge_still_finds_the_socket(
    short_dir: Path, runtime_dir: Path
) -> None:
    from scistudio.cli import mcp_bridge

    project = short_dir / "proj"
    shared = project / ".scistudio"
    shared.mkdir(parents=True)
    shared.chmod(0o775)  # a lab's group-shared project directory
    requested = shared / "mcp.sock"

    async def scenario() -> None:
        server = MCPServer(socket_path=requested, project_dir=project)
        await server.start()
        bound = server.socket_path
        client = None
        try:
            assert bound != requested
            assert bound.parent == runtime_dir / "scistudio"
            assert _mode(bound.parent) == 0o700
            assert _mode(bound) == 0o600
            assert _mode(shared) == 0o775, "the project's own directory is left as it is"
            assert not requested.exists()
            assert (shared / "mcp.sock.path").read_text(encoding="utf-8") == str(bound)
            # Discovery: the bridge client follows the pointer to the private socket.
            assert mcp_bridge._posix_socket_connect_path(requested) == bound
            client = await asyncio.to_thread(mcp_bridge._try_connect_attached, project)
            assert client is not None
            # Keep the client attached until the server has registered it, so
            # stop() hangs up on it and drains its transport inside the
            # coroutine. A server transport left to the garbage collector
            # raises out of __del__ on Python 3.13 (see MCPServer.stop, #2019).
            for _ in range(200):
                if server._clients:
                    break
                await asyncio.sleep(0.01)
            assert server._clients, "the server never registered the bridge's connection"
        finally:
            await asyncio.wait_for(server.stop(), timeout=10)
            if client is not None:
                client.close()
        assert not bound.exists()
        assert not (shared / "mcp.sock.path").exists()

    asyncio.run(scenario())


@posix_only
def test_overlong_path_falls_back_to_the_private_directory(short_dir: Path, runtime_dir: Path) -> None:
    project = short_dir / ("p" * 40) / ("q" * 40)
    project.mkdir(parents=True)
    requested = project / ".scistudio" / "mcp.sock"
    assert len(str(requested).encode("utf-8")) > 100

    async def scenario() -> None:
        server = MCPServer(socket_path=requested, project_dir=project)
        await server.start()
        try:
            assert server.socket_path.parent == runtime_dir / "scistudio"
            assert _mode(server.socket_path) == 0o600
            pointer = requested.with_suffix(".sock.path")
            assert pointer.read_text(encoding="utf-8") == str(server.socket_path)
        finally:
            await server.stop()

    asyncio.run(scenario())


@posix_only
@pytest.mark.usefixtures("umask_002")
def test_private_directory_prefers_xdg_runtime_dir(runtime_dir: Path) -> None:
    path = server_module.private_socket_dir()
    assert path == runtime_dir / "scistudio"
    assert _mode(path) == 0o700


@posix_only
@pytest.mark.usefixtures("umask_002")
def test_private_directory_falls_back_to_a_per_user_temp_directory(
    short_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(short_dir))
    path = server_module.private_socket_dir()
    assert path == short_dir / f"scistudio-{os.getuid()}"
    assert _mode(path) == 0o700
    assert os.lstat(path).st_uid == os.getuid()


@posix_only
@pytest.mark.parametrize("hostile", ["open-to-others", "symlink"])
def test_hostile_private_directory_is_refused(short_dir: Path, runtime_dir: Path, hostile: str) -> None:
    target = runtime_dir / "scistudio"
    if hostile == "open-to-others":
        target.mkdir()
        target.chmod(0o777)
    else:
        elsewhere = short_dir / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        target.symlink_to(elsewhere)
    with pytest.raises(PermissionError, match="refusing MCP socket directory"):
        server_module.private_socket_dir()

    # A server that needs the fallback refuses to bind rather than use it.
    project = short_dir / "proj"
    shared = project / ".scistudio"
    shared.mkdir(parents=True)
    shared.chmod(0o755)
    server = MCPServer(socket_path=shared / "mcp.sock", project_dir=project)
    with pytest.raises(PermissionError):
        asyncio.run(server.start())
    assert not (shared / "mcp.sock").exists()


@posix_only
def test_standalone_bridge_socket_without_a_project_is_private(
    runtime_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.ai.agent.mcp import runtime as runtime_module

    monkeypatch.setattr(runtime_module, "make_mcp_runtime", lambda project_dir: object())

    async def scenario() -> None:
        server, _ = await runtime_module.start_inprocess_server(None)
        try:
            assert server.socket_path == runtime_dir / "scistudio" / f"mcp-bridge-{os.getpid()}.sock"
            assert _mode(server.socket_path) == 0o600
        finally:
            await runtime_module.stop_inprocess_server(server)

    asyncio.run(scenario())


@posix_only
@pytest.mark.usefixtures("umask_002")
def test_taken_over_temp_fallback_moves_to_a_unique_private_directory(
    short_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No-context audit P3-6: another user holding ``scistudio-<uid>`` does not stop the server."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(short_dir))
    monkeypatch.setattr(server_module, "_fallback_socket_dir", None)
    planted = short_dir / "planted"
    planted.mkdir()
    (short_dir / f"scistudio-{os.getuid()}").symlink_to(planted)  # someone got there first

    path = server_module.private_socket_dir()
    assert path.parent == short_dir
    assert path.name.startswith(f"scistudio-{os.getuid()}-")
    assert _mode(path) == 0o700
    assert server_module.private_socket_dir() == path, "reused for the life of the process"

    project = short_dir / "proj"
    shared = project / ".scistudio"
    shared.mkdir(parents=True)
    shared.chmod(0o755)
    requested = shared / "mcp.sock"

    async def scenario() -> None:
        server = MCPServer(socket_path=requested, project_dir=project)
        await server.start()
        try:
            assert server.socket_path.parent == path
            assert (shared / "mcp.sock.path").read_text(encoding="utf-8") == str(server.socket_path)
        finally:
            await server.stop()

    asyncio.run(scenario())


@posix_only
def test_xdg_runtime_dir_open_to_others_is_not_used(short_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xdg = short_dir / "xdg-open"
    xdg.mkdir()
    xdg.chmod(0o777)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    monkeypatch.setattr(tempfile, "tempdir", str(short_dir))
    assert server_module.private_socket_dir() == short_dir / f"scistudio-{os.getuid()}"


@posix_only
@pytest.mark.usefixtures("runtime_dir")
def test_socket_is_created_owner_only_before_any_chmod(short_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No-context audit P3-6: bound under a 0077 umask, so no window exists before the chmod."""
    project = short_dir / "proj"
    project.mkdir()
    requested = project / ".scistudio" / "mcp.sock"
    real_chmod = os.chmod

    def chmod(path: object, mode: int, *args: object, **kwargs: object) -> None:
        if Path(str(path)) == requested:
            return  # skip the socket's chmod: observe the mode bind produced
        real_chmod(path, mode, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(server_module.os, "chmod", chmod)
    previous = os.umask(0)
    try:

        async def scenario() -> None:
            server = MCPServer(socket_path=requested, project_dir=project)
            await server.start()
            try:
                assert _mode(requested) & 0o077 == 0
            finally:
                await server.stop()

        asyncio.run(scenario())
        assert os.umask(0) == 0, "the process umask is restored after the bind"
    finally:
        os.umask(previous)
