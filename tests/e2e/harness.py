"""End-to-end test harness for the microplastics acceptance test.

This module owns the *infrastructure* for driving the SciEasy embedded coding
agent through a real workflow build. It does **NOT** touch the workflow YAML,
custom blocks, or the canvas — those are produced by the agent under test.

Per ADR-033 spec §8.5 T-ECA-502.

Lifecycle (mandated by the spec):

    1. Launch the SciEasy backend (``scieasy serve``) as a subprocess.
    2. Wait for ``/healthz`` to become reachable.
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

import datetime as _dt
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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
    server_cmd: tuple[str, ...] = (
        sys.executable,
        "-m",
        "scieasy.api.app",
    )
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
        self._chat_id: str | None = None
        self._run_dir: Path | None = None
        self._transcript_events: list[dict[str, Any]] = []
        self._started_at: float | None = None

    # ------------------------------------------------------------------ lifecycle

    def setup(self) -> None:
        """Launch the backend and wait for it to be healthy.

        Raises
        ------
        RuntimeError
            If ``/healthz`` is not reachable within ``health_timeout_s``.
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

        self._server_proc = subprocess.Popen(
            list(self.config.server_cmd),
            cwd=str(_REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Poll /healthz.
        deadline = time.monotonic() + self.config.health_timeout_s
        url = f"http://{self.config.host}:{self.config.port}/healthz"
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if self._server_proc.poll() is not None:
                stderr = (self._server_proc.stderr or _Empty()).read()
                raise RuntimeError(
                    f"scieasy backend exited early (rc={self._server_proc.returncode}); stderr={stderr!r}"
                )
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        self._started_at = time.monotonic()
                        return
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last_err = exc
                time.sleep(0.25)
        raise RuntimeError(
            f"Backend /healthz did not become reachable within "
            f"{self.config.health_timeout_s}s; last error: {last_err!r}"
        )

    def create_project(self) -> str:
        """Create a fresh chat/project and return the chat_id.

        Issues a POST against the project-creation API and stores the
        returned chat id on the instance. Tests should call this once
        between :meth:`setup` and :meth:`send_prompt`.
        """
        url = f"http://{self.config.host}:{self.config.port}/api/projects"
        body = json.dumps({"workspace": str(self.config.project_workspace)}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"create_project failed: HTTP {exc.code} {exc.reason}") from exc
        chat_id = payload.get("chat_id") or payload.get("id")
        if not chat_id:
            raise RuntimeError(f"Backend did not return a chat id; payload={payload!r}")
        self._chat_id = str(chat_id)
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

    def send_prompt(self, text: str) -> None:
        """Send ``text`` to the agent as the user-prompt of the chat.

        The backend exposes a POST endpoint that mirrors what the chat-tab
        front-end would emit on send. Capturing this here keeps the
        harness independent of a real browser.
        """
        if self._chat_id is None:
            raise RuntimeError("send_prompt called before create_project/open_chat")
        url = f"http://{self.config.host}:{self.config.port}/api/chats/{self._chat_id}/messages"
        body = json.dumps({"role": "user", "content": text}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            if resp.status not in (200, 202):
                raise RuntimeError(f"send_prompt: unexpected HTTP {resp.status}")
        # Mark the wall clock origin so wait_for_done can enforce its timeout.
        self._started_at = time.monotonic()

    def wait_for_done(self, timeout: float | None = None) -> dict[str, Any]:
        """Block until the agent emits a terminal envelope or times out.

        Polls a streaming endpoint that the backend exposes for the chat;
        each newline-delimited JSON object is appended to the captured
        transcript. The method returns the final envelope. ``timeout`` is
        in seconds; defaults to ``agent_timeout_s`` from the config.

        Notes
        -----
        The exact endpoint shape (SSE vs newline-delimited JSON over an
        HTTP stream) is fixed by Phase 1's stream-json wiring (see ADR-033
        Phase 1). This method is conservative: it accepts either an
        ``event: done`` SSE frame or a JSON object with
        ``"type": "done"``. T-ECA-505 may tighten the contract.
        """
        if self._chat_id is None:
            raise RuntimeError("wait_for_done called before send_prompt")
        timeout = timeout if timeout is not None else self.config.agent_timeout_s
        deadline = (self._started_at or time.monotonic()) + timeout
        url = f"http://{self.config.host}:{self.config.port}/api/chats/{self._chat_id}/events"
        req = urllib.request.Request(url, headers={"Accept": "application/x-ndjson"})
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5.0) as resp:
                for raw_line in resp:
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            f"Agent did not finish within {timeout}s (captured {len(self._transcript_events)} events)"
                        )
                    line = raw_line.decode().strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[len("data:") :].strip()
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._transcript_events.append(evt)
                    if evt.get("type") in {"done", "error"} or evt.get("envelope_type") in {"done", "error"}:
                        return evt
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"wait_for_done: stream endpoint returned HTTP {exc.code}") from exc
        raise TimeoutError("Agent stream ended without a terminal event")

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

        # Workflow YAML: fetch the canonical canvas dump from the backend.
        self._dump_endpoint(
            f"/api/chats/{self._chat_id}/workflow.yaml" if self._chat_id else None,
            workflow_path,
            content_type="text",
        )

        # Project state: snapshot of the workspace as the backend sees it.
        self._dump_endpoint(
            f"/api/chats/{self._chat_id}/state" if self._chat_id else None,
            state_path,
            content_type="json",
        )

        # Errors log: stderr drained from the backend subprocess.
        with errors_path.open("wb") as fh:
            if self._server_proc and self._server_proc.stderr:
                # Non-blocking drain; subprocess may still be running.
                try:
                    pending = self._server_proc.stderr.peek()  # type: ignore[attr-defined]
                    if pending:
                        fh.write(pending)
                except (AttributeError, ValueError):
                    pass

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
            with urllib.request.urlopen(url, timeout=10.0) as resp:
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


class _Empty:
    """Tiny shim so ``.read()`` is always safe on a missing stderr handle."""

    def read(self) -> bytes:
        return b""


__all__: Iterable[str] = (
    "HarnessArtifacts",
    "HarnessConfig",
    "MicroplasticsHarness",
)
