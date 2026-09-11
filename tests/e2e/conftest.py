"""Fixtures for the opt-in headless end-to-end suite (#2298).

The suite starts a real server process, so it is slow and is skipped unless
``SCISTUDIO_RUN_E2E=1``. CI runs it as its own job; locally::

    SCISTUDIO_RUN_E2E=1 PYTHONPATH=./src pytest tests/e2e -n 0 --no-cov
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.harness import Backend, EventStream, ServeProcess


@pytest.fixture(scope="session")
def serve(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ServeProcess]:
    """One server for the session, with its home in a temporary directory."""
    server = ServeProcess(tmp_path_factory.mktemp("e2e-home"))
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def backend(serve: ServeProcess, request: pytest.FixtureRequest) -> Iterator[Backend]:
    client = Backend(serve.base_url)
    try:
        yield client
    finally:
        client.close()
        report = getattr(request.node, "rep_call", None)
        if report is not None and report.failed:
            print(f"\n--- scistudio serve log (tail) ---\n{serve.log_tail()}")


@pytest.fixture
def events(serve: ServeProcess) -> Iterator[EventStream]:
    """A GUI WebSocket session, open for the whole test."""
    stream = EventStream(serve.base_url)
    try:
        yield stream
    finally:
        stream.close()


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    parent = tmp_path / "projects"
    parent.mkdir()
    return parent


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    """Expose the call-phase report so fixtures can dump the server log on failure."""
    report = yield
    if report.when == "call":
        item.rep_call = report  # type: ignore[attr-defined]
    return report
