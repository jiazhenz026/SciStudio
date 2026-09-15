"""uvicorn's graceful-shutdown drain is bounded for ``serve`` and ``gui`` (#2351).

SciStudio ends its own long-lived streams on a stop request, but uvicorn waits
for every open connection before it runs the application's shutdown. A
connection a client keeps open must not hold that shutdown past the bound,
which sits inside the desktop's 25 s force-kill with the rest of the budget.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from scistudio.cli import main as cli_main

DESKTOP_FORCE_KILL_SEC = 25.0
# Workflow runs 10 s, AI terminal sessions 3 s, command processes a 5 s grace.
REST_OF_THE_STOP_BUDGET_SEC = 18.0

# The CLI commands write these into os.environ in-process (``gui --bundled``
# sets SCISTUDIO_BUNDLED, which moves run logs to the user-data directory).
_CLI_ENV_KEYS = ("SCISTUDIO_BUNDLED", "SCISTUDIO_ENGINE_API_URL", "SCISTUDIO_ROOT_PATH")


@pytest.fixture(autouse=True)
def _restore_cli_environment() -> Iterator[None]:
    """Keep the in-process CLI's environment writes from leaking into later tests."""
    previous = {key: os.environ.get(key) for key in _CLI_ENV_KEYS}
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _capture_run(seen: dict[str, Any]) -> Any:
    def fake_run(app_target: str, **kwargs: Any) -> None:
        seen.update(kwargs, app_target=app_target)

    return fake_run


@pytest.mark.parametrize(
    "argv",
    [
        ["serve", "--port", "8125"],
        ["gui", "--no-browser", "--port", "8126"],
        ["gui", "--bundled", "--port", "0"],
    ],
)
def test_serve_and_gui_bound_the_connection_drain(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", _capture_run(seen))
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "")
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)

    result = CliRunner().invoke(cli_main.app, argv)

    assert result.exit_code == 0, result.output
    assert seen["timeout_graceful_shutdown"] == cli_main.GRACEFUL_SHUTDOWN_TIMEOUT_SEC


def test_the_drain_bound_fits_the_desktop_stop_budget() -> None:
    bound = cli_main.GRACEFUL_SHUTDOWN_TIMEOUT_SEC
    assert bound > 0
    assert bound + REST_OF_THE_STOP_BUDGET_SEC < DESKTOP_FORCE_KILL_SEC


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.mark.timeout(120)
def test_a_held_open_connection_does_not_hold_the_shutdown_past_the_bound() -> None:
    """An unrelated response that never ends still lets the lifespan shutdown run."""
    shutdown_reached = threading.Event()

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    shutdown_reached.set()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"held\n", "more_body": True})
            await asyncio.Event().wait()  # never finishes, like a client-held stream

    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        lifespan="on",
        log_level="warning",
        timeout_graceful_shutdown=cli_main.GRACEFUL_SHUTDOWN_TIMEOUT_SEC,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started

    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        client.sendall(b"GET /hold HTTP/1.1\r\nHost: localhost\r\n\r\n")
        received = b""
        while b"held" not in received:
            chunk = client.recv(1024)
            assert chunk, "the held response closed early"
            received += chunk

        stop_requested = time.monotonic()
        server.should_exit = True
        assert shutdown_reached.wait(cli_main.GRACEFUL_SHUTDOWN_TIMEOUT_SEC + 10), "the lifespan shutdown never ran"
        elapsed = time.monotonic() - stop_requested
        assert elapsed < cli_main.GRACEFUL_SHUTDOWN_TIMEOUT_SEC + 3
    finally:
        client.close()
        thread.join(15)
