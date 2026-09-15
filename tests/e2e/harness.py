"""Drive a real ``scistudio serve`` process over HTTP and ``/ws`` (#2298).

The unit and integration suites call the FastAPI app in-process, so nothing
tests the product the way a user runs it: a server process, a project on disk,
drop-in blocks discovered from files, workflow runs in worker processes, and
the GUI's WebSocket protocol. This harness does exactly that and nothing more.

- :class:`ServeProcess` starts ``python -m scistudio serve`` on a free local
  port with ``HOME``/``USERPROFILE`` and every SciStudio store pointed into a
  temporary directory, so a run never touches the developer's real library,
  logs, or recent-projects list.
- :class:`Backend` is a thin HTTP client for the endpoints the GUI uses.
- :class:`EventStream` is one GUI WebSocket session. Keep it open while a run
  is in flight: the server cancels runs a short grace period after the last GUI
  socket disconnects (``api/ws.py``), exactly as it does for a closed window.
- :func:`build_tutorial_project` builds a project the way the Learning Center
  does, by copying a core tutorial's shipped assets into it.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as ws_connect

E2E_ENABLED = os.environ.get("SCISTUDIO_RUN_E2E") == "1"

#: Skip marker for every e2e test module: the suite starts a real server.
requires_e2e = pytest.mark.skipif(
    not E2E_ENABLED,
    reason="headless e2e starts a real server; set SCISTUDIO_RUN_E2E=1 to run it",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_TUTORIALS = REPO_ROOT / "src" / "scistudio" / "tutorials" / "core"

TERMINAL_RUN_STATES = frozenset({"completed", "failed", "cancelled"})

# Variables that would point the child at another engine, project, or mount.
_INHERITED_ENV_TO_DROP = (
    "SCISTUDIO_ENGINE_API_URL",
    "SCISTUDIO_ENGINE_IPC_TOKEN",
    "SCISTUDIO_ROOT_PATH",
    "SCISTUDIO_BUNDLED",
    "SCISTUDIO_PROJECT_DIR",
    "SCISTUDIO_HOST",
)


def free_port() -> int:
    """Return a local TCP port that is free right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def isolated_env(home: Path) -> dict[str, str]:
    """Environment for a server whose every user-level path lives under ``home``."""
    env = {key: value for key, value in os.environ.items() if key not in _INHERITED_ENV_TO_DROP}
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "SCISTUDIO_STORE": str(home / "store"),
            "SCISTUDIO_LOG_DIR": str(home / "logs"),
            "SCISTUDIO_ARTIFACT_RETENTION": "0",
            # Projects are git repositories; give their commits an identity
            # without reading the developer's global git config.
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "SciStudio E2E",
            "GIT_AUTHOR_EMAIL": "e2e@scistudio.invalid",
            "GIT_COMMITTER_NAME": "SciStudio E2E",
            "GIT_COMMITTER_EMAIL": "e2e@scistudio.invalid",
            # Run the checkout under test, not whatever copy is installed.
            "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO_ROOT / "src"), os.environ.get("PYTHONPATH")])),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


class ServeProcess:
    """One ``scistudio serve`` subprocess on 127.0.0.1."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.log_path = home / "serve.log"
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: Any = None

    def start(self, timeout: float = 120.0) -> None:
        """Start the server and wait until it answers ``/api/version``."""
        self.home.mkdir(parents=True, exist_ok=True)
        self._log = self.log_path.open("wb")
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "scistudio", "serve", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=self.home,
            env=isolated_env(self.home),
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"scistudio serve exited with {self._proc.returncode}:\n{self.log_tail()}")
            try:
                if httpx.get(f"{self.base_url}/api/version", timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        self.stop()
        raise TimeoutError(f"scistudio serve was not ready after {timeout:.0f}s:\n{self.log_tail()}")

    def log_tail(self, lines: int = 80) -> str:
        """The last lines the server wrote, for failure messages."""
        if self._log is not None:
            self._log.flush()
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(no server log)"
        return "\n".join(text.splitlines()[-lines:])

    def stop(self) -> None:
        """Stop the server; kill it if it does not exit promptly."""
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=15)
        if self._log is not None:
            self._log.close()
            self._log = None


class Backend:
    """HTTP calls the GUI makes, with failures that show the server's answer."""

    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=60.0)

    def close(self) -> None:
        self.http.close()

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise AssertionError(f"{method} {path} -> {response.status_code}: {response.text[:2000]}")
        return response.json() if response.content else None

    def create_project(self, name: str, parent: Path) -> dict[str, Any]:
        """Create a project under ``parent`` and make it the active project."""
        project: dict[str, Any] = self.call(
            "POST", "/api/projects/", json={"name": name, "description": "headless e2e", "path": str(parent)}
        )
        return project

    def reload_registries(self) -> dict[str, Any]:
        """Re-scan the project's drop-in types, blocks, and previewers."""
        result: dict[str, Any] = self.call("POST", "/api/blocks/reload")
        return result

    def put_workflow(self, definition: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = self.call("PUT", f"/api/workflows/{definition['id']}", json=definition)
        return result

    def run_ids(self, workflow_id: str) -> list[str]:
        page = self.call("GET", "/api/runs", params={"workflow_id": workflow_id, "limit": 500})
        return [str(row["run_id"]) for row in page["runs"]]

    def execute(self, workflow_id: str, timeout: float = 30.0) -> str:
        """Start ``workflow_id`` and return the new run's id.

        ``POST .../execute`` answers before the run row exists and does not
        name the run, so wait for a run id that was not there before.
        """
        before = set(self.run_ids(workflow_id))
        started = self.call("POST", f"/api/workflows/{workflow_id}/execute")
        assert started["status"] == "started", started
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = [run_id for run_id in self.run_ids(workflow_id) if run_id not in before]
            if new:
                return new[0]
            time.sleep(0.2)
        raise AssertionError(f"no run of {workflow_id!r} appeared within {timeout:.0f}s")

    def run(self, run_id: str) -> dict[str, Any]:
        """The lineage record: ``{"run": {...}, "block_executions": [...]}``."""
        result: dict[str, Any] = self.call("GET", f"/api/runs/{run_id}")
        return result

    def wait_for_run(self, run_id: str, timeout: float = 180.0) -> dict[str, Any]:
        """Poll the lineage record until the run reaches a terminal status.

        The ``workflow_completed`` event fires before the record is finalized,
        so the record, not the event, is the source of truth for the outcome.
        """
        deadline = time.monotonic() + timeout
        record = self.run(run_id)
        while time.monotonic() < deadline:
            if record["run"].get("status") in TERMINAL_RUN_STATES:
                return record
            time.sleep(0.25)
            record = self.run(run_id)
        raise AssertionError(f"run {run_id} still {record['run'].get('status')!r} after {timeout:.0f}s")

    def open_preview(self, ref: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        """Open a routed preview session for a data ref and return its first envelope."""
        envelope: dict[str, Any] = self.call(
            "POST", "/api/previews/sessions", json={"target": {"kind": "data_ref", "ref": ref}, "query": query or {}}
        )
        return envelope

    def open_panel(self, ref: str, kind: str = "data_ref") -> str:
        """Open the panel context a mounted panel reads through, as the GUI does.

        A core previewer is a panel now, so what the session envelope used to
        carry in its payload is fetched by the panel itself. A test asking
        whether an output is previewable has to follow the same path the frame
        does, or it is asserting against a shape nothing produces.
        """
        context: dict[str, Any] = self.call(
            "POST", "/api/panels/contexts", json={"kind": "preview", "target": {"kind": kind, "ref": ref}}
        )
        return str(context["context_id"])

    def panel_read(self, context_id: str, ref: str, op: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform one bounded panel read against an open context."""
        result: dict[str, Any] = self.call(
            "POST",
            f"/api/panels/contexts/{context_id}/read",
            json={"ref": ref, "op": op, "params": params or {}},
        )
        return result


class EventStream:
    """One GUI WebSocket session on ``/ws``, read on a background thread."""

    def __init__(self, base_url: str) -> None:
        self._ws = ws_connect(base_url.replace("http", "ws", 1) + "/ws", open_timeout=15, max_size=None)
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self.seen: list[dict[str, Any]] = []
        self._reader = threading.Thread(target=self._read, name="e2e-ws-reader", daemon=True)
        self._reader.start()

    def _read(self) -> None:
        try:
            for raw in self._ws:
                self._inbox.put(json.loads(raw))
        except ConnectionClosed:
            pass

    def send(self, message: dict[str, Any]) -> None:
        self._ws.send(json.dumps(message))

    def wait_for(
        self, predicate: Callable[[dict[str, Any]], bool], *, what: str, timeout: float = 180.0
    ) -> dict[str, Any]:
        """Return the next message matching ``predicate``; fail after ``timeout``."""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                message = self._inbox.get(timeout=remaining)
            except queue.Empty:
                break
            self.seen.append(message)
            if predicate(message):
                return message
        recent = [(m.get("type"), m.get("block_id")) for m in self.seen[-40:]]
        raise AssertionError(f"timed out after {timeout:.0f}s waiting for {what}; recent events: {recent}")

    def wait_for_event(self, event_type: str, block_id: str | None = None, timeout: float = 180.0) -> dict[str, Any]:
        return self.wait_for(
            lambda m: m.get("type") == event_type and (block_id is None or m.get("block_id") == block_id),
            what=f"{event_type} for {block_id or 'any block'}",
            timeout=timeout,
        )

    def close(self) -> None:
        self._ws.close()
        self._reader.join(timeout=5)


@dataclass(frozen=True)
class Project:
    id: str
    path: Path


def copy_asset(source: Path, destination: Path) -> None:
    """Copy one tutorial asset (a file or a directory's contents) into a project."""
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_tutorial_project(
    backend: Backend,
    parent: Path,
    *,
    name: str,
    tutorial: str,
    copies: Sequence[tuple[str, str]],
) -> Project:
    """Create a project and copy a core tutorial's assets into it.

    ``copies`` mirrors the tutorial's own ``copy: {source, destination}`` steps:
    ``source`` is relative to ``src/scistudio/tutorials/core/<tutorial>/`` and
    ``destination`` to the project root. The registries are re-scanned
    afterwards so drop-in types, blocks, and previewers are live.
    """
    tutorial_dir = CORE_TUTORIALS / tutorial
    created = backend.create_project(name, parent)
    project = Project(id=str(created["id"]), path=Path(created["path"]))
    for source, destination in copies:
        copy_asset(tutorial_dir / source, project.path / destination)
    backend.reload_registries()
    return project
