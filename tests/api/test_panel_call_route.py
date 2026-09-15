"""T-003 (ADR-054 MiniApp FR-010/FR-011/FR-017): the session-authenticated call
route, its JSON/binary/error results, the process lifecycle endpoints, and the
guarantee that preview contexts never expose call and that ``.py`` is not served.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.routes.panels import router
from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.registry import PanelRegistry
from scistudio.previewers.models import OwnerKind, PreviewTarget
from tests.panels.conftest import install_panel_service

pytestmark = pytest.mark.serial

_PANEL_PY = (
    "import numpy as np\n"
    "def setup(data):\n    pass\n"
    "def echo(text):\n    return {'echoed': text}\n"
    "def grid():\n    return np.arange(4, dtype='float64')\n"
    "def boom():\n    raise ValueError('author fault')\n"
    "def wide(size):\n    return 'x' * size\n"
)


def _runtime(tmp_path: Path, *, contexts='["miniapp"]'):
    panel_dir = tmp_path / "lab.explorer"
    panel_dir.mkdir()
    (panel_dir / "panel.json").write_text(
        f'{{"id":"lab.explorer","api_version":"1.0","contexts":{contexts},"types":["Text"]}}', encoding="utf-8"
    )
    (panel_dir / "index.html").write_text("<p>app</p>", encoding="utf-8")
    (panel_dir / "panel.py").write_text(_PANEL_PY, encoding="utf-8")
    data = tmp_path / "data.txt"
    data.write_text("hello", encoding="utf-8")
    panels = PanelRegistry()
    panels.register(
        parse_descriptor(panel_dir, owner_kind=OwnerKind.PROJECT, owner_name="p", registered_types={"Text"})[0]
    )
    record = DataRecord(
        "data-a",
        StorageReference(backend="filesystem", path=str(data), metadata={"type_chain": ["DataObject", "Text"]}),
        "Text",
        {"type_chain": ["DataObject", "Text"]},
        ["DataObject", "Text"],
    )
    scheduler = SimpleNamespace(
        _project_dir=str(tmp_path),
        _block_outputs={"seg": {"out": {"data_ref": "data-a"}}},
        _block_states={"seg": SimpleNamespace(value="done")},
    )
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(tmp_path)),
        data_catalog={"data-a": record},
        workflow_runs={"wf": SimpleNamespace(scheduler=scheduler)},
        event_bus=EventBus(),
    )
    runtime.event_bus.runtime = runtime
    runtime.get_data_record = lambda ref: runtime.data_catalog[ref]
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=runtime.data_catalog[target.ref].type_name,
        type_chain=tuple(runtime.data_catalog[target.ref].type_chain),
    )
    runtime.type_registry = SimpleNamespace(
        resolve=lambda name: SimpleNamespace(base_type={"Text": "DataObject"}.get(name, ""))
    )
    install_panel_service(runtime, panels)
    return runtime


def _client(tmp_path: Path, *, contexts='["miniapp"]') -> TestClient:
    app = FastAPI()
    app.state.runtime = _runtime(tmp_path, contexts=contexts)
    app.state.registry = ProcessRegistry()
    app.include_router(router)
    return TestClient(app)


_CREATE = {
    "kind": "miniapp",
    "panel_id": "lab.explorer",
    "source": {"workflow_id": "wf", "block_id": "seg", "port": "out"},
}


def _open(client: TestClient, payload=None) -> dict:
    response = client.post("/api/panels/contexts", json=payload or _CREATE)
    assert response.status_code == 200, response.text
    body = response.json()
    _await_running(client, body["context_id"])
    return body


def _await_running(client: TestClient, context_id: str, timeout=10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/panels/contexts/{context_id}/process").json().get("state")
        if state == "running":
            return
        time.sleep(0.05)


def test_miniapp_context_reports_call_operation(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _open(client)
    assert body["kind"] == "miniapp"
    assert body["operations"] == ["read", "call", "submitAnswers"]
    assert body["services"] == ["save"]
    assert body["process"]["state"] in ("starting", "running")
    client.delete(f"/api/panels/contexts/{body['context_id']}")


def test_json_call_returns_result(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _open(client)
    try:
        response = client.post(
            f"/api/panels/contexts/{body['context_id']}/call", json={"fn": "echo", "args": {"text": "hi"}}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"result": {"echoed": "hi"}}
    finally:
        client.delete(f"/api/panels/contexts/{body['context_id']}")


def test_numpy_call_returns_octet_stream_with_headers(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _open(client)
    try:
        response = client.post(f"/api/panels/contexts/{body['context_id']}/call", json={"fn": "grid", "args": {}})
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["X-Panel-Dtype"] == "<f8"
        assert response.headers["X-Panel-Shape"] == "[4]"
        assert len(response.content) == 32
    finally:
        client.delete(f"/api/panels/contexts/{body['context_id']}")


def test_author_exception_is_reported_and_process_survives(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _open(client)
    try:
        response = client.post(f"/api/panels/contexts/{body['context_id']}/call", json={"fn": "boom", "args": {}})
        assert response.status_code == 200
        error = response.json()["error"]
        assert error["type"] == "ValueError"
        assert "author fault" in error["message"]
        # The process is still running and answers the next call.
        again = client.post(
            f"/api/panels/contexts/{body['context_id']}/call", json={"fn": "echo", "args": {"text": "x"}}
        )
        assert again.json() == {"result": {"echoed": "x"}}
    finally:
        client.delete(f"/api/panels/contexts/{body['context_id']}")


def test_unknown_or_closed_context_is_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post("/api/panels/contexts/pc-missing/call", json={"fn": "echo", "args": {}})
    assert response.status_code == 404


def test_call_on_preview_context_is_unsupported(tmp_path: Path) -> None:
    # US3: a preview context never provides call, and a raw call is refused.
    client = _client(tmp_path, contexts='["preview","miniapp"]')
    created = client.post(
        "/api/panels/contexts", json={"kind": "preview", "panel_id": "lab.explorer", "target": {"ref": "data-a"}}
    )
    assert created.status_code == 200, created.text
    context_id = created.json()["context_id"]
    assert created.json()["operations"] == ["read"]
    assert created.json()["process"] is None
    response = client.post(f"/api/panels/contexts/{context_id}/call", json={"fn": "echo", "args": {}})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsupported"


def test_restart_and_stop_endpoints(tmp_path: Path) -> None:
    client = _client(tmp_path)
    body = _open(client)
    context_id = body["context_id"]
    try:
        restarted = client.post(f"/api/panels/contexts/{context_id}/process/restart")
        assert restarted.status_code == 200
        _await_running(client, context_id)
        stopped = client.post(f"/api/panels/contexts/{context_id}/process/stop")
        assert stopped.status_code == 200
        assert stopped.json()["process"]["state"] in ("stopped", "crashed")
    finally:
        client.delete(f"/api/panels/contexts/{context_id}")


def test_python_file_is_not_served(tmp_path: Path) -> None:
    # FR-017: the token asset route must never serve panel.py.
    client = _client(tmp_path)
    body = _open(client)
    try:
        token = body["token"]
        response = client.get(f"/api/panels/t/{token}/assets/lab.explorer/panel.py")
        assert response.status_code == 404
        # index.html is served, proving the route itself works.
        ok = client.get(f"/api/panels/t/{token}/assets/lab.explorer/index.html")
        assert ok.status_code == 200
    finally:
        client.delete(f"/api/panels/contexts/{body['context_id']}")


def test_call_declares_its_own_result_contract(tmp_path: Path) -> None:
    """FR-010: the call route's 200 is ``{result}`` or ``{error}``, never ``ReadResult``.

    The declared contract was the read route's, which carries sampled /
    truncated / complete flags no call has ever returned, and the 504 a call
    timeout produces was undeclared — so an OpenAPI consumer validating a real
    call response against the contract rejected it.
    """
    schema = _client(tmp_path).app.openapi()
    call = schema["paths"]["/api/panels/contexts/{context_id}/call"]["post"]
    json_schema = call["responses"]["200"]["content"]["application/json"]["schema"]

    assert [option["$ref"].rsplit("/", 1)[-1] for option in json_schema["anyOf"]] == [
        "ContextCallResult",
        "ContextCallError",
    ]
    assert "504" in call["responses"]
    assert "application/octet-stream" in call["responses"]["200"]["content"]
    assert set(call["responses"]["200"]["headers"]) == {"X-Panel-Dtype", "X-Panel-Shape", "X-Panel-Metadata"}


def test_the_call_budget_is_the_process_result_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-011: the call path measures a JSON result against ``max_result_bytes``.

    It used to measure against the read route's ``READ_BYTES`` (20 MiB) while
    the subprocess allowed ``max_result_bytes`` (64 MiB), so a result between
    the two was refused route-side as ``read_budget`` — one user-visible
    condition reported under two codes, and a ceiling no configuration could
    raise. Proved here by lowering the configurable budget and watching the
    route follow it: the same call succeeds at the default (see
    ``test_json_call_returns_result``).
    """
    from scistudio.api.routes import panels as panels_route

    monkeypatch.setattr(panels_route, "max_result_bytes", lambda: 32)
    client = _client(tmp_path)
    body = _open(client)
    try:
        response = client.post(
            f"/api/panels/contexts/{body['context_id']}/call",
            json={"fn": "wide", "args": {"size": 256}},
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "read_budget"
    finally:
        client.delete(f"/api/panels/contexts/{body['context_id']}")


@pytest.mark.parametrize("ending", ["stop", "crash"])
def test_hung_calls_do_not_starve_http_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: str) -> None:
    """HTTP health stays responsive with more blocked calls than AnyIO workers."""
    import anyio.to_thread
    import httpx

    from scistudio.panels.service import get_panel_contexts

    monkeypatch.setenv("SCISTUDIO_PANEL_TEARDOWN_GRACE", "0.1")
    monkeypatch.setenv("SCISTUDIO_PANEL_CALL_TIMEOUT", "10")
    app = _client(tmp_path).app
    panel_dir = tmp_path / "lab.explorer"
    (panel_dir / "panel.py").write_text(
        "import os, time\nfrom pathlib import Path\n"
        "def setup(data): pass\n"
        "def hang():\n"
        "    Path(__file__).with_name('entered').touch()\n"
        "    while not Path(__file__).with_name('release').exists(): time.sleep(.01)\n"
        "    os._exit(17)\n",
        encoding="utf-8",
    )

    @app.get("/health-sync")
    def health_sync():
        return {"ok": True}

    async def run():
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous_limit = limiter.total_tokens
        limiter.total_tokens = 2
        store = get_panel_contexts(app.state.runtime)
        calls = []
        process = None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            try:
                created = await client.post("/api/panels/contexts", json=_CREATE)
                assert created.status_code == 200, created.text
                context_id = created.json()["context_id"]
                process = store.get(context_id).process
                deadline = time.monotonic() + 10
                while process.state == "starting" and time.monotonic() < deadline:
                    await asyncio.sleep(0.02)
                assert process.state == "running"
                calls = [
                    asyncio.create_task(
                        client.post(f"/api/panels/contexts/{context_id}/call", json={"fn": "hang", "args": {}})
                    )
                    for _ in range(3)
                ]
                deadline = time.monotonic() + 2
                while not (panel_dir / "entered").exists() and time.monotonic() < deadline:
                    await asyncio.sleep(0.01)
                assert (panel_dir / "entered").exists()
                # Let every request enter the endpoint. A sync call route consumes
                # both AnyIO tokens here, so the unrelated sync route times out.
                await asyncio.sleep(0.05)
                assert all(not call.done() for call in calls)
                for _ in range(3):
                    response = await asyncio.wait_for(client.get("/health-sync"), timeout=1)
                    assert response.json() == {"ok": True}
                if ending == "crash":
                    (panel_dir / "release").touch()
                else:
                    stopped = await client.post(f"/api/panels/contexts/{context_id}/process/stop")
                    assert stopped.status_code == 200
                responses = await asyncio.wait_for(asyncio.gather(*calls), timeout=5)
                assert all(response.status_code >= 400 for response in responses)
                assert (await asyncio.wait_for(client.get("/health-sync"), timeout=1)).status_code == 200
            finally:
                limiter.total_tokens = previous_limit
                if process is not None:
                    await asyncio.to_thread(process.stop)
                store.close_all()
                if calls:
                    await asyncio.gather(*calls, return_exceptions=True)

    asyncio.run(run())
