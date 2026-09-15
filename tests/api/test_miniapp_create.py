"""ADR-054 MiniApp FR-024/FR-026/FR-027/FR-031/FR-034/FR-036: the MiniApp routes.

The acceptance scenarios these cover are User Story 1 (create from a block and
watch the template appear), User Story 5 (the MiniApps tab lists them), User
Story 6 (a MiniApp opens on data of its type) and User Story 8 (convert to an
interactive block).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.ai.agent import availability as agent_availability
from scistudio.ai.agent.availability import AvailabilityReport, AvailabilityState, ProviderAvailability
from scistudio.api.routes.ai_pty import _state as pty_state
from scistudio.api.routes.ai_pty import engine as pty_engine
from scistudio.api.routes.panels import router
from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.panels.registry import PanelRegistry
from scistudio.previewers.models import OwnerKind, PreviewTarget
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager

# One test opens a real MiniApp context, which starts a real subprocess.
pytestmark = pytest.mark.serial

_TYPES = {"Text", "Table"}


def _record(name: str, path: Path, type_name: str) -> DataRecord:
    chain = ["DataObject", type_name]
    return DataRecord(
        name,
        StorageReference(backend="filesystem", path=str(path), metadata={"type_chain": chain}),
        type_name,
        {"type_chain": chain},
        chain,
    )


def _runtime(tmp_path: Path) -> SimpleNamespace:
    """A runtime with two finished block outputs: a ``Text`` and a ``Table``."""
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")
    table_file = tmp_path / "peaks.txt"
    table_file.write_text("a,b", encoding="utf-8")

    catalog = {
        "data-text": _record("data-text", text_file, "Text"),
        "data-table": _record("data-table", table_file, "Table"),
    }
    definition = SimpleNamespace(
        id="wf",
        metadata={"name": "Segmentation run"},
        nodes=[
            SimpleNamespace(id="seg", block_type="Segment", config={"name": "Segment cells"}),
            SimpleNamespace(id="tab", block_type="Tabulate", config={}),
        ],
    )
    scheduler = SimpleNamespace(
        _project_dir=str(tmp_path),
        _workflow=definition,
        _block_outputs={"seg": {"out": {"data_ref": "data-text"}}, "tab": {"out": {"data_ref": "data-table"}}},
        _block_states={"seg": SimpleNamespace(value="done"), "tab": SimpleNamespace(value="done")},
    )

    service = SimpleNamespace()
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(tmp_path)),
        data_catalog=catalog,
        workflow_runs={"wf": SimpleNamespace(scheduler=scheduler)},
        event_bus=EventBus(),
    )
    runtime.event_bus.runtime = runtime
    runtime.get_data_record = lambda ref: catalog[ref]
    runtime.get_preview_service = lambda: service
    runtime.register_output_payload = lambda value: value
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=catalog[target.ref].type_name,
        type_chain=tuple(catalog[target.ref].type_chain),
    )
    runtime.type_registry = SimpleNamespace(resolve=lambda name: SimpleNamespace(base_type="DataObject"))

    def refresh() -> None:
        panels = PanelRegistry()
        panels_dir = tmp_path / "panels"
        if panels_dir.is_dir():
            for child in sorted(panels_dir.iterdir()):
                if child.is_dir():
                    panels.load(child, OwnerKind.PROJECT, _TYPES)
        registry = PreviewerRegistry()
        registry.load_core()
        registry.install_panels(panels)
        service.registry = registry
        service.router = PreviewRouter(registry)
        service.sessions = PreviewSessionManager(registry)

    runtime.refresh_all_registries = refresh
    refresh()
    return runtime


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.runtime = _runtime(tmp_path)
    app.state.registry = ProcessRegistry()
    app.include_router(router)
    return TestClient(app)


def _report(*providers: ProviderAvailability) -> AvailabilityReport:
    state = next((p.state for p in providers if p.state is AvailabilityState.READY), AvailabilityState.NOT_INSTALLED)
    return AvailabilityReport(state=state, providers=tuple(providers))


_READY = ProviderAvailability(key="claude-code", label="Claude Code", state=AvailabilityState.READY)
_MISSING = ProviderAvailability(
    key="claude-code",
    label="Claude Code",
    state=AvailabilityState.NOT_INSTALLED,
    next_step="Install Claude Code with npm install -g @anthropic-ai/claude-code.",
)


@pytest.fixture()
def agent(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A ready provider and a recorded pre-spawned session."""
    spawned: dict[str, Any] = {}

    async def probe(_loader: Any, *, refresh: bool = False) -> AvailabilityReport:
        return _report(*spawned.get("providers", (_READY,)))

    def open_tab(*, provider: str, cwd: str, opening_message: str, permission_mode: str) -> str:
        spawned.update(provider=provider, cwd=cwd, opening_message=opening_message, permission_mode=permission_mode)
        return "tab-abc123"

    monkeypatch.setattr(agent_availability, "probe_availability", probe)
    monkeypatch.setattr(pty_engine, "open_work_import_tab", open_tab)
    return spawned


_SOURCE = {"workflow_id": "wf", "block_id": "seg", "port": "out"}


def _create(client: TestClient, **overrides: Any) -> Any:
    body = {"request": "let me drag a threshold across the stack and see the mask", "source": _SOURCE}
    body.update(overrides)
    return client.post("/api/panels/miniapps", json=body)


def test_create_writes_the_template_directory_and_the_brief(tmp_path: Path, agent: dict[str, Any]) -> None:
    """US1 AS2: the directory exists with the three template files when the route returns."""
    client = _client(tmp_path)
    response = _create(client, name="Threshold explorer")
    assert response.status_code == 201, response.text
    body = response.json()

    directory = Path(body["directory"])
    assert directory == tmp_path / "panels" / body["panel_id"]
    assert {p.name for p in directory.iterdir()} == {"panel.json", "index.html", "panel.py"}

    manifest = json.loads((directory / "panel.json").read_text(encoding="utf-8"))
    assert manifest["contexts"] == ["miniapp"]
    assert manifest["types"] == ["Text"]
    assert manifest["id"] == body["panel_id"]
    assert manifest["name"] == "Threshold explorer"
    assert manifest["description"] == "let me drag a threshold across the stack and see the mask"

    assert body["source"] == _SOURCE
    assert body["session_tab_id"] == "tab-abc123"


def test_create_writes_a_brief_the_session_is_pointed_at(tmp_path: Path, agent: dict[str, Any]) -> None:
    """FR-024/FR-027: one brief per session, and the agent is told to read it."""
    client = _client(tmp_path)
    response = _create(client)
    assert response.status_code == 201, response.text
    panel_id = response.json()["panel_id"]

    briefs = sorted((tmp_path / ".scistudio" / "miniapps").glob("*.md"))
    assert len(briefs) == 1
    relpath = briefs[0].relative_to(tmp_path).as_posix()
    assert agent["opening_message"] == f"Read the file {relpath} and follow the instructions in it."
    assert agent["cwd"] == str(tmp_path)
    assert agent["permission_mode"] == "safe"

    brief = briefs[0].read_text(encoding="utf-8")
    assert "scistudio-write-miniapp" in brief
    assert f"panels/{panel_id}" in brief
    assert "validate_panel" in brief
    assert "`contexts`" in brief and "`types`" in brief
    # #2447: look at the data, ask with a questionnaire, wait for the submit, then build.
    assert "questionnaire.json" in brief and "`Questionnaire`" in brief
    assert "Decide for me" in brief
    assert "wait_for_answers" in brief
    assert f"panels/{panel_id}/answers.json" in brief
    assert "let me drag a threshold across the stack and see the mask" in brief


def test_create_refuses_and_writes_nothing_when_no_agent_can_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US1 AS4: no directory is created and the graded reason is returned verbatim."""

    async def probe(_loader: Any, *, refresh: bool = False) -> AvailabilityReport:
        return _report(_MISSING)

    def refuse(**_kwargs: Any) -> str:
        raise AssertionError("the session must not be spawned when no agent is available")

    monkeypatch.setattr(agent_availability, "probe_availability", probe)
    monkeypatch.setattr(pty_engine, "open_work_import_tab", refuse)

    client = _client(tmp_path)
    response = _create(client)

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "agent_unavailable", "message": _MISSING.next_step}
    assert not (tmp_path / "panels").exists()
    assert not (tmp_path / ".scistudio" / "miniapps").exists()


def test_create_refuses_a_provider_that_cannot_be_handed_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-024: ``session_unsupported_reason`` refuses a provider however ready it is."""
    unsupported = ProviderAvailability(
        key="kimi-code",
        label="Kimi Code",
        state=AvailabilityState.READY,
        session_unsupported_reason="Kimi Code parses its first positional argument as a subcommand.",
    )

    async def probe(_loader: Any, *, refresh: bool = False) -> AvailabilityReport:
        return AvailabilityReport(state=AvailabilityState.READY, providers=(unsupported,))

    monkeypatch.setattr(agent_availability, "probe_availability", probe)
    client = _client(tmp_path)
    response = _create(client, provider="kimi-code")

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == unsupported.session_unsupported_reason
    assert not (tmp_path / "panels").exists()


def test_create_picks_the_next_free_id(tmp_path: Path, agent: dict[str, Any]) -> None:
    """Edge case: a MiniApp id already exists at the project tier."""
    client = _client(tmp_path)
    first = _create(client, name="Threshold explorer").json()["panel_id"]
    second = _create(client, name="Threshold explorer").json()["panel_id"]

    assert first == "threshold_explorer"
    assert second == "threshold_explorer_2"
    assert (tmp_path / "panels" / second / "panel.json").is_file()


def test_create_refuses_a_source_with_no_successful_run(tmp_path: Path, agent: dict[str, Any]) -> None:
    client = _client(tmp_path)
    response = _create(client, source={"workflow_id": "wf", "block_id": "nope", "port": "out"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_output"
    assert not (tmp_path / "panels").exists()


def test_template_page_explains_itself_and_signals_ready(tmp_path: Path, agent: dict[str, Any]) -> None:
    """FR-026: the page renders with ``panel.py`` doing nothing, and says what it is."""
    client = _client(tmp_path)
    directory = Path(_create(client, name="Threshold explorer").json()["directory"])

    page = (directory / "index.html").read_text(encoding="utf-8")
    assert "let me drag a threshold across the stack and see the mask" in page
    assert "A MiniApp is a small app" in page
    assert "AI tab" in page
    assert "scistudio.ready()" in page
    assert "{{scistudio:" not in page

    # ``setup`` doing nothing is what makes the page above renderable at once.
    module: dict[str, Any] = {}
    exec(compile((directory / "panel.py").read_text(encoding="utf-8"), "panel.py", "exec"), module)
    assert module["setup"](object()) is None


def test_template_page_escapes_the_request(tmp_path: Path, agent: dict[str, Any]) -> None:
    """The user's words are text on the page, never markup."""
    client = _client(tmp_path)
    directory = Path(_create(client, request="show me <script>alert(1)</script> please").json()["directory"])

    page = (directory / "index.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page


def test_created_miniapp_opens_a_context_on_the_chosen_output(tmp_path: Path, agent: dict[str, Any]) -> None:
    """US1 AS2: the MiniApp tab shows the template page on the chosen output."""
    client = _client(tmp_path)
    created = _create(client).json()

    response = client.post(
        "/api/panels/contexts",
        json={"kind": "miniapp", "panel_id": created["panel_id"], "source": _SOURCE},
    )
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["kind"] == "miniapp"
    assert context["operations"] == ["read", "call", "submitAnswers"]
    assert context["input"]["type"] == "Text"
    client.delete(f"/api/panels/contexts/{context['context_id']}")


def test_sources_lists_only_outputs_of_the_declared_type(tmp_path: Path, agent: dict[str, Any]) -> None:
    """US6 AS1: the picker lists the ``Text`` outputs and nothing else (FR-034)."""
    client = _client(tmp_path)
    panel_id = _create(client).json()["panel_id"]

    response = client.get(f"/api/panels/miniapps/{panel_id}/sources")
    assert response.status_code == 200, response.text
    sources = response.json()["sources"]

    assert sources == [
        {
            "workflow_id": "wf",
            "workflow_name": "Segmentation run",
            "block_id": "seg",
            "block_name": "Segment cells",
            "port": "out",
            "type": "Text",
        }
    ]


def test_sources_of_an_unknown_miniapp_are_a_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/panels/miniapps/lab.nothing/sources")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_panel"


def test_list_miniapps_reports_what_the_tab_shows(tmp_path: Path, agent: dict[str, Any]) -> None:
    """FR-031/FR-032: name, declared type, tier, and directory for the popover."""
    client = _client(tmp_path)
    created = _create(client, name="Threshold explorer").json()

    response = client.get("/api/panels/miniapps")
    assert response.status_code == 200, response.text
    assert response.json()["miniapps"] == [
        {
            "panel_id": created["panel_id"],
            "name": "Threshold explorer",
            "description": "let me drag a threshold across the stack and see the mask",
            "type": "Text",
            "tier": "project",
            "directory": created["directory"],
            "has_python": True,
        }
    ]


def test_convert_starts_a_session_and_leaves_the_miniapp_alone(tmp_path: Path, agent: dict[str, Any]) -> None:
    """US8 AS1: the brief names the outputs and the ADR-051 contract (FR-036)."""
    client = _client(tmp_path)
    created = _create(client).json()
    directory = Path(created["directory"])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    briefs_before = set((tmp_path / ".scistudio" / "miniapps").glob("*.md"))

    response = client.post(
        f"/api/panels/miniapps/{created['panel_id']}/convert",
        json={
            "outputs": [{"name": "mask", "type": "Mask", "port": "out"}],
            "note": "keep the smoothing radius configurable",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json() == {"session_tab_id": "tab-abc123", "provider": "claude-code", "permission_mode": "safe"}

    written = set((tmp_path / ".scistudio" / "miniapps").glob("*.md")) - briefs_before
    assert len(written) == 1
    brief = written.pop().read_text(encoding="utf-8")
    assert f"panels/{created['panel_id']}" in brief
    assert "scistudio-write-block" in brief
    assert "prepare_prompt" in brief
    assert "one decision" in brief
    assert "`mask`" in brief and "`Mask`" in brief
    assert "keep the smoothing radius configurable" in brief

    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_convert_of_an_unknown_miniapp_is_a_404(tmp_path: Path, agent: dict[str, Any]) -> None:
    client = _client(tmp_path)
    response = client.post("/api/panels/miniapps/lab.nothing/convert", json={"outputs": []})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_panel"


def test_a_session_that_does_not_start_leaves_the_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge case: the agent fails to start after the directory was created."""

    async def probe(_loader: Any, *, refresh: bool = False) -> AvailabilityReport:
        return _report(_READY)

    def fail(**_kwargs: Any) -> str:
        raise FileNotFoundError("claude binary vanished")

    monkeypatch.setattr(agent_availability, "probe_availability", probe)
    monkeypatch.setattr(pty_engine, "open_work_import_tab", fail)

    client = _client(tmp_path)
    response = _create(client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_tab_id"] is None
    assert (Path(body["directory"]) / "index.html").is_file()


def test_project_source_listing_does_not_require_an_existing_panel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/api/panels/miniapps/sources")
    assert response.status_code == 200
    assert {row["type"] for row in response.json()["sources"]} == {"Text", "Table"}


@pytest.mark.parametrize("missing_owner", [False, True])
def test_previous_project_sources_cannot_be_listed_or_opened(
    tmp_path: Path, agent: dict[str, Any], missing_owner: bool
) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    runtime = client.app.state.runtime
    assert len(client.get("/api/panels/miniapps/sources").json()["sources"]) == 2
    other = tmp_path / "empty-project"
    other.mkdir()
    runtime.active_project = SimpleNamespace(id="empty", path=str(other))
    runtime.data_catalog = {}
    # Keep old scheduler outputs and even resolvable catalog aliases around:
    # ownership must reject them before they can be frozen or re-registered.
    if missing_owner:
        del runtime.workflow_runs["wf"].scheduler._project_dir
    assert client.get("/api/panels/miniapps/sources").json()["sources"] == []
    assert client.get(f"/api/panels/miniapps/{created['panel_id']}/sources").json()["sources"] == []
    response = _create(client)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_output"
    response = client.post(
        "/api/panels/contexts",
        json={
            "kind": "miniapp",
            "panel_id": created["panel_id"],
            "source": _SOURCE,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_output"
    assert not (other / "panels").exists()


def test_project_switch_excludes_retained_runs(
    client: TestClient, runtime: Any, opened_project: Path, project_parent: Path
) -> None:
    retained = _runtime(opened_project)
    scheduler = retained.workflow_runs["wf"].scheduler
    # Real scheduler outputs carry storage payloads which the source resolver
    # can register again after open_project resets the data catalogue.
    scheduler._block_outputs = {
        "seg": {
            "out": {
                "backend": "filesystem",
                "path": str(opened_project / "notes.txt"),
                "metadata": {"type_chain": ["DataObject", "Text"]},
            }
        }
    }
    runtime.workflow_runs["wf"] = SimpleNamespace(scheduler=scheduler, task=SimpleNamespace(done=lambda: True))
    assert client.get("/api/panels/miniapps/sources").json()["sources"]
    response = client.post("/api/projects/", json={"name": "Empty B", "path": str(project_parent)})
    assert response.status_code == 200, response.text
    assert client.get("/api/panels/miniapps/sources").json()["sources"] == []
    assert not runtime.data_catalog


@pytest.mark.parametrize("provider", [None, "claude-code"])
@pytest.mark.parametrize(
    "mode,expected", [("safe", "safe"), ("auto", "auto"), ("bypass", "bypass"), ("dangerous", "bypass")]
)
def test_create_preserves_supported_permission_modes(
    tmp_path: Path, agent: dict[str, Any], provider: str | None, mode: str, expected: str
) -> None:
    response = _create(_client(tmp_path), provider=provider, permission_mode=mode)
    assert response.status_code == 201, response.text
    assert response.json()["permission_mode"] == expected
    assert agent["provider"] == "claude-code"
    assert agent["permission_mode"] == expected


@pytest.mark.parametrize("provider", [None, "claude-code"])
def test_create_refuses_unsupported_auto_before_writes_or_session(
    tmp_path: Path, agent: dict[str, Any], monkeypatch: pytest.MonkeyPatch, provider: str | None
) -> None:
    from dataclasses import replace

    from scistudio.ai.agent import providers_registry

    unsupported = replace(providers_registry.get("claude-code"), auto_argv=(), auto_argv_absent_reason="test fixture")
    monkeypatch.setattr(providers_registry, "get", lambda _key: unsupported)
    response = _create(_client(tmp_path), provider=provider, permission_mode="auto")

    assert response.status_code == 400
    assert "has no Auto permission mode" in response.json()["detail"]["message"]
    assert "opening_message" not in agent
    assert not (tmp_path / "panels").exists()
    assert not (tmp_path / ".scistudio" / "miniapps").exists()


@pytest.mark.parametrize("supported", [True, False])
def test_convert_validates_auto_before_writing_brief_or_spawning(
    tmp_path: Path, agent: dict[str, Any], monkeypatch: pytest.MonkeyPatch, supported: bool
) -> None:
    from dataclasses import replace

    from scistudio.ai.agent import providers_registry

    client = _client(tmp_path)
    created = _create(client).json()
    directory = Path(created["directory"])
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    briefs_before = set((tmp_path / ".scistudio" / "miniapps").glob("*.md"))
    agent.clear()
    if not supported:
        descriptor = replace(
            providers_registry.get("claude-code"), auto_argv=(), auto_argv_absent_reason="test fixture"
        )
        monkeypatch.setattr(providers_registry, "get", lambda _key: descriptor)

    response = client.post(
        f"/api/panels/miniapps/{created['panel_id']}/convert",
        json={"outputs": [{"name": "mask", "type": "Mask", "port": "out"}], "permission_mode": "auto"},
    )

    assert {p.name: p.read_bytes() for p in directory.iterdir()} == original
    new_briefs = set((tmp_path / ".scistudio" / "miniapps").glob("*.md")) - briefs_before
    if supported:
        assert response.status_code == 201, response.text
        assert response.json()["permission_mode"] == "auto"
        assert agent["permission_mode"] == "auto"
        assert len(new_briefs) == 1
    else:
        assert response.status_code == 400
        assert "has no Auto permission mode" in response.json()["detail"]["message"]
        assert "opening_message" not in agent
        assert new_briefs == set()


# ---------------------------------------------------------------------------
# Questionnaire submit (#2447, MiniApp FR-050/FR-051)
# ---------------------------------------------------------------------------

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "questionnaire" / "miniapp"


class _FakePty:
    def __init__(self, cwd: Path, *, alive: bool = True) -> None:
        self._cwd = cwd
        self.alive = alive
        self.written: list[bytes] = []

    def is_alive(self) -> bool:
        return self.alive

    def write(self, data: bytes) -> None:
        self.written.append(data)


def _questionnaire_context(client: TestClient, tmp_path: Path, created: dict[str, Any]) -> str:
    """Turn the created MiniApp into a questionnaire page with no panel.py, and open it."""
    directory = tmp_path / "panels" / created["panel_id"]
    (directory / "panel.py").unlink()
    shutil.copyfile(_FIXTURE / "questionnaire.json", directory / "questionnaire.json")
    shutil.copyfile(_FIXTURE / "index.html", directory / "index.html")
    client.app.state.runtime.refresh_all_registries()  # type: ignore[attr-defined]
    response = client.post(
        "/api/panels/contexts", json={"kind": "miniapp", "panel_id": created["panel_id"], "source": _SOURCE}
    )
    assert response.status_code == 200, response.text
    assert response.json()["operations"] == ["read", "submitAnswers"]
    return str(response.json()["context_id"])


@pytest.fixture()
def fast_enter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pty_engine, "TYPE_LINE_ENTER_DELAY_S", 0.0)


def test_submit_saves_answers_and_types_one_line_into_the_session(
    tmp_path: Path, agent: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fast_enter: None
) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    fake = _FakePty(tmp_path)
    monkeypatch.setitem(pty_state._active_ptys, "tab-abc123", fake)
    context_id = _questionnaire_context(client, tmp_path, created)

    response = client.post(
        f"/api/panels/contexts/{context_id}/answers",
        json={"answers": {"chart": {"status": "answered", "value": "pca"}, "notes": {"status": "decide_for_me"}}},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    relpath = f"panels/{created['panel_id']}/answers.json"
    assert result["saved"] is True and result["notified"] is True and result["reason"] is None
    assert result["path"] == relpath
    document = json.loads((tmp_path / relpath).read_text(encoding="utf-8"))
    assert [a["status"] for a in document["answers"]] == ["answered", "skipped", "decide_for_me", "skipped", "skipped"]
    assert document["submitted_at"] == result["submitted_at"]
    # The line, then Enter as its own keystroke — never an interrupt.
    assert len(fake.written) == 2
    line = fake.written[0].decode()
    assert created["panel_id"] in line and relpath in line and "\n" not in line and "\r" not in line
    assert fake.written[1] == b"\r"
    client.delete(f"/api/panels/contexts/{context_id}")


def test_submit_without_a_live_session_only_saves(
    tmp_path: Path, agent: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fast_enter: None
) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    fake = _FakePty(tmp_path, alive=False)
    monkeypatch.setitem(pty_state._active_ptys, "tab-abc123", fake)
    context_id = _questionnaire_context(client, tmp_path, created)

    first = client.post(f"/api/panels/contexts/{context_id}/answers", json={"answers": {}}).json()
    assert first["saved"] is True and first["notified"] is False and first["reason"] == "session_ended"
    assert "Go back to your AI chat" in first["message"]
    assert fake.written == []
    second = client.post(f"/api/panels/contexts/{context_id}/answers", json={"answers": {}}).json()
    assert second["reason"] == "no_session"
    assert (tmp_path / first["path"]).is_file()
    client.delete(f"/api/panels/contexts/{context_id}")


def test_a_session_in_another_directory_is_not_typed_into(
    tmp_path: Path, agent: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fast_enter: None
) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    fake = _FakePty(tmp_path / "elsewhere")
    monkeypatch.setitem(pty_state._active_ptys, "tab-abc123", fake)
    context_id = _questionnaire_context(client, tmp_path, created)
    result = client.post(f"/api/panels/contexts/{context_id}/answers", json={"answers": {}}).json()
    assert result["notified"] is False and fake.written == []
    client.delete(f"/api/panels/contexts/{context_id}")


def test_submit_refuses_answers_that_do_not_fit(tmp_path: Path, agent: dict[str, Any]) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    context_id = _questionnaire_context(client, tmp_path, created)
    response = client.post(
        f"/api/panels/contexts/{context_id}/answers",
        json={"answers": {"chart": {"status": "answered", "value": "not-an-option"}}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_answers"
    assert not (tmp_path / "panels" / created["panel_id"] / "answers.json").exists()
    client.delete(f"/api/panels/contexts/{context_id}")


def test_submit_without_a_questionnaire_is_refused(tmp_path: Path, agent: dict[str, Any]) -> None:
    client = _client(tmp_path)
    created = _create(client).json()
    context_id = _questionnaire_context(client, tmp_path, created)
    (tmp_path / "panels" / created["panel_id"] / "questionnaire.json").unlink()
    response = client.post(f"/api/panels/contexts/{context_id}/answers", json={"answers": {}})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_questionnaire"
    client.delete(f"/api/panels/contexts/{context_id}")
