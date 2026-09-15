"""Reach SciStudio's agent MCP tools the way an external agent does (#2398).

A running ``scistudio serve`` exposes one tool registry through two front doors,
and ``scistudio`` ships a stdio process for each of them:

- the **WebMCP HTTP bridge** (``GET /api/webmcp/tools``, ``POST
  /api/webmcp/call``). It serves every registered tool, including the
  ``audience:external`` workspace and command tools, and authenticates with the
  per-launch loopback token the server publishes in
  ``~/.scistudio/webmcp/loopback-<port>.json``. ``scistudio webmcp-adapter`` is
  the stdio MCP server AI apps launch in front of it.
- the **project MCP socket** the backend binds for the open project. It serves
  every tool except the external-audience ones. ``scistudio mcp-bridge`` is the
  stdio proxy the provisioned agent configs launch to reach it.

:class:`WebMcpClient` talks to the HTTP bridge directly and is what the tool
suite drives. :class:`StdioMcpClient` speaks line-delimited JSON-RPC to either
stdio process, for the transport tests. :class:`ToolLedger` records which tools
a test session actually dispatched, so a guard test can fail when a registered
tool is never exercised.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

TOKEN_HEADER = "x-scistudio-webmcp-token"


@dataclass
class ToolLedger:
    """Names of the tools a test session dispatched to the server."""

    called: set[str] = field(default_factory=set)

    def record(self, name: str) -> None:
        self.called.add(name)


@dataclass(frozen=True)
class ToolResult:
    """One adapted tool result as the WebMCP bridge returns it."""

    name: str
    is_error: bool
    content: list[dict[str, Any]]
    structured: dict[str, Any] | None

    @property
    def data(self) -> Any:
        """The structured result, unwrapped when FastMCP wrapped a non-object return."""
        if self.structured is None:
            raise AssertionError(f"{self.name} returned no structured content: {self.text[:2000]}")
        if set(self.structured) == {"result"}:
            return self.structured["result"]
        return self.structured

    @property
    def text(self) -> str:
        return "\n".join(str(block.get("text", "")) for block in self.content)

    def ok(self) -> Any:
        """The structured result of a call that must have succeeded."""
        assert not self.is_error, f"{self.name} failed: {self.text[:2000]}"
        return self.data

    def refused(self, code: str) -> dict[str, Any]:
        """The envelope of a call a documented rule refused with ``code``."""
        assert self.is_error, f"{self.name} was expected to be refused ({code}) but succeeded: {self.structured}"
        envelope = self.data
        assert envelope.get("status") in {"refused", "conflict"}, envelope
        assert envelope["refusal"]["code"] == code, envelope
        return dict(envelope)

    def raised(self) -> str:
        """The text of a call the tool rejected by raising (``isError`` with the detail withheld)."""
        assert self.is_error, f"{self.name} was expected to fail but succeeded: {self.structured}"
        assert self.structured is None, self.structured
        # The bridge names the exception type and withholds its message (FR-003).
        assert "detail withheld by the webmcp bridge" in self.text, self.text
        return self.text


def read_loopback_token(home: Path, port: int, timeout: float = 30.0) -> str:
    """The loopback token ``scistudio serve`` published for ``port`` under ``home``."""
    path = home / ".scistudio" / "webmcp" / f"loopback-{port}.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["port"] == port, record
            return str(record["token"])
        time.sleep(0.1)
    raise AssertionError(f"no loopback token file at {path} after {timeout:.0f}s")


class WebMcpClient:
    """The WebMCP HTTP bridge, called the way the served page and the adapter call it."""

    def __init__(self, base_url: str, token: str, ledger: ToolLedger) -> None:
        self.http = httpx.Client(base_url=base_url, headers={TOKEN_HEADER: token}, timeout=180.0)
        self.ledger = ledger
        self.project_id: str | None = None

    def close(self) -> None:
        self.http.close()

    def catalogue(self) -> dict[str, Any]:
        """Fetch the catalogue and adopt its project snapshot, as a host does before calling."""
        response = self.http.get("/api/webmcp/tools")
        assert response.status_code == 200, response.text[:2000]
        catalogue: dict[str, Any] = response.json()
        self.project_id = catalogue["context"]["projectId"]
        return catalogue

    def post_call(self, name: str, arguments: dict[str, Any], project_id: str | None) -> httpx.Response:
        return self.http.post("/api/webmcp/call", json={"name": name, "arguments": arguments, "projectId": project_id})

    def call(self, name: str, arguments: dict[str, Any] | None = None, /, **kwargs: Any) -> ToolResult:
        """Invoke one tool with the adopted project snapshot and return its adapted result.

        Arguments go in ``arguments`` or as keywords; a tool argument called
        ``name`` (``scaffold_block``) has to use the dict.
        """
        args = dict(arguments or {}, **kwargs)
        response = self.post_call(name, args, self.project_id)
        assert response.status_code == 200, f"{name} -> HTTP {response.status_code}: {response.text[:2000]}"
        self.ledger.record(name)
        body = response.json()
        return ToolResult(
            name=name,
            is_error=bool(body.get("isError")),
            content=list(body.get("content") or []),
            structured=body.get("structuredContent"),
        )


class StdioMcpClient:
    """A stdio MCP server process (``mcp-bridge`` or ``webmcp-adapter``), driven line by line."""

    def __init__(self, argv: Sequence[str], *, env: dict[str, str], cwd: Path) -> None:
        self.proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
        self._next_id = 0
        #: Messages that arrived while waiting for a response and were not it.
        self.skipped: list[dict[str, Any]] = []
        self._lines: queue.Queue[bytes] = queue.Queue()
        self._stderr: list[bytes] = []
        threading.Thread(target=self._pump_stdout, name="e2e-mcp-stdout", daemon=True).start()
        threading.Thread(target=self._pump_stderr, name="e2e-mcp-stderr", daemon=True).start()

    def _pump_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)

    def _pump_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr.append(line)

    @property
    def stderr(self) -> str:
        return b"".join(self._stderr).decode("utf-8", errors="replace")

    def _send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 120.0) -> dict[str, Any]:
        """Send one request and return its response, skipping server notifications."""
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                break
            message: dict[str, Any] = json.loads(line)
            if message.get("id") == request_id:
                return message
            self.skipped.append(message)
        raise AssertionError(f"no response to {method} within {timeout:.0f}s; stderr:\n{self.stderr[-3000:]}")

    def initialize(self) -> dict[str, Any]:
        response = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "scistudio-e2e", "version": "0"},
            },
        )
        assert "result" in response, response
        self.notify("notifications/initialized")
        result: dict[str, Any] = response["result"]
        return result

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    def close(self, timeout: float = 20.0) -> int:
        """Close stdin (the end of the conversation) and return the exit code; kill on a hang."""
        if self.proc.stdin is not None and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self.proc.kill()
            self.proc.wait(timeout=10)
            raise AssertionError(
                f"MCP stdio process did not exit after stdin closed; stderr:\n{self.stderr[-3000:]}"
            ) from exc


def text_payload(response: dict[str, Any]) -> Any:
    """The JSON value a socket ``tools/call`` result carries in its single text block."""
    assert "result" in response, response
    content = response["result"]["content"]
    assert len(content) == 1 and content[0]["type"] == "text", content
    return json.loads(content[0]["text"])
