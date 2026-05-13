"""End-to-end test harness for the microplastics acceptance test.

This module owns the *infrastructure* for driving the SciEasy embedded coding
agent through a real workflow build. It does **NOT** touch the workflow YAML,
custom blocks, or the canvas — those are produced by the agent under test.

Per ADR-033 spec §8.5 T-ECA-502.

Lifecycle (mandated by the spec):

    1. Launch the SciEasy backend (``scieasy serve``) as a subprocess.
    2. Wait for ``/api/ai/status`` to become reachable.
    3. Create a fresh project workspace under a tmp directory.
    4. Open the chat tab and send the test prompt.
    5. Wait for the agent to emit a terminal ``done`` envelope or time out.
    6. Persist transcript, workflow YAML, run outputs to
       ``tests/e2e/runs/<timestamp>/`` for after-the-fact inspection.
    7. Tear down the backend.

Browser automation note
-----------------------
The spec authorises three browser-driving strategies:

    * ``claude-in-chrome`` MCP tools (preferred when the dispatcher session has
      them loaded).
    * Playwright + Chromium (fallback if Playwright is in dev deps).
    * HTTP-/WS-only harness (documented fallback when neither is available).

This implementation provides the **HTTP/WS-only** code path. The browser-
driven path will be added by T-ECA-505 alongside the actual test body; the
class is structured so a `BrowserDriver` strategy can be plugged in without
rewriting the lifecycle code.

Stability
---------
This harness is exercised only under ``pytest -m e2e``. Default CI
(``pytest -n auto --timeout=60 -m 'not e2e'``) never imports it, so the
subprocess machinery does not affect the unit-test gate.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default backend bind. The harness will pick a free port if 8000 is busy.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_HEALTH_TIMEOUT_S = 30.0
DEFAULT_AGENT_TIMEOUT_S = 1800.0  # 30 min per spec §8.5

# Module-level repository root anchor (tests/e2e/harness.py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNS_DIR = Path(__file__).resolve().parent / "runs"


def _default_server_cmd(host: str, port: int) -> tuple[str, ...]:
    """Build the canonical uvicorn argv for the SciEasy backend.

    Mirrors ``scieasy serve`` (``src/scieasy/cli/main.py``): runs
    ``uvicorn scieasy.api.app:create_app --factory`` so the lifespan that
    sets up :class:`ApiRuntime` and the MCP server actually runs. The
    earlier shape ``python -m scieasy.api.app`` was a stub that does not
    exist as a runnable module (P1 from #771).
    """
    return (
        sys.executable,
        "-m",
        "uvicorn",
        "scieasy.api.app:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    )


def _pick_free_port(preferred: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> int:
    """Return ``preferred`` if it binds, otherwise an OS-assigned free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


# Module-level opener that bypasses any system proxy. ``urllib.request.urlopen``
# silently picks up ``HTTP_PROXY`` / ``HTTPS_PROXY`` (and on Windows the IE
# proxy settings), which on a corporate machine can route loopback traffic
# through a proxy and produce sub-second timeouts against ``127.0.0.1``. The
# harness only ever talks to the backend it spawned, so an empty ProxyHandler
# is always correct.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_open(req_or_url: urllib.request.Request | str, *, timeout: float) -> Any:
    """Open ``req_or_url`` through the no-proxy opener with ``timeout``."""
    return _NO_PROXY_OPENER.open(req_or_url, timeout=timeout)


def _drain_stream_to_log(stream: Any, log_path: Path, label: str) -> None:
    """Copy a subprocess pipe to ``log_path`` line by line.

    Used by :meth:`MicroplasticsHarness.setup` to keep the backend's
    stdout/stderr pipes from filling and blocking the server. Each line
    is prefixed with ``[{label}]`` so stdout and stderr can be separated
    after the fact. The function returns when the pipe closes.
    """
    try:
        with log_path.open("ab") as fh:
            for line in iter(stream.readline, b""):
                if not line:
                    break
                fh.write(label.encode() + b": " + line)
                fh.flush()
    except (OSError, ValueError):
        # ValueError is raised when ``stream`` is closed during teardown;
        # OSError can fire on Windows when the pipe handle goes away.
        return


@dataclass
class HarnessConfig:
    """Configuration knobs for :class:`MicroplasticsHarness`.

    All fields have sensible defaults; tests typically only override
    ``prompt`` and ``agent_timeout_s``.
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    health_timeout_s: float = DEFAULT_HEALTH_TIMEOUT_S
    agent_timeout_s: float = DEFAULT_AGENT_TIMEOUT_S
    # Path the agent writes its outputs to. Resolved at setup() time.
    project_workspace: Path | None = None
    runs_root: Path = _RUNS_DIR
    # Server argv. If left as ``None`` (the default) the harness will build
    # the canonical uvicorn invocation via :func:`_default_server_cmd` at
    # setup() time using the final host/port (a free port may be substituted
    # before launch). Explicit overrides are honoured as-is — useful for
    # tests that want to point at a stub.
    server_cmd: tuple[str, ...] | None = None
    # If True, the harness preserves the project workspace and run artifacts
    # even on teardown. Useful for debugging; CI invocations typically leave
    # this False.
    preserve_workspace: bool = False


@dataclass
class HarnessArtifacts:
    """File-level outputs captured from a single run.

    Populated incrementally by harness methods. Consumers read these paths
    after :meth:`MicroplasticsHarness.capture`.
    """

    run_dir: Path
    transcript_path: Path
    workflow_yaml_path: Path
    project_state_path: Path
    errors_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


class MicroplasticsHarness:
    """Drive the SciEasy embedded coding agent end-to-end for one run.

    Usage (intended to be called by ``T-ECA-505``)::

        config = HarnessConfig()
        harness = MicroplasticsHarness(config)
        harness.setup()
        try:
            chat_id = harness.create_project()
            harness.open_chat(chat_id)
            harness.send_prompt("...prompt body...")
            harness.wait_for_done(timeout=1800)
            artifacts = harness.capture()
        finally:
            harness.teardown()

    The class is **stateful** and not thread-safe. One instance == one run.
    """

    def __init__(self, config: HarnessConfig | None = None) -> None:
        self.config = config or HarnessConfig()
        self._server_proc: subprocess.Popen[bytes] | None = None
        self._server_log_path: Path | None = None
        self._server_log_threads: list[threading.Thread] = []
        self._chat_id: str | None = None
        self._project_id: str | None = None
        self._run_dir: Path | None = None
        self._transcript_events: list[dict[str, Any]] = []
        self._started_at: float | None = None

    # ------------------------------------------------------------------ lifecycle

    def setup(self) -> None:
        """Launch the backend and wait for it to be healthy.

        Raises
        ------
        RuntimeError
            If ``/api/ai/status`` is not reachable within ``health_timeout_s``.
        """
        # Bind to a free port if the requested one is busy.
        self.config.port = _pick_free_port(self.config.port, self.config.host)

        # Allocate the runs/<timestamp>/ directory eagerly so partial-failure
        # capture still has somewhere to land.
        self._run_dir = self.config.runs_root / _timestamp()
        self._run_dir.mkdir(parents=True, exist_ok=True)

        # Allocate a project workspace if the caller did not supply one.
        if self.config.project_workspace is None:
            self.config.project_workspace = Path(tempfile.mkdtemp(prefix="scieasy-e2e-", dir=str(self._run_dir)))
        self.config.project_workspace.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["SCIEASY_HOST"] = self.config.host
        env["SCIEASY_PORT"] = str(self.config.port)
        env["SCIEASY_PROJECT_DIR"] = str(self.config.project_workspace)

        # Build the default server_cmd now that we know the final port.
        # Explicit overrides (set by the caller) are honoured unchanged.
        server_cmd = self.config.server_cmd or _default_server_cmd(self.config.host, self.config.port)

        self._server_proc = subprocess.Popen(
            list(server_cmd),
            cwd=str(_REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Drain stdout+stderr to a log file in a background thread. Without
        # this the server's INFO logs + the type-registry warnings rapidly
        # fill the OS pipe buffer (~64 KB on Windows) and the backend
        # blocks at startup before it ever binds the listening socket.
        self._server_log_path = self._run_dir / "server.log"
        self._server_log_threads = []
        for stream, name in (
            (self._server_proc.stdout, "stdout"),
            (self._server_proc.stderr, "stderr"),
        ):
            if stream is None:
                continue
            t = threading.Thread(
                target=_drain_stream_to_log,
                args=(stream, self._server_log_path, name),
                daemon=True,
            )
            t.start()
            self._server_log_threads.append(t)

        # Poll /api/ai/status.
        deadline = time.monotonic() + self.config.health_timeout_s
        url = f"http://{self.config.host}:{self.config.port}/api/ai/status"
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if self._server_proc.poll() is not None:
                # Drain threads own the pipes now; tail the log file for
                # the post-mortem details.
                tail = b""
                if self._server_log_path and self._server_log_path.exists():
                    with contextlib.suppress(OSError):
                        tail = self._server_log_path.read_bytes()[-4000:]
                raise RuntimeError(
                    f"scieasy backend exited early (rc={self._server_proc.returncode}); log tail={tail!r}"
                )
            try:
                with _http_open(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        self._started_at = time.monotonic()
                        return
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_err = exc
                time.sleep(0.25)
        raise RuntimeError(
            f"Backend /api/ai/status did not become reachable within "
            f"{self.config.health_timeout_s}s; last error: {last_err!r}"
        )

    def create_project(self, name: str | None = None, description: str = "") -> str:
        """Create a fresh project and return the WebSocket chat_id.

        Issues ``POST /api/projects/`` against the real backend schema
        (:class:`scieasy.api.schemas.ProjectCreate`: ``name``,
        ``description``, ``path``). The previous wire shape
        ``{"workspace": ...}`` did not match the route and was the second
        P1 from #771.

        The backend's project entity has its own id, which is recorded as
        ``project_id`` on this instance. The WebSocket chat session is
        identified by a free-form ``chat_id`` (see
        ``scieasy.api.routes.ai.chat_ws`` — ``chat_id: str`` path param),
        so the harness mints a uuid here and returns it. Tests should
        call this once between :meth:`setup` and :meth:`send_prompt`.
        """
        if self.config.project_workspace is None:
            raise RuntimeError("create_project called before setup")
        workspace = self.config.project_workspace
        project_name = name or f"e2e-{_timestamp()}-{workspace.name}"

        url = f"http://{self.config.host}:{self.config.port}/api/projects/"
        body = json.dumps(
            {
                "name": project_name,
                "description": description,
                "path": str(workspace),
            }
        ).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with _http_open(req, timeout=10.0) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"create_project failed: HTTP {exc.code} {exc.reason}") from exc
        project_id = payload.get("id")
        if not project_id:
            raise RuntimeError(f"Backend did not return a project id; payload={payload!r}")
        self._project_id = str(project_id)
        # The chat_id is a WS-scope identifier, distinct from the project
        # id. Mint a uuid so reconnect/resume logic works deterministically.
        self._chat_id = f"e2e-{uuid.uuid4()}"
        return self._chat_id

    def open_chat(self, chat_id: str | None = None) -> None:
        """Bind the harness to an existing chat session.

        In the HTTP-only harness path this is a no-op state-change. In a
        browser-driven implementation it would navigate the page to the
        chat tab. Kept as a separate method so T-ECA-505's browser driver
        can override exactly this step.
        """
        if chat_id is not None:
            self._chat_id = str(chat_id)
        if self._chat_id is None:
            raise RuntimeError("open_chat called before create_project")

    def chat_ws_url(self) -> str:
        """Return the canonical WebSocket URL for the active chat session.

        Path: ``/api/ai/chat/{chat_id}``; required query: ``project_dir``.
        Exposed as a helper so :meth:`send_prompt` and unit tests share
        one source of truth.
        """
        if self._chat_id is None:
            raise RuntimeError("chat_ws_url called before create_project/open_chat")
        if self.config.project_workspace is None:
            raise RuntimeError("chat_ws_url called before setup")
        query = urllib.parse.urlencode({"project_dir": str(self.config.project_workspace)})
        return f"ws://{self.config.host}:{self.config.port}/api/ai/chat/{self._chat_id}?{query}"

    def send_prompt(self, text: str) -> None:
        """Send ``text`` to the agent over the chat WebSocket.

        Opens (lazily) the bidirectional WebSocket at
        ``/api/ai/chat/{chat_id}?project_dir=...`` (the real
        implementation in :mod:`scieasy.api.routes.ai`) and emits the
        canonical ``{"type": "user_message", "content": ...}`` frame.

        The earlier shape — POST to ``/api/chats/{id}/messages`` — was
        the third P1 from #771: that REST surface does not exist; chat
        is WebSocket-only per ADR-033 §3 D5.2.

        The WebSocket is kept open for :meth:`wait_for_done` to drain
        ``agent_event`` frames. Callers should not invoke ``send_prompt``
        twice without first awaiting :meth:`wait_for_done`.
        """
        if self._chat_id is None:
            raise RuntimeError("send_prompt called before create_project/open_chat")

        # Lazy-import the WS client so a missing optional dep does not break
        # the rest of the module at collection time. ``websockets`` is a
        # transitive dependency via ``uvicorn[standard]``, but importing
        # it eagerly would couple harness *collection* (which runs in the
        # default unit-test pass for unit tests of the harness itself) to
        # the runtime dep.
        from websockets.sync.client import connect as _ws_connect  # type: ignore[import-not-found]

        url = self.chat_ws_url()
        # Open and stash on the instance so wait_for_done can keep reading.
        self._ws_conn = _ws_connect(url, open_timeout=10.0)
        self._ws_conn.send(json.dumps({"type": "user_message", "content": text}))
        # Mark the wall clock origin so wait_for_done can enforce its timeout.
        self._started_at = time.monotonic()

    def wait_for_done(self, timeout: float | None = None) -> dict[str, Any]:
        """Block until the agent emits a terminal envelope or times out.

        Drains ``agent_event`` envelopes from the chat WebSocket opened
        by :meth:`send_prompt`. Each inbound JSON envelope is recorded on
        the transcript; the method returns when the inner event's
        ``kind`` is ``"done"`` or ``"error"`` (server-side terminal
        signals per ADR-033). ``error``-type top-level frames also
        terminate.

        Parameters
        ----------
        timeout : float, optional
            Wall-clock seconds. Defaults to ``agent_timeout_s`` from the
            config.

        Returns
        -------
        dict
            The terminal envelope. Always recorded on the transcript first.
        """
        if self._chat_id is None:
            raise RuntimeError("wait_for_done called before send_prompt")
        ws = getattr(self, "_ws_conn", None)
        if ws is None:
            raise RuntimeError("wait_for_done called before send_prompt opened a WebSocket")
        timeout_s = timeout if timeout is not None else self.config.agent_timeout_s
        deadline = (self._started_at or time.monotonic()) + timeout_s

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Agent did not finish within {timeout_s}s (captured {len(self._transcript_events)} events)"
                    )
                try:
                    raw = ws.recv(timeout=min(remaining, 5.0))
                except TimeoutError:
                    # ``websockets.sync`` raises TimeoutError on recv timeout;
                    # loop back so the outer deadline check fires when due.
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._transcript_events.append(envelope)

                env_type = envelope.get("type")
                if env_type == "error":
                    return envelope
                inner = envelope.get("event") or {}
                kind = inner.get("kind")
                if kind in {"done", "error"}:
                    return envelope
        finally:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                ws.close()
            self._ws_conn = None

    def capture(self) -> HarnessArtifacts:
        """Dump transcript + workflow YAML + project state under runs/<ts>/.

        Returns
        -------
        HarnessArtifacts
            Paths to each captured artefact. Always populated even if a
            given artefact could not be read (an empty file is written so
            callers can rely on path existence).
        """
        if self._run_dir is None:
            raise RuntimeError("capture called before setup")
        run_dir = self._run_dir
        transcript_path = run_dir / "transcript.ndjson"
        workflow_path = run_dir / "workflow.yaml"
        state_path = run_dir / "project_state.json"
        errors_path = run_dir / "errors.log"

        # Transcript: the in-memory accumulator from wait_for_done.
        with transcript_path.open("w", encoding="utf-8") as fh:
            for evt in self._transcript_events:
                fh.write(json.dumps(evt) + "\n")

        # Workflow YAML and project-state dumps: these endpoints do not
        # exist yet (the chat-id-based REST paths originally referenced
        # here were P1 #771-adjacent dead ends). T-ECA-505 will design
        # the canonical capture surface; until then ``_dump_endpoint``
        # writes an empty file when the path is ``None``, preserving the
        # contract that every artefact path always exists.
        self._dump_endpoint(None, workflow_path, content_type="text")
        self._dump_endpoint(None, state_path, content_type="json")

        # Errors log: snapshot whatever the drain threads have written so
        # far. We do not stop the threads or close the subprocess here —
        # ``teardown`` handles that — so the file may keep growing after
        # ``capture`` returns. Best-effort copy.
        if self._server_log_path and self._server_log_path.exists():
            with contextlib.suppress(OSError):
                errors_path.write_bytes(self._server_log_path.read_bytes())
        else:
            errors_path.touch()

        metadata = {
            "host": self.config.host,
            "port": self.config.port,
            "project_workspace": str(self.config.project_workspace),
            "chat_id": self._chat_id,
            "event_count": len(self._transcript_events),
        }
        return HarnessArtifacts(
            run_dir=run_dir,
            transcript_path=transcript_path,
            workflow_yaml_path=workflow_path,
            project_state_path=state_path,
            errors_path=errors_path,
            metadata=metadata,
        )

    def teardown(self) -> None:
        """Stop the backend subprocess and clean up the workspace.

        Always safe to call (idempotent). Honours
        ``HarnessConfig.preserve_workspace`` for post-mortem inspection.
        """
        ws = getattr(self, "_ws_conn", None)
        if ws is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive teardown
                ws.close()
            self._ws_conn = None
        if self._server_proc is not None:
            try:
                self._server_proc.terminate()
                try:
                    self._server_proc.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    self._server_proc.kill()
                    self._server_proc.wait(timeout=5.0)
            except Exception:  # pragma: no cover - best-effort teardown
                pass
            finally:
                self._server_proc = None
        # After the process exits, the pipe-readers in the drain threads
        # will see EOF and return. Join briefly so we know the log file
        # is flushed by the time we delete the workspace.
        for thread in self._server_log_threads:
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                thread.join(timeout=2.0)
        self._server_log_threads = []

        if (
            not self.config.preserve_workspace
            and self.config.project_workspace
            and self.config.project_workspace.exists()
            and self._run_dir
            and self.config.project_workspace.is_relative_to(self._run_dir)
        ):
            # Only delete tmp workspaces we allocated under runs/<ts>/.
            shutil.rmtree(self.config.project_workspace, ignore_errors=True)

    # ------------------------------------------------------------------ helpers

    @property
    def chat_id(self) -> str | None:
        return self._chat_id

    @property
    def project_id(self) -> str | None:
        """The backend's project id from ``POST /api/projects/`` (None until create_project)."""
        return self._project_id

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    @property
    def transcript(self) -> list[dict[str, Any]]:
        """Read-only view of the collected stream-json events."""
        return list(self._transcript_events)

    def _dump_endpoint(
        self,
        path: str | None,
        dest: Path,
        content_type: str,
    ) -> None:
        """Fetch ``path`` from the backend and persist to ``dest``.

        Best-effort: writes an empty file on error so consumers can rely
        on path existence. The reason is appended to the errors log.
        """
        if not path:
            dest.touch()
            return
        url = f"http://{self.config.host}:{self.config.port}{path}"
        try:
            with _http_open(url, timeout=10.0) as resp:
                raw = resp.read()
            if content_type == "json":
                # Pretty-print for diff'ability.
                try:
                    parsed = json.loads(raw.decode())
                    dest.write_text(json.dumps(parsed, indent=2, sort_keys=True))
                    return
                except json.JSONDecodeError:
                    pass
            dest.write_bytes(raw)
        except Exception as exc:  # pragma: no cover - best-effort capture
            dest.touch()
            errs = (self._run_dir or Path(".")) / "errors.log"
            with errs.open("a", encoding="utf-8") as fh:
                fh.write(f"_dump_endpoint({path}): {exc!r}\n")


__all__: Iterable[str] = (
    "HarnessArtifacts",
    "HarnessConfig",
    "MicroplasticsHarness",
    "_default_server_cmd",
)
