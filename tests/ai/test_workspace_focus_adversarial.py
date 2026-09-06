"""Adversarial tests against the workspace focus: can it lie to the agent?

ADR-054 spec 5, FR-001 to FR-005 (issue #2254). Adversarial pass, agent S5-D1.

The owner's one hard requirement for spec 5 is that **the agent must always know
whether the person is on the canvas or in an explore session**. Every other
thing spec 5 builds is in service of that. ``tests/ai/test_workspace_focus.py``
proves the channel *carries* the focus: each mode round-trips through the route
and the file, a restart restores it, and the context tool reports it. What it
does not ask is the question this file exists for:

    **Is there a state in which the agent believes it knows where the person
    is, and is wrong?**

There are three, and each has its own test below. They share a shape: the focus
is a *report* about a moment, and it is read as a *fact* about now. Nothing
between the report and the read carries the difference.

The three tests that prove a defect are marked ``xfail(strict=True)`` rather
than left hard-red. The assertion in each body is the behaviour the owner's
requirement demands, written unweakened; the marker records that the current
implementation does not deliver it, keeps the assembly's CI honest about what
is a *new* failure, and turns into a loud failure the moment someone fixes the
defect without deleting the marker. Every one is registered in
``docs/planning/adr-054-assembly-followups.md`` under ``### S4-D1 / S5-D1``.

The fixtures and helpers are imported from ``tests/ai/test_workspace_focus.py``
on purpose: what makes a finding here credible is that it is reached through
exactly the harness the passing tests use — the real FastAPI app, the real
``_RuntimeAdapter`` MCP context, and a real project on disk. Only non-``test_``
names are imported, so pytest collects each test once.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.mcp._focus import (
    MODE_CANVAS,
    MODE_EXPLORE,
    NoExploreSessionError,
    WorkspaceFocus,
    focus_is_stale,
    resolve_session_path,
)
from scistudio.api.app import create_app
from scistudio.api.runtime import ApiRuntime
from tests.ai.test_workspace_focus import (
    ACTIVE_CONTEXT,
    EXPLORE_REPORT,
    NOTEBOOK,
    _context_result,
    _create_project,
    _persisted,
    _point_home_at,
    _runtime_of,
    _write_notebook,
)

# ---------------------------------------------------------------------------
# Fixtures — the same shape as the module they adversarially mirror
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _adversarial_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """One isolated SciStudio home for this module, as the sibling module does."""
    home = tmp_path_factory.mktemp("focus-adversarial-home")
    with pytest.MonkeyPatch.context() as monkeypatch:
        _point_home_at(home, monkeypatch)
        yield home


@pytest.fixture(scope="module")
def client(_adversarial_home: Path) -> Iterator[TestClient]:
    """One live app for the module: the production ``_RuntimeAdapter`` is per-process."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _keep_the_module_context(client: TestClient) -> Iterator[None]:
    """Restore the process-global MCP context after every test.

    The restart test stands up two further apps, and ``api.app.lifespan``
    clears the global slot on the way down. Snapshotting keeps that coupling
    local to the test that causes it.
    """
    from scistudio.ai.agent.mcp import _context as mcp_context

    installed = mcp_context.get_optional_context()
    try:
        yield
    finally:
        mcp_context.set_context(installed)


@pytest.fixture()
def runtime(client: TestClient) -> ApiRuntime:
    return _runtime_of(client)


@pytest.fixture()
def project(client: TestClient, tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    """A fresh project, opened, for this test alone."""
    return _create_project(client, tmp_path / "projects", f"Adversarial {request.node.name}").path


# ---------------------------------------------------------------------------
# DEFECT D1 — a mode this build cannot read moves the person to the canvas
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT S5-D1-001 (P2): an unrecognised mode arriving over a live explore focus "
        "clears the focus, and the context tool then asserts mode=canvas for a person who "
        "is demonstrably not on the canvas. See docs/planning/adr-054-assembly-followups.md, "
        "'### S4-D1 / S5-D1 (adversarial testing)'."
    ),
)
def test_an_unreadable_mode_over_a_live_explore_focus_must_not_report_the_person_onto_the_canvas(
    client: TestClient, runtime: ApiRuntime, project: Path
) -> None:
    """Proves: a newer frontend can silently move the agent's idea of the person to the canvas.

    ``_normalise_focus`` degrades an unrecognised mode to ``None`` — "no focus
    was ever reported" — and ``effective_focus`` reads that as
    :data:`MODE_CANVAS` over the persisted workflow (FR-003). Both halves are
    deliberate and documented. Composed, they are not conservative: a build
    whose frontend has learned a fourth mode reports it, this backend drops the
    record, and the context tool answers ``canvas`` — an assertion about where
    the person is, not an admission that it does not know. The agent then
    proposes a workflow edit to somebody who is in a notebook, which is the
    exact damage FR-003's own rationale names.

    Why the existing tests did not ask: ``test_an_unreadable_mode_is_not
    _persisted`` posts the unreadable mode into a workspace that had **no focus
    at all**, where degrading to canvas costs nothing. It never posts one over a
    focus that was already explore, so the case where the fallback *overwrites a
    known truth with a different one* is untested.

    What the fix must deliver (either is acceptable): keep the last readable
    focus, or report a mode the agent can recognise as "unknown". Asserting
    ``canvas`` is the one answer that is affirmatively wrong.
    """
    _write_notebook(project)
    reported = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})
    assert reported.status_code == 200
    assert _context_result().mode == MODE_EXPLORE, "precondition: the person is in a session"

    # A build newer than this backend reports a mode it has never heard of.
    response = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": {"mode": "diff"}})
    assert response.status_code == 200

    result = _context_result()
    assert result.mode != MODE_CANVAS, (
        f"the person was in an explore session and the backend was told about a mode it cannot read; "
        f"answering mode={result.mode!r} tells the agent the person is on the canvas, which is a "
        f"different wrong answer from 'I do not know'. focus_stale={result.focus_stale}"
    )


# ---------------------------------------------------------------------------
# DEFECT D2 — a focus restored after a restart looks exactly like a live one
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT S5-D1-002 (P2): after a backend restart the restored focus reports "
        "mode=explore with focus_stale=false although no session exists in the new process "
        "and the frontend has reported nothing since it started. The agent cannot tell a "
        "restored focus from a live one. See docs/planning/adr-054-assembly-followups.md."
    ),
)
def test_a_focus_restored_after_a_restart_must_be_distinguishable_from_a_live_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves: FR-002's restore hands the agent a report that predates the process as a fact about now.

    FR-002 requires the focus to survive a restart, and it does. But a restart
    is the one moment at which the focus is guaranteed *not* to describe a live
    session: the new process's ``SessionService`` holds no sessions at all, and
    the frontend has not reported since it came up. The notebook file is still
    on disk, so :func:`focus_is_stale` — which asks only about the file — says
    the focus is live, and the context tool answers ``mode=explore``,
    ``focus_stale=False``. The agent then appends and runs cells "in the
    person's session", and what it is really doing is opening a session of its
    own that nobody is looking at.

    ``focus_reported_at`` is returned, but it is the only clue and it is not
    usable on its own: the agent has no backend start time to compare it
    against, and the tool's own documentation offers none.

    Why the existing tests did not ask: ``test_the_focus_survives_a_backend
    _restart`` asserts precisely that the restored record is *identical* to the
    reported one — including ``reported_at`` — and treats that identity as the
    success condition. Identity is exactly the problem: it is what leaves the
    agent unable to tell the two situations apart.

    What the fix must deliver: something in the answer that separates "the
    frontend told me this while I was running" from "I read this off disk when I
    started". A ``focus_stale`` of true is the cheapest; a field naming the
    restore is the more useful.
    """
    home = tmp_path / "home"
    home.mkdir()
    _point_home_at(home, monkeypatch)

    with TestClient(create_app()) as first:
        opened = _create_project(first, tmp_path / "projects", "Adversarial Restart")
        _write_notebook(opened.path)
        assert first.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT}).status_code

    with TestClient(create_app()) as restarted:
        assert restarted.get(f"/api/projects/{opened.id}").status_code == 200
        service_sessions = restarted.get("/api/explore/sessions")
        assert service_sessions.status_code == 200

        result = _context_result()
        assert result.mode == MODE_EXPLORE, "precondition: FR-002 restored the explore focus"

        # Nothing is open. The focus says otherwise, and says it as a live fact.
        assert result.focus_stale is True, (
            "a focus read off disk at startup describes a session that cannot exist yet: the new "
            "process holds no sessions and the frontend has reported nothing. Reporting "
            "focus_stale=false makes a restored report indistinguishable from a live one."
        )


# ---------------------------------------------------------------------------
# DEFECT D3 — closing the session does not make the focus stale
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT S5-D1-003 (P2): FR-004 defines staleness as a question about the notebook "
        "file, so closing the session leaves the focus reading as a live explore session. "
        "The session tools then silently open a second session nobody is looking at. "
        "See docs/planning/adr-054-assembly-followups.md."
    ),
)
def test_a_focus_whose_session_has_been_closed_must_not_read_as_a_live_session(
    client: TestClient, project: Path
) -> None:
    """Proves: FR-004's staleness test asks about the file when the question is about the session.

    The person opens a session, the frontend reports the focus, the person
    closes the session. ``SessionService.close`` drops it from the registry and
    leaves the notebook on disk — that is what closing a notebook means. The
    focus still names it; :func:`focus_is_stale` stats the file, finds it, and
    reports the focus live. The context tool answers ``mode=explore``,
    ``focus_stale=False``, and every session tool proceeds — through
    ``SessionService.open_notebook``, which is idempotent and therefore *opens a
    brand-new session* rather than refusing.

    So the agent believes it is appending a cell into the notebook the person is
    looking at, and the person is looking at nothing.

    Why the existing tests did not ask: ``tests/ai/test_workspace_focus.py``
    states the assumption in its own helper — "staleness is a question about the
    file, not about the session service" — and its notebook fixture is a file
    written directly to disk with no session ever opened over it. Every
    staleness test in that module therefore runs in a world that already has no
    session, and calls that world *not stale*. This test opens a real session
    first, so the transition from "there is one" to "there is not" is visible.

    What the fix must deliver: staleness that consults the session registry, or
    a frontend contract that clears the focus on close plus a backend that does
    not trust a focus naming a session the service does not hold.
    """
    data_file = project / "data" / "spectra.csv"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("wavelength,intensity\n400,1.0\n", encoding="utf-8")

    opened = client.post("/api/explore/sessions", json={"source": "file", "path": "data/spectra.csv"})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    session_id = body["session_id"]
    session_path = body["notebook_path"]

    reported = client.post(
        ACTIVE_CONTEXT,
        json={"workflow_id": "calibration", "focus": {"mode": MODE_EXPLORE, "session_path": session_path}},
    )
    assert reported.status_code == 200
    assert _context_result().mode == MODE_EXPLORE, "precondition: the person is in a real session"

    closed = client.delete(f"/api/explore/sessions/{session_id}", params={"commit": "false"})
    assert closed.status_code == 200, closed.text
    assert session_id not in {row["session_id"] for row in client.get("/api/explore/sessions").json()["sessions"]}

    result = _context_result()
    assert result.focus_stale is True, (
        f"the session the focus names has been closed and is no longer in the service's registry, "
        f"but focus_stale={result.focus_stale} and mode={result.mode!r}. A session tool called now "
        f"opens a second session over the same notebook and reports success."
    )


# ---------------------------------------------------------------------------
# The places the implementation holds — pushed, and found correct
# ---------------------------------------------------------------------------


def test_a_focus_never_reported_refuses_the_session_tools_and_names_the_recovery(
    client: TestClient, project: Path
) -> None:
    """Proves the never-reported case refuses with the *content* FR-005 requires.

    Why the existing tests did not ask this exactly: the module's refusal tests
    parametrise ``MODE_CANVAS`` and ``MODE_PAUSE`` — both of which require a
    focus to have been reported — and the one no-focus case
    (``test_the_refusal_holds_with_no_context_installed``) removes the *context*
    rather than the focus. The state a freshly opened project is actually in —
    a live context whose ``workspace_focus`` is ``None`` — is asserted here.

    The refusal is asserted by content, not by type: FR-005 requires it to say
    how to open a session, and an exception that merely declines is not the
    guarantee the spec is buying.
    """
    assert _runtime_of(client).workspace_focus is None, "precondition: nothing has been reported"

    with pytest.raises(NoExploreSessionError) as refusal:
        resolve_session_path()

    message = str(refusal.value)
    assert "No explore session is active" in message
    assert "open_explore_session" in message, "the refusal must name the tool that recovers from it"
    assert "block_outputs" in message and "file" in message, "and the arguments that tool takes"
    assert "session_path" in message, "and the escape hatch for a session the person is not looking at"


def test_a_focus_does_not_leak_across_a_project_switch(
    client: TestClient, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """Proves two open projects cannot be confused for one another, even at the same path.

    The dangerous shape is two projects that both contain ``explore/qc.ipynb``:
    a focus restored from the wrong project would name a notebook that exists,
    would therefore not be stale, and would send the agent into the wrong
    person's file. ``_load_active_workflow_id_from_disk`` runs on every open and
    replaces both fields from *that* project's disk, so it cannot happen.

    Why the existing tests did not ask: every test in the sibling module uses a
    single project per test, so the cross-project read is never exercised.
    Pushed here, and the implementation is correct.
    """
    parent = tmp_path / "projects"
    first = _create_project(client, parent, f"Switch A {request.node.name}")
    _write_notebook(first.path)
    assert client.post(ACTIVE_CONTEXT, json={"workflow_id": "wf-a", "focus": EXPLORE_REPORT}).status_code == 200

    second = _create_project(client, parent, f"Switch B {request.node.name}")
    _write_notebook(second.path)  # the same relative path exists in both projects

    # Opening B must not carry A's focus over, even though B has a file there.
    after_switch = _context_result()
    assert after_switch.mode == MODE_CANVAS
    assert after_switch.session_path is None
    assert _runtime_of(client).workspace_focus is None

    # And going back to A restores A's own focus rather than B's absence.
    assert client.get(f"/api/projects/{first.id}").status_code == 200
    back = _context_result()
    assert back.mode == MODE_EXPLORE
    assert back.session_path == NOTEBOOK
    assert back.workflow_id == "calibration"


def test_editing_the_persistence_file_underneath_does_not_change_the_live_focus(
    client: TestClient, runtime: ApiRuntime, project: Path, request: pytest.FixtureRequest
) -> None:
    """Proves the running process's focus is memory, not the file, and stays consistent.

    The file is a mirror for the *next* process, not the source of truth for
    this one. Truncating it, emptying it, or filling it with a different focus
    while the backend runs must not move the agent's answer, and the next report
    must overwrite whatever a third party left there rather than merging with
    it.

    Why the existing tests did not ask: the sibling module writes a malformed
    file and then *opens a project*, which is the read path. Nobody edits the
    file while the process is live, which is what a person poking at
    ``.scistudio/`` or a half-finished write from a killed sibling process
    actually looks like.

    Pushed here, and the implementation is correct.
    """
    _write_notebook(project)
    assert client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT}).status_code == 200

    target = project / ".scistudio" / "active_workflow.json"
    target.write_text("", encoding="utf-8")  # truncated by a killed writer

    unchanged = _context_result()
    assert unchanged.mode == MODE_EXPLORE
    assert unchanged.session_path == NOTEBOOK

    target.write_text(
        json.dumps({"workflow_id": "hijack", "focus": {"mode": MODE_EXPLORE, "session_path": "explore/theirs.ipynb"}}),
        encoding="utf-8",
    )
    assert _context_result().session_path == NOTEBOOK, "a file edit is not a report"

    # The next real report rewrites the file whole rather than merging.
    assert client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": {"mode": MODE_CANVAS}}).status_code
    persisted = _persisted(project)
    assert persisted["workflow_id"] == "calibration"
    assert persisted["focus"]["mode"] == MODE_CANVAS
    assert persisted["focus"]["session_path"] is None
    assert runtime.workspace_focus is not None
    assert runtime.workspace_focus["mode"] == MODE_CANVAS


def test_two_reports_in_a_row_leave_the_echo_the_runtime_and_the_file_agreeing(
    client: TestClient, runtime: ApiRuntime, project: Path
) -> None:
    """Proves the three places a focus lives cannot disagree after back-to-back reports.

    A focus that is right in memory and wrong on disk, or right on disk and
    wrong in the response the frontend just got, is a focus that lies to
    somebody. ``set_workspace_focus`` assigns and then republishes from the
    field it just assigned, so the last write wins in all three places rather
    than in two of them; ``reported_at`` is stamped server-side, so it orders by
    arrival rather than by the browser's clock.

    Why the existing tests did not ask: each round-trip test in the sibling
    module posts one report into a fresh project and reads it back. Two reports
    in sequence — the shape a person tabbing between the canvas and a notebook
    actually produces — are never sent.

    Pushed here, and the implementation is correct.
    """
    _write_notebook(project)

    first = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": EXPLORE_REPORT})
    second = client.post(ACTIVE_CONTEXT, json={"workflow_id": "calibration", "focus": {"mode": MODE_CANVAS}})
    assert first.status_code == 200 and second.status_code == 200

    echoed = second.json()["focus"]
    assert echoed["mode"] == MODE_CANVAS
    assert echoed == runtime.workspace_focus, "the echo the frontend got is the record the runtime holds"
    assert echoed == _persisted(project)["focus"], "and the record the runtime holds is the one on disk"
    assert echoed["reported_at"] >= first.json()["focus"]["reported_at"], (
        "reported_at is stamped on arrival, so the later report can never carry the earlier stamp"
    )
    assert _context_result().mode == MODE_CANVAS


def test_a_canvas_focus_over_a_workflow_that_no_longer_exists_is_reported_as_live(
    client: TestClient, project: Path
) -> None:
    """Characterises a gap FR-004 deliberately leaves open, so it is visible rather than assumed.

    FR-004 makes only an *explore* focus stale, and the spec says why: "a canvas
    focus over a deleted workflow is the existing tool's business". This test
    pins what that business currently is, because the answer is not obvious from
    the requirement and an agent reading the result cannot tell the two cases
    apart: ``workflow_name`` falls back to ``workflow_id`` both when the YAML
    carries no title *and* when there is no YAML at all.

    This is asserted as it behaves rather than as a defect: the behaviour
    predates spec 5 (ADR-040 Addendum 5) and FR-003 requires the existing fields
    to be unchanged. It is registered as a P3 follow-up so the ambiguity is
    tracked rather than rediscovered.

    Why the existing tests did not ask: the sibling module's canvas tests always
    name a workflow, and never check whether that workflow exists.
    """
    response = client.post(ACTIVE_CONTEXT, json={"workflow_id": "deleted-workflow", "focus": {"mode": MODE_CANVAS}})
    assert response.status_code == 200
    assert not (project / "workflows" / "deleted-workflow.yaml").exists()

    result = _context_result()
    assert result.mode == MODE_CANVAS
    assert result.focus_stale is False, "FR-004 scopes staleness to explore focuses"
    assert result.workflow_id == "deleted-workflow"
    # The gap: this is byte-identical to an existing workflow whose YAML has no title.
    assert result.workflow_name == "deleted-workflow"


def test_a_focus_reported_with_no_project_open_is_stale_rather_than_actionable() -> None:
    """Proves the no-project case fails closed at the unit the tools call.

    ``focus_is_stale`` cannot check a notebook it has no root to resolve
    against, and answers *stale* rather than *live* — which is the only safe
    direction, because the tools' contract is that a non-stale explore focus can
    be acted on.

    Why the existing tests did not ask: the sibling module asserts a focus
    *escaping* the project is stale, which exercises the containment branch. The
    branch where ``project_dir`` is ``None`` — a report that arrived before a
    project was open, or after one was closed — is a different early return.

    Pushed here, and the implementation is correct.
    """
    focus = WorkspaceFocus(mode=MODE_EXPLORE, session_path=NOTEBOOK)

    assert focus_is_stale(focus, None) is True

    class _NoProject:
        project_dir = None
        active_workflow_id = None
        workspace_focus: ClassVar[dict[str, Any]] = {"mode": MODE_EXPLORE, "session_path": NOTEBOOK}

    with pytest.raises(NoExploreSessionError) as refusal:
        resolve_session_path(ctx=_NoProject())  # type: ignore[arg-type]
    assert "stale" in str(refusal.value)
    assert "open_explore_session" in str(refusal.value)
