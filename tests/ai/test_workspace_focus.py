"""The workspace focus, end to end on the backend.

ADR-054 spec 5, FR-001 to FR-005 (issue #2254). The owner's one hard
requirement for that spec is that the agent must always know whether the person
is on the canvas or in an explore session, and the mechanism is the
active-workflow channel of ADR-040 Addendum 5 widened into a focus rather than a
second channel beside it. This file tests the widened channel the way the spec's
§4.4 says to: post each mode on the route, read it back from the runtime *and*
from the file, restart the runtime object, and call the context tool.

The tests drive the real FastAPI app, not a stub. That matters for two reasons
this surface has already been bitten by:

* The production ``MCPContext`` is the ``_RuntimeAdapter`` defined inside
  ``scistudio.api.app.lifespan``, and it declares every member it exposes — a
  runtime field that the adapter does not forward never reaches a tool, however
  correct both ends are. Running under ``TestClient`` installs that adapter, so
  a missing forward fails here rather than in the desktop app.
* FR-002 restores the focus "exactly as it restores the active workflow id",
  which is a claim about a real project open, not about a helper call.

The fixtures are the three from ``tests/api/conftest.py``, restated here because
this file lives under ``tests/ai/`` — where the spec's affected-files table puts
it, since what is under test is what the agent is told.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp._focus import (
    FOCUS_FIELDS,
    FOCUS_MODES,
    MODE_CANVAS,
    MODE_EXPLORE,
    MODE_PAUSE,
    NoExploreSessionError,
    WorkspaceFocus,
    canvas_focus,
    effective_focus,
    focus_is_stale,
    refusal_message,
    resolve_session_path,
)
from scistudio.ai.agent.mcp.tools_workflow.read import get_active_workflow_context
from scistudio.api.app import create_app
from scistudio.api.runtime import ApiRuntime
from scistudio.api.runtime._projects import _FOCUS_FIELDS, _FOCUS_MODES

ACTIVE_CONTEXT = "/api/ai/active-context"
NOTEBOOK = "explore/qc.ipynb"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the runtime's user-level registry at an isolated home.

    Exposed rather than folded into ``client`` because the restart test builds a
    second app and must land in the *same* home — that is what makes the second
    runtime know the project the first one created.
    """
    home = tmp_path / "home"
    home.mkdir()
    from scistudio.api import runtime as runtime_module

    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture()
def client(fake_home: Path) -> Iterator[TestClient]:
    """A live app whose lifespan installs the production MCP context."""
    with TestClient(create_app()) as test_client:
        yield test_client


def _runtime_of(test_client: TestClient) -> ApiRuntime:
    """The ``ApiRuntime`` behind a client (``TestClient.app`` is typed as ASGI)."""
    return test_client.app.state.runtime  # type: ignore[attr-defined,no-any-return]


@pytest.fixture()
def runtime(client: TestClient) -> ApiRuntime:
    return _runtime_of(client)


@pytest.fixture()
def project(client: TestClient, tmp_path: Path) -> Path:
    parent = tmp_path / "projects"
    parent.mkdir()
    response = client.post(
        "/api/projects/",
        json={"name": "Focus Project", "description": "spec 5 focus", "path": str(parent)},
    )
    assert response.status_code == 200
    return Path(response.json()["path"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persisted(project_dir: Path) -> dict[str, Any]:
    """Return the parsed ``.scistudio/active_workflow.json`` — the file FR-002 names."""
    target = project_dir / ".scistudio" / "active_workflow.json"
    return json.loads(target.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write_notebook(project_dir: Path, relative: str = NOTEBOOK) -> Path:
    """Create a file where a focused session's notebook would be.

    Staleness is a question about the file, not about the session service, so a
    plausible empty notebook is enough and keeps this file from depending on the
    explore runtime.
    """
    target = project_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"cells": [], "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
    return target


def _context_result() -> Any:
    """Call the context tool against whatever MCP context is installed."""
    return asyncio.run(get_active_workflow_context())


CANVAS_REPORT = {"mode": MODE_CANVAS, "workflow_id": "calibration"}
EXPLORE_REPORT = {
    "mode": MODE_EXPLORE,
    "workflow_id": "calibration",
    "session_path": NOTEBOOK,
    "bound_run_id": "run-7",
    "current_cell_id": "cell-3",
}
PAUSE_REPORT = {
    "mode": MODE_PAUSE,
    "workflow_id": "calibration",
    "paused_node_id": "node-peaks",
    "paused_run_id": "run-9",
}


# ---------------------------------------------------------------------------
# FR-001 / FR-002 — the channel carries the focus, the file keeps it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        pytest.param(CANVAS_REPORT, {"mode": MODE_CANVAS, "workflow_id": "calibration"}, id="canvas"),
        pytest.param(
            EXPLORE_REPORT,
            {
                "mode": MODE_EXPLORE,
                "workflow_id": "calibration",
                "session_path": NOTEBOOK,
                "bound_run_id": "run-7",
                "current_cell_id": "cell-3",
            },
            id="explore",
        ),
        pytest.param(
            PAUSE_REPORT,
            {
                "mode": MODE_PAUSE,
                "workflow_id": "calibration",
                "paused_node_id": "node-peaks",
                "paused_run_id": "run-9",
            },
            id="pause",
        ),
    ],
)
def test_each_mode_round_trips_through_the_route_and_the_file(
    client: TestClient,
    runtime: ApiRuntime,
    project: Path,
    report: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """FR-001/FR-002: every mode reaches the runtime and the per-project file."""
    response = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": report})
    assert response.status_code == 200

    echoed = response.json()["focus"]
    assert echoed is not None
    for key, value in expected.items():
        assert echoed[key] == value, key
    # The record is complete whatever the mode reported, so a reader never has
    # to guess whether a missing key means "not applicable" or "older build".
    assert set(echoed) == set(FOCUS_FIELDS)
    # Stamped by the backend on receipt, not sent by the browser.
    assert echoed["reported_at"]
    assert report.get("reported_at") is None

    assert runtime.workspace_focus == echoed
    assert _persisted(project)["focus"] == echoed
    # The workflow id still travels the way it did before the focus existed.
    assert _persisted(project)["workflow_id"] == "calibration"


def test_the_focus_survives_a_backend_restart(client: TestClient, fake_home: Path, project: Path) -> None:
    """FR-002: a second runtime over the same project restores the focus.

    A genuine restart — a new app, a new ``ApiRuntime``, the same home and the
    same project directory — rather than a helper call, because "restores it on
    project open and on backend restart exactly as it restores the active
    workflow id" is a claim about the open path.
    """
    _write_notebook(project)
    reported = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})
    reported_at = reported.json()["focus"]["reported_at"]

    with TestClient(create_app()) as restarted:
        runtime = _runtime_of(restarted)
        project_id = next(iter(runtime.known_projects.keys()))
        assert restarted.get(f"/api/projects/{project_id}").status_code == 200

        assert runtime.active_workflow_id == "calibration"
        assert runtime.workspace_focus is not None
        assert runtime.workspace_focus["mode"] == MODE_EXPLORE
        assert runtime.workspace_focus["session_path"] == NOTEBOOK
        assert runtime.workspace_focus["bound_run_id"] == "run-7"
        assert runtime.workspace_focus["current_cell_id"] == "cell-3"
        # The receipt timestamp is the one the first process stamped, not a new
        # one: a restart is not a report.
        assert runtime.workspace_focus["reported_at"] == reported_at

        result = _context_result()
        assert result.mode == MODE_EXPLORE
        assert result.session_path == NOTEBOOK


def test_a_workflow_only_report_leaves_the_focus_alone(client: TestClient, runtime: ApiRuntime, project: Path) -> None:
    """FR-001: omitting ``focus`` says nothing about where the person is.

    This is what every caller written before ADR-054 sends — the store's own
    active-workflow sync among them — and it must not be able to tell the agent
    the person has left their notebook because a workflow loaded in the
    background.
    """
    _write_notebook(project)
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})

    response = client.post(ACTIVE_CONTEXT, json={"workflow_id": "other"})

    assert response.status_code == 200
    assert runtime.active_workflow_id == "other"
    assert runtime.workspace_focus is not None
    assert runtime.workspace_focus["mode"] == MODE_EXPLORE
    assert response.json()["focus"]["mode"] == MODE_EXPLORE


def test_an_explicit_null_focus_clears_it(client: TestClient, runtime: ApiRuntime, project: Path) -> None:
    """FR-001: ``focus: null`` is the frontend's way back to "never reported"."""
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": CANVAS_REPORT})
    assert runtime.workspace_focus is not None

    response = client.post(ACTIVE_CONTEXT, json={"focus": None})

    assert response.status_code == 200
    assert response.json()["focus"] is None
    assert runtime.workspace_focus is None
    assert "focus" not in _persisted(project)


def test_an_unreadable_mode_is_not_persisted(client: TestClient, runtime: ApiRuntime, project: Path) -> None:
    """A mode this build cannot read degrades to no focus, not to a 422.

    A backend that rejected a newer frontend's report would lose the channel
    entirely; dropping the record loses only the extra identifiers, and the
    canvas fallback still answers the agent's question conservatively.
    """
    response = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": {"mode": "hologram"}})

    assert response.status_code == 200
    assert response.json()["focus"] is None
    assert runtime.workspace_focus is None
    assert "focus" not in _persisted(project)
    assert _context_result().mode == MODE_CANVAS


def test_a_malformed_persistence_file_does_not_break_project_open(
    client: TestClient, fake_home: Path, project: Path
) -> None:
    """A file a newer build wrote, or a corrupted one, must not break the open."""
    target = project / ".scistudio" / "active_workflow.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"workflow_id": "calibration", "focus": ["not", "a", "record"]}', encoding="utf-8")

    runtime = _runtime_of(client)
    project_id = next(iter(runtime.known_projects.keys()))
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    assert runtime.active_workflow_id == "calibration"
    assert runtime.workspace_focus is None
    assert _context_result().mode == MODE_CANVAS


# ---------------------------------------------------------------------------
# FR-003 — the context tool reports the focus
# ---------------------------------------------------------------------------


def test_the_context_tool_reports_the_canvas_mode(client: TestClient, project: Path) -> None:
    """FR-003 acceptance 2: canvas carries the workflow id, as it does today."""
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": CANVAS_REPORT})

    result = _context_result()

    assert result.mode == MODE_CANVAS
    assert result.workflow_id == "calibration"
    assert result.session_path is None
    assert result.paused_node_id is None
    assert result.focus_stale is False


def test_the_context_tool_reports_the_explore_mode(client: TestClient, project: Path) -> None:
    """FR-003 acceptance 1: notebook path, bound run, and current cell."""
    _write_notebook(project)
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})

    result = _context_result()

    assert result.mode == MODE_EXPLORE
    assert result.session_path == NOTEBOOK
    assert result.bound_run_id == "run-7"
    assert result.current_cell_id == "cell-3"
    assert result.focus_stale is False
    # The workflow the person came from is still reported: switching to a
    # session does not close it.
    assert result.workflow_id == "calibration"


def test_the_context_tool_reports_the_pause_mode(client: TestClient, project: Path) -> None:
    """FR-003 acceptance 3: the paused node and its run."""
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": PAUSE_REPORT})

    result = _context_result()

    assert result.mode == MODE_PAUSE
    assert result.paused_node_id == "node-peaks"
    assert result.paused_run_id == "run-9"
    assert result.session_path is None


def test_a_never_reported_focus_reads_as_canvas_over_the_persisted_workflow(client: TestClient, project: Path) -> None:
    """FR-003: no focus ever reported is mode canvas with the persisted id.

    This is the additivity claim in its strongest form. The POST is the
    pre-ADR-054 one, byte for byte; the tool answers with today's two fields and
    a mode that says the same thing today's absence of a mode said.
    """
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration"})

    result = _context_result()

    assert result.mode == MODE_CANVAS
    assert result.workflow_id == "calibration"
    assert result.workflow_name == "calibration"
    assert result.focus_stale is False
    assert result.focus_reported_at is None
    assert result.session_path is None
    assert result.bound_run_id is None
    assert result.current_cell_id is None
    assert result.paused_node_id is None
    assert result.paused_run_id is None


def test_the_pre_focus_file_still_loads(client: TestClient, project: Path) -> None:
    """A persistence file written before this build behaves exactly as it did."""
    target = project / ".scistudio" / "active_workflow.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"workflow_id": "calibration"}), encoding="utf-8")

    runtime = _runtime_of(client)
    project_id = next(iter(runtime.known_projects.keys()))
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    assert runtime.active_workflow_id == "calibration"
    assert runtime.workspace_focus is None
    result = _context_result()
    assert (result.workflow_id, result.workflow_name, result.mode) == ("calibration", "calibration", MODE_CANVAS)


def test_a_context_without_the_member_degrades_to_today(tmp_path: Path) -> None:
    """A context implementation predating the focus must not raise.

    Third-party adapters and older test stubs satisfy the pre-ADR-054 Protocol
    and nothing more. ``effective_focus`` reads the member with ``getattr`` for
    exactly this case, and the answer is the canvas fallback.
    """

    class _OldContext:
        active_workflow_id = "calibration"
        project_dir = tmp_path

    focus = effective_focus(_OldContext())  # type: ignore[arg-type]

    assert focus == WorkspaceFocus(mode=MODE_CANVAS, workflow_id="calibration")


# ---------------------------------------------------------------------------
# FR-004 — a focus over a notebook that is gone is stale
# ---------------------------------------------------------------------------


def test_a_focus_naming_a_missing_notebook_is_reported_stale(client: TestClient, project: Path) -> None:
    """FR-004: the notebook was deleted or moved after the focus was reported."""
    notebook = _write_notebook(project)
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})
    assert _context_result().focus_stale is False

    notebook.unlink()

    result = _context_result()
    assert result.mode == MODE_EXPLORE
    assert result.session_path == NOTEBOOK
    assert result.focus_stale is True


def test_only_an_explore_focus_can_be_stale(tmp_path: Path) -> None:
    """A canvas focus over a deleted workflow is the workflow tool's business,
    and a pause focus names a run rather than a file."""
    assert focus_is_stale(canvas_focus("gone"), tmp_path) is False
    assert focus_is_stale(WorkspaceFocus(mode=MODE_PAUSE, paused_node_id="n", paused_run_id="r"), tmp_path) is False
    assert focus_is_stale(WorkspaceFocus(mode=MODE_EXPLORE), tmp_path) is False


def test_a_focus_escaping_the_project_is_stale(tmp_path: Path) -> None:
    """A session path that resolves outside the project is not actionable.

    The focus arrives over HTTP, so it is caller input like any other and goes
    through the same containment check every other agent-supplied path does.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside = tmp_path / "outside.ipynb"
    outside.write_text("{}", encoding="utf-8")

    focus = WorkspaceFocus(mode=MODE_EXPLORE, session_path="../outside.ipynb")

    assert focus_is_stale(focus, project_dir) is True


# ---------------------------------------------------------------------------
# FR-005 — the refusal every session tool makes
# ---------------------------------------------------------------------------


def test_the_refusal_names_the_way_to_open_a_session_from_the_canvas(client: TestClient, project: Path) -> None:
    """FR-005 acceptance 4: on the canvas, a session tool refuses and recovers.

    The message has to let the agent act in one step, so it is asserted to name
    the tool and both of its sources — a refusal that only reported the decline
    would send the agent back to the person.
    """
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": CANVAS_REPORT})

    with pytest.raises(NoExploreSessionError) as excinfo:
        resolve_session_path()

    message = str(excinfo.value)
    assert "No explore session is active" in message
    assert "open_explore_session" in message
    assert "block_outputs" in message
    assert "session_path" in message


def test_the_refusal_says_a_stale_focus_is_stale(client: TestClient, project: Path) -> None:
    """FR-004/FR-005: naming the dead notebook is what stops the agent retrying.

    Without it the agent sees the same refusal it would see on the canvas, and
    the obvious recovery — report the focus again — is the one that cannot work.
    """
    notebook = _write_notebook(project)
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})
    notebook.unlink()

    with pytest.raises(NoExploreSessionError) as excinfo:
        resolve_session_path()

    message = str(excinfo.value)
    assert NOTEBOOK in message
    assert "stale" in message
    assert "open_explore_session" in message


def test_a_pause_focus_refuses_like_the_canvas(client: TestClient, project: Path) -> None:
    """Only an explore focus names a session; a pause is not one."""
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": PAUSE_REPORT})

    with pytest.raises(NoExploreSessionError):
        resolve_session_path()


def test_the_focused_session_is_the_default(client: TestClient, project: Path) -> None:
    """FR-005: every session tool acts on the focused session by default."""
    _write_notebook(project)
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})

    assert resolve_session_path() == NOTEBOOK


def test_an_explicit_path_wins_over_the_focus(client: TestClient, project: Path) -> None:
    """FR-005: an agent may work in a session the person is not looking at.

    Including over a stale focus — that escape hatch is the whole point, and a
    refusal that fired anyway would make it unreachable exactly when it is most
    useful. Existence is the session API's answer to give, not this helper's.
    """
    client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})

    assert resolve_session_path("explore/other.ipynb") == "explore/other.ipynb"
    # Windows separators and a leading ``./`` normalise to the one spelling
    # ``SessionService.session_for`` addresses a session by.
    assert resolve_session_path(r".\explore\other.ipynb") == "explore/other.ipynb"


def test_the_refusal_holds_with_no_context_installed() -> None:
    """No project, no app, no context: the tools still refuse rather than raise.

    The standalone MCP bridge is in exactly this state, and the refusal is what
    makes FR-005 hold there by construction.
    """
    with pytest.raises(NoExploreSessionError):
        resolve_session_path(ctx=None)

    assert refusal_message() == refusal_message(stale_path=None)
    assert "no longer exists" in refusal_message(stale_path="explore/gone.ipynb")


# ---------------------------------------------------------------------------
# The record's shape, on both sides of the layer boundary
# ---------------------------------------------------------------------------


def test_the_two_layers_agree_on_the_focus_record() -> None:
    """The API's field list and the AI layer's must not drift apart.

    They are written out twice because ``scistudio.api.runtime`` must not import
    ``scistudio.ai.agent.mcp._focus`` — that executes the MCP package's
    ``__init__``, which eagerly imports every tool module and FastMCP. The
    duplication is deliberate; this assertion is what keeps it honest, and
    ``docs/planning/adr-054-assembly-followups.md`` F-B1-2 records the durable
    fix.
    """
    assert FOCUS_FIELDS == _FOCUS_FIELDS
    assert FOCUS_MODES == _FOCUS_MODES
    assert set(FOCUS_FIELDS) == set(WorkspaceFocus().as_dict())


def test_a_focus_mapping_round_trips_through_the_record() -> None:
    """``as_dict`` and ``from_mapping`` are inverses over the wire shape."""
    focus = WorkspaceFocus(
        mode=MODE_EXPLORE,
        workflow_id="calibration",
        session_path=NOTEBOOK,
        bound_run_id="run-7",
        current_cell_id="cell-3",
        reported_at="2026-09-05T00:00:00Z",
    )

    assert WorkspaceFocus.from_mapping(focus.as_dict()) == focus


@pytest.mark.parametrize("raw", [None, {}, [], "canvas", {"mode": None}, {"mode": "hologram"}])
def test_an_unusable_mapping_is_no_focus(raw: Any) -> None:
    """Anything the parser cannot recognise means "never reported"."""
    assert WorkspaceFocus.from_mapping(raw) is None
