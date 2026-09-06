"""Adversarial tests against the session MCP tools: the refusal, and the thinness rule.

ADR-054 spec 5, FR-005, FR-019, FR-021, FR-023, FR-024 (issue #2254).
Adversarial pass, agent S5-D1.

``tests/ai/test_mcp_tools_explore.py`` scripts the session API with a
:class:`_Service` whose ``open_notebook`` accepts **every** path and never
raises. That is the right shape for asserting what each tool *asks* of the API,
and it is the reason three whole classes of caller input have never reached the
session service in a test: a path that is not there, a path that is there but is
not a notebook, and a path that walks out of the project. Half of this file
drives a **real** :class:`~scistudio.explore.session.SessionService` over a real
temporary project so those three land where they really land, and asserts the
refusal by its **content** — FR-005 buys a message that lets the agent recover
in one step, and an exception that merely declines is not that.

The other half is FR-024 stated the way the spec states it — "every session tool
MUST go through the session API and MUST NOT reach the kernel, the notebook
file, or the queue" — but *derived* rather than restated. The sibling module
holds the rule with a hand-written blacklist of attribute names. A blacklist is
right until :class:`~scistudio.explore.session.ExploreSession` grows a
fifty-second public member, at which point it silently stops covering the
surface it names. The tests here invert it: the members the tools may touch are
an explicit allowlist checked against the AST, and the members they may not are
computed from the session class itself, so a new kernel-, queue- or
bridge-shaped member is covered on the day it is added.

Findings that prove a defect are ``xfail(strict=True)`` with the assertion
written unweakened, and every one is registered in
``docs/planning/adr-054-assembly-followups.md`` under ``### S4-D1 / S5-D1``.
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Coroutine, Iterator
from pathlib import Path
from typing import Any, ClassVar, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp import tools_explore as tools_explore_pkg
from scistudio.ai.agent.mcp._focus import MODE_EXPLORE
from scistudio.ai.agent.mcp.tools_explore import (
    _service,
    append_cell,
    check_packaging,
    get_bindings,
    open_explore_session,
    package_notebook,
    read_notebook,
    run_cell,
)
from scistudio.explore.session import ExploreSession, PathEscapesProjectError
from tests.ai.test_mcp_tools_explore import _Service, _Session, _StubContext

_T = TypeVar("_T")

PACKAGE_ROOT = Path(tools_explore_pkg.__file__).resolve().parent
NOTEBOOK = "explore/qc.ipynb"

#: An empty but valid notebook — enough for ``NotebookStore.read`` to answer.
EMPTY_NOTEBOOK = json.dumps({"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run one tool coroutine. The repository does not install pytest-asyncio."""
    return asyncio.run(coro)


#: Every tool that resolves a session before acting. ``open_explore_session`` is
#: absent because it creates one; it has its own FR-019 tests below.
FOCUSED_TOOLS: tuple[tuple[str, Any, dict[str, Any]], ...] = (
    ("read_notebook", read_notebook, {}),
    ("append_cell", append_cell, {"source": "x = 1"}),
    ("run_cell", run_cell, {"cell_id": "cell-a"}),
    ("get_bindings", get_bindings, {}),
    ("check_packaging", check_packaging, {}),
    ("package_notebook", package_notebook, {"block_name": "qc"}),
)
_TOOL_IDS = [entry[0] for entry in FOCUSED_TOOLS]


# ---------------------------------------------------------------------------
# A real project, a real session service — the half the scripted API cannot reach
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_project(tmp_path: Path) -> Path:
    """A project directory with one real notebook, one data file, and a sibling outside it."""
    root = tmp_path / "project"
    (root / "explore").mkdir(parents=True)
    (root / "explore" / "qc.ipynb").write_text(EMPTY_NOTEBOOK, encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "spectra.csv").write_text("wavelength,intensity\n400,1.0\n", encoding="utf-8")
    (tmp_path / "outside.ipynb").write_text(EMPTY_NOTEBOOK, encoding="utf-8")
    return root


@pytest.fixture()
def real_ctx(real_project: Path) -> Iterator[Any]:
    """An MCP context whose session service is a real one over ``real_project``."""
    from scistudio.explore.session import SessionService

    class _RealContext:
        project_dir = real_project
        active_workflow_id = "wf-1"
        workspace_focus: ClassVar[dict[str, Any]] = {"mode": MODE_EXPLORE, "session_path": NOTEBOOK}

        def __init__(self) -> None:
            self._svc = SessionService(real_project)

        def get_session_service(self) -> Any:
            return self._svc

    stub = _RealContext()
    _context.set_context(stub)  # type: ignore[arg-type]
    _service.reset_fallback_services()
    try:
        yield stub
    finally:
        _context.set_context(None)
        _service.reset_fallback_services()


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=_TOOL_IDS)
def test_an_explicit_path_that_is_not_there_refuses_and_names_how_to_open_a_session(
    real_ctx: Any, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    """Proves FR-005's recovery message survives the explicit-path branch too.

    An agent that names a session the person does not have is the ordinary
    mistake this branch exists to absorb, and the refusal has to be as
    actionable as the no-focus one — otherwise the agent's recovery depends on
    which of two ways it got the path wrong.

    Why the existing tests did not ask: the scripted ``_Service.open_notebook``
    in ``test_mcp_tools_explore.py`` returns a session for *any* string, so no
    test in that module has ever seen ``session_for`` raise. Only a real
    ``SessionService`` reads the file, and only reading it produces the
    ``FileNotFoundError`` that ``session_for`` translates.

    Pushed here, and the implementation is correct.
    """
    with pytest.raises(_service.SessionToolError) as refusal:
        _run(tool(session_path="explore/never-existed.ipynb", **kwargs))

    message = str(refusal.value)
    assert "explore/never-existed.ipynb" in message, "the refusal must name the path it could not find"
    assert "open_explore_session" in message, "and the tool that recovers from it"
    assert "get_active_workflow_context" in message, "and how to find out where the person actually is"


@pytest.mark.parametrize("name,tool,kwargs", FOCUSED_TOOLS, ids=_TOOL_IDS)
def test_an_explicit_path_outside_the_project_is_contained_by_the_session_api(
    real_ctx: Any, real_project: Path, name: str, tool: Any, kwargs: dict[str, Any]
) -> None:
    """Proves the traversal hole that ``resolve_session_path`` leaves open is closed downstream.

    :func:`scistudio.ai.agent.mcp._focus.resolve_session_path` normalises an
    explicit path but deliberately does **not** contain it — its docstring says
    the session API owns that answer. That is a real division of labour and it
    is worth proving rather than assuming, because every other MCP tool that
    takes a path is contained *in the tool layer* by ``_safe_under`` (#790), so
    a reader checking this one for the same guard finds nothing and has to trust
    a comment. ``SessionService._contained_relative`` is the guard, and it
    refuses a ``..`` walk before any file is read.

    Why the existing tests did not ask: the scripted service has no containment
    at all, so ``_run(tool(session_path="../../anything"))`` succeeds in that
    module. The escape is only observable against the real service.

    Pushed here, and the implementation is correct: the file outside the project
    exists and is a valid notebook, and it is still refused.
    """
    escape = "../outside.ipynb"
    assert (real_project.parent / "outside.ipynb").is_file(), "precondition: the target really is readable"

    with pytest.raises(PathEscapesProjectError) as refusal:
        _run(tool(session_path=escape, **kwargs))

    assert "outside this project" in str(refusal.value)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT S5-D1-004 (P3): the refusals for an explicit path that escapes the project, and "
        "for one that is not a notebook, do not name how to open a session, and the second leaks "
        "the backend's absolute filesystem path into the agent's context. Only the "
        "not-there case is translated. See docs/planning/adr-054-assembly-followups.md."
    ),
)
def test_every_explicit_path_refusal_names_how_to_open_a_session(real_ctx: Any) -> None:
    """Proves two of the three bad-explicit-path refusals hand the agent a dead end.

    FR-005 makes the refusal the enforcement, and §4.1 says why: "the refusal
    names the way to open a session, so the agent can recover in one step".
    ``session_for`` delivers that for exactly one of the three ways an explicit
    path can be wrong — the file is missing — because it translates only
    ``FileNotFoundError``. The other two propagate raw from the session API:

    * a path outside the project raises ``PathEscapesProjectError``, whose
      message cites *FR-002 of another spec* at an agent that has never read it;
    * a path that exists but is not a notebook raises ``NotebookStoreError``
      carrying a JSON parser message and the **absolute path of the file on the
      backend's disk**, which is both unactionable and a needless disclosure
      into the agent's context window.

    Why the existing tests did not ask: the scripted service raises neither, so
    the sibling module's refusal tests all exercise the ``NoExploreSessionError``
    path and none of them reaches ``session_for``'s translation layer at all.

    What the fix must deliver: ``session_for`` translating these two the way it
    already translates the missing file — the reason, then
    :data:`scistudio.ai.agent.mcp._focus.OPEN_SESSION_HINT`.
    """
    messages: dict[str, str] = {}
    for label, path in (("escaping", "../outside.ipynb"), ("not a notebook", "data/spectra.csv")):
        with pytest.raises(Exception) as refusal:  # the exception class is itself the finding
            _run(read_notebook(session_path=path))
        messages[label] = str(refusal.value)

    unhelpful = {label: text for label, text in messages.items() if "open_explore_session" not in text}
    assert unhelpful == {}, (
        f"FR-005 §4.1: a session tool's refusal names the way to open a session so the agent "
        f"recovers in one step. These do not: {unhelpful}"
    )
    assert str(Path(real_ctx.project_dir).resolve()) not in messages["not a notebook"], (
        "and the refusal for a non-notebook leaks the backend's absolute path"
    )


# ---------------------------------------------------------------------------
# DEFECT — the detached service is invisible to the agent
# ---------------------------------------------------------------------------


@pytest.fixture()
def detached_ctx(real_project: Path) -> Iterator[Any]:
    """A context that carries no session service, so the tools build a detached one."""

    class _NoServiceContext:
        project_dir = real_project
        active_workflow_id = "wf-1"
        workspace_focus: ClassVar[dict[str, Any]] = {"mode": MODE_EXPLORE, "session_path": NOTEBOOK}

    stub = _NoServiceContext()
    _context.set_context(stub)  # type: ignore[arg-type]
    _service.reset_fallback_services()
    try:
        yield stub
    finally:
        _context.set_context(None)
        _service.reset_fallback_services()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECT S5-D1-005 (P2): when the tools fall back to a detached session service, no tool "
        "result says so. ``resolve_session_service`` computes the origin and every production "
        "caller throws it away, so the agent is told it appended a cell to the person's notebook "
        "when nobody is reading the file it wrote. See docs/planning/adr-054-assembly-followups.md."
    ),
)
def test_a_tool_acting_through_a_detached_service_tells_the_agent_so(detached_ctx: Any) -> None:
    """Proves the one condition under which every session tool's answer is quietly untrue.

    ``_service.py``'s own docstring states the stakes: a detached service is
    "this process's own" and "an agent working through a detached service is
    working on its own copy of the notebook, and that is a fact about its
    answers". It says the fallback happens "never quietly", because
    :func:`resolve_session_service` "reports the origin to any caller that
    asks".

    Nothing asks. :func:`session_service` — the only production caller — is
    ``service, _origin = resolve_session_service()`` and discards it, and no
    result model in ``_models.py`` has a field for it. The single channel that
    survives is a WARNING in the backend's log, which the agent cannot read and
    the person will not look at.

    So the agent calls ``append_cell``, is told a cell id, reports to the person
    that the cell is in their notebook, and the person's window shows nothing —
    which is the same failure FR-024 exists to prevent, arrived at from the
    other side.

    Why the existing tests did not ask:
    ``tests/ai/test_mcp_session_service_forwarding.py`` asserts the origin at the
    ``resolve_session_service`` seam — where it is correct — and never asks
    whether the origin reaches a **tool result**. The scripted context in
    ``test_mcp_tools_explore.py`` always carries a service, so the detached
    branch never runs there at all.

    What the fix must deliver: a field on the session result models carrying the
    origin (or at least a flag), populated from the value
    :func:`resolve_session_service` already returns.
    """
    _, origin = _service.resolve_session_service()
    assert origin.is_detached, "precondition: this context has no session service to share"

    result = _run(read_notebook())

    rendered = result.model_dump_json()
    assert "detached" in rendered.lower(), (
        f"no field of the result tells the agent it is reading a notebook nobody else is looking at. "
        f"Fields: {sorted(type(result).model_fields)}"
    )


def test_the_detached_fallback_is_at_least_reachable_and_cached(detached_ctx: Any, caplog: Any) -> None:
    """Proves the detached path works and announces itself exactly once per project.

    The fallback itself is correct and worth pinning: two tool calls share one
    service rather than opening a second notebook store over the same file, and
    the WARNING that names the consequence is emitted once rather than per call.
    The defect above is about where that warning *goes*, not about whether the
    fallback works.

    Why the existing tests did not ask: the forwarding module asserts the origin
    record; it does not assert the caching or the once-only announcement, which
    is what keeps a busy agent from filling the log.

    Pushed here, and the implementation is correct.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="scistudio.ai.agent.mcp.tools_explore._service"):
        first, first_origin = _service.resolve_session_service()
        second, second_origin = _service.resolve_session_service()

    assert first is second, "a detached service is built once per project and reused"
    assert first_origin.is_detached and second_origin.is_detached
    announcements = [record for record in caplog.records if "session tools:" in record.getMessage()]
    assert len(announcements) == 1, f"the detached build must announce once, not per call: {announcements}"
    assert "reloads the file" in announcements[0].getMessage(), "and the announcement must name the consequence"


# ---------------------------------------------------------------------------
# FR-019 — open_explore_session must not move the person
# ---------------------------------------------------------------------------


@pytest.fixture()
def scripted(tmp_path: Path) -> Iterator[tuple[_StubContext, _Service]]:
    """The sibling module's scripted session API, without its packaging fixture.

    Reused rather than restated so that a change to the fake shape breaks both
    files at once. The packaging seam is scripted per test below, where it
    matters, instead of module-wide.
    """
    root = tmp_path / "project"
    (root / "explore").mkdir(parents=True)
    (root / "explore" / "qc.ipynb").write_text(EMPTY_NOTEBOOK, encoding="utf-8")
    service = _Service(root)
    stub = _StubContext(
        project_dir=root,
        _service_obj=service,
        workspace_focus={"mode": MODE_EXPLORE, "session_path": NOTEBOOK, "current_cell_id": "cell-b"},
    )
    _context.set_context(stub)  # type: ignore[arg-type]
    _service.reset_fallback_services()
    try:
        yield stub, service
    finally:
        _context.set_context(None)
        _service.reset_fallback_services()


def test_open_explore_session_does_not_change_the_focus_when_the_open_fails(
    scripted: tuple[_StubContext, _Service],
) -> None:
    """Proves FR-019 holds on the failure path, which is where a write-back would hide.

    A tool that set the focus would most plausibly do it *after* a successful
    open, so the passing-case test in the sibling module is the easy half. The
    half that matters for an invariant is that nothing is written on the way out
    of a failure either — including the focus of a person who was in a *different*
    session when the agent's open blew up.

    Why the existing tests did not ask: the sibling module asserts the focus is
    unchanged after a *successful* open (explore focus and canvas focus), and
    separately asserts the argument-validation refusals. It never combines them:
    no test observes the focus after an open that reached the service and
    raised.

    Pushed here, and the implementation is correct.
    """
    ctx, service = scripted
    before = dict(ctx.workspace_focus or {})
    service.open_error = RuntimeError("the block has never run")

    with pytest.raises(RuntimeError):
        _run(open_explore_session(source="block_outputs", block_id="peaks"))

    assert ctx.workspace_focus == before, "a failed open must not touch the person's focus"
    assert ("open_over_block_outputs", ("peaks", None, None)) in service.calls, "precondition: it reached the service"


def test_open_explore_session_called_twice_does_not_change_the_focus(
    scripted: tuple[_StubContext, _Service],
) -> None:
    """Proves the invariant survives repetition, and that the second call reports the same focus.

    FR-019 is an invariant, not a property of the first call, and the tool's own
    docstring warns that calling it twice over the same source makes a second
    notebook — so the repeated call is a realistic agent mistake and the focus
    must be as untouched after it as before.

    Why the existing tests did not ask: every FR-019 test in the sibling module
    calls the tool once.

    Pushed here, and the implementation is correct.
    """
    ctx, _svc = scripted
    before = dict(ctx.workspace_focus or {})

    first = _run(open_explore_session(source="file", path="data/spectra.csv"))
    second = _run(open_explore_session(source="file", path="data/spectra.csv"))

    assert ctx.workspace_focus == before
    assert first.focus_unchanged is True and second.focus_unchanged is True
    assert first.focused_session_path == second.focused_session_path == NOTEBOOK


# ---------------------------------------------------------------------------
# FR-021 / FR-023 — a refusal is a result, and a surprise is not a success
# ---------------------------------------------------------------------------


def test_run_cell_does_not_report_an_unanticipated_queue_failure_as_a_completed_run(
    scripted: tuple[_StubContext, _Service],
) -> None:
    """Proves an error ``run_cell`` did not anticipate is not flattened into a clean result.

    ``run_cell`` translates three refusal classes into ``refused=True`` results.
    The requirement it is serving (FR-021) is about the *queue's* refusal, so the
    interesting question is what happens to a failure outside that set — a bug,
    a driver error, anything the tool's author did not enumerate. The dangerous
    answer would be a broad ``except Exception`` that produced
    ``completed=True`` with empty outputs, which reads to the agent as "the cell
    ran and produced nothing". It does not do that: the exception propagates and
    the agent sees a tool error.

    Why the existing tests did not ask: the sibling module parametrises exactly
    the three anticipated classes (``KeyError``, ``SessionError``,
    ``RuntimeError``) and asserts each becomes a refusal result. Nothing asserts
    the boundary of that set.

    Pushed here, and the implementation is correct.
    """
    _ctx, service = scripted
    session = service._session(NOTEBOOK)

    def _explode(cell_id: str) -> Any:
        raise MemoryError("the kernel host is out of memory")

    session.run_cell = _explode  # type: ignore[assignment,method-assign]

    with pytest.raises(MemoryError):
        _run(run_cell(cell_id="cell-a"))


def test_package_notebook_does_not_report_a_block_it_did_not_write(
    scripted: tuple[_StubContext, _Service], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves an unanticipated packaging failure is not reported as ``packaged=true``.

    FR-023 makes a *refusal* a result, and the two refusal classes are
    translated. An ``OSError`` from the write — a full disk, a read-only blocks
    directory — is neither, and reporting ``packaged=true`` for it would tell the
    agent a block exists in the palette that does not. The tool lets it
    propagate, and nothing partially-successful is reported.

    Why the existing tests did not ask: the sibling module covers
    ``PackagingRefusedError``, ``ValueError``, the no-commit case and the
    not-drained case — every path that *returns*. No test drives a path that
    must not return.

    Pushed here, and the implementation is correct.
    """
    from scistudio.explore import packaging as packaging_module

    def _fail(document: Any, **kwargs: Any) -> Any:
        raise OSError("blocks/ is read-only")

    monkeypatch.setattr(packaging_module, "package_notebook", _fail)
    _ctx, service = scripted
    service._session(NOTEBOOK).notebook_commit = "abc123"

    with pytest.raises(OSError, match="read-only"):
        _run(package_notebook(block_name="qc"))

    assert service.events == [], "nothing may be published for a block that was not written"


# ---------------------------------------------------------------------------
# FR-024 — the thinness rule, derived from the session class rather than restated
# ---------------------------------------------------------------------------


def _package_modules() -> list[Path]:
    modules = sorted(PACKAGE_ROOT.rglob("*.py"))
    assert modules, "the session tool package has no modules to check"
    return modules


def _attribute_names_used() -> dict[str, set[str]]:
    """Every attribute name reached anywhere in the package, per module."""
    used: dict[str, set[str]] = {}
    for path in _package_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used[path.name] = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    return used


def _public_session_members() -> set[str]:
    return {name for name in dir(ExploreSession) if not name.startswith("_")}


#: The one public :class:`ExploreSession` member whose name contains a forbidden
#: word and which a thin tool may still read: it is a boolean *about* the kernel,
#: not a handle *to* it, and ``read_notebook`` reports it so the agent knows
#: whether the next ``run_cell`` will start one.
KERNEL_WORD_CARVE_OUT = frozenset({"has_kernel"})

#: Members that are the notebook file rather than the session's view of it.
#: Derived-by-name cannot find these, so they are named — but unlike the sibling
#: module's blacklist they are additive to a derived set rather than the whole of
#: it, so a new kernel/queue/bridge member is covered without this list moving.
FILE_REACHING_MEMBERS = frozenset({"write", "stripped_notebook", "note_branch_commit", "note_explore_commit"})


def _fr024_forbidden_members() -> frozenset[str]:
    """The FR-024 names, computed from the session class as it is today.

    FR-024 names three things a session tool may not reach: the kernel, the
    notebook file, and the queue. Two of the three are findable by name on
    :class:`ExploreSession` — every member that reaches the kernel, the queue or
    the kernel bridge says so in its name — and the third is the small explicit
    set above. Deriving rather than listing is the point: the sibling module's
    hand-written blacklist stops covering the class the moment the class grows,
    and the growth is exactly when a shortcut would be introduced.
    """
    by_name = {
        name
        for name in _public_session_members()
        if ("kernel" in name or "queue" in name or "bridge" in name) and name not in KERNEL_WORD_CARVE_OUT
    }
    return frozenset(by_name | FILE_REACHING_MEMBERS)


def test_the_forbidden_member_set_is_not_empty_and_still_names_the_obvious_three() -> None:
    """Guards the derivation itself: a rule that computed to nothing would pass everything."""
    forbidden = _fr024_forbidden_members()

    assert {"kernel", "queue", "bridge"} <= forbidden, forbidden
    assert {"start_kernel", "stop_kernel", "restart_kernel", "report_kernel_died"} <= forbidden
    assert "has_kernel" not in forbidden, "the carve-out is deliberate and must stay explicit"
    assert len(forbidden) >= 10, f"the derived rule collapsed to {sorted(forbidden)}"


def test_no_session_tool_reaches_a_member_the_session_class_marks_as_forbidden() -> None:
    """Proves FR-024 against the session class as it stands, not against a list written once.

    Why the existing tests did not ask: ``test_no_session_tool_reaches_the_kernel
    _or_the_queue_through_a_session_object`` holds a frozen
    ``FORBIDDEN_ATTRIBUTES`` set of sixteen names. It is correct today and it
    cannot notice tomorrow: an ``ExploreSession`` that grows ``kernel_handle``
    or ``queue_depth`` is not in that set, and a tool reaching it passes. This
    test recomputes the forbidden set from the class on every run.

    Pushed here, and the implementation is correct.
    """
    forbidden = _fr024_forbidden_members()
    offenders = {module: sorted(names & forbidden) for module, names in _attribute_names_used().items()}
    offenders = {module: names for module, names in offenders.items() if names}

    assert offenders == {}, (
        f"FR-024: these session tool modules reach a member that is the kernel, the queue or the "
        f"notebook file: {offenders}. Every execution passes through the session service."
    )


#: The public :class:`ExploreSession` members the session tools are reviewed to
#: use. An allowlist rather than a blacklist: a new reach fails this test and has
#: to be justified in review, which is the direction FR-024's guarantee needs.
#:
#: The check is name-based, so a name that also exists on another object (for
#: example ``notebook_path`` on a ``PackagedBlock``) is counted here. That is
#: conservative in the safe direction and is why the list is longer than the set
#: of members actually taken off a session.
REVIEWED_SESSION_MEMBERS = frozenset(
    {
        "binding_types",
        "bindings",
        "bound_run",
        "cell_marks",
        "cells",
        "current_cell",
        "document",
        "facts",
        "graph",
        "has_kernel",
        "insert_cell",
        "last_bound_by",
        "marks",
        "marks_by_cell",
        "needs_restart",
        "notebook_commit",
        "notebook_path",
        "observations",
        "relative_path",
        "reload_if_changed",
        "run_cell",
        "session_id",
        "wait_until_idle",
    }
)


def test_the_session_members_the_tools_reach_are_the_reviewed_set() -> None:
    """Proves FR-024 as an allowlist: a new reach into the session must be argued for.

    A blacklist answers "did anyone touch the three things we already thought
    of". FR-024 is the stronger claim that a session tool is *thin* — a call to
    the session API and nothing else — and the only assertion that carries it is
    one that fails when the surface grows in either direction.

    Why the existing tests did not ask: the sibling module has no allowlist for
    attributes at all; its allowlist covers imports only, and its attribute rule
    is the blacklist above. A tool that started reaching ``session.window`` or
    ``session.emit_snippet`` — session API members, but not thin ones for an
    agent tool — would pass every assertion in that file.

    Pushed here, and the implementation is correct.
    """
    reached = set().union(*_attribute_names_used().values()) & _public_session_members()

    unreviewed = sorted(reached - REVIEWED_SESSION_MEMBERS)
    stale = sorted(REVIEWED_SESSION_MEMBERS - reached)
    assert not unreviewed, (
        f"the session tools reach {unreviewed}, which nobody has reviewed against FR-024. "
        f"Add each to REVIEWED_SESSION_MEMBERS with a reason, or route it through the session API."
    )
    assert not stale, (
        f"REVIEWED_SESSION_MEMBERS lists {stale}, which nothing reaches any more. "
        f"A stale allowlist is an allowlist nobody trusts; delete the entries."
    )


def test_no_session_tool_reaches_a_forbidden_member_through_getattr() -> None:
    """Proves the AST attribute rule cannot be walked around with a string.

    ``getattr(session, "queue")`` is not an ``ast.Attribute`` on ``queue`` and is
    therefore invisible to every attribute-based assertion in the sibling module.
    It is also exactly how a shortcut would be written by someone who knew the
    check existed. This walks the call graph for ``getattr`` and
    ``object.__getattribute__`` with a literal name argument and holds the name
    to the same derived forbidden set.

    Why the existing tests did not ask: the sibling module walks ``ast.Attribute``
    nodes only.

    Pushed here, and the implementation is correct.
    """
    forbidden = _fr024_forbidden_members()
    offenders: dict[str, list[str]] = {}
    for path in _package_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
            if name not in {"getattr", "__getattribute__"} or len(node.args) < 2:
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value in forbidden:
                offenders.setdefault(path.name, []).append(arg.value)

    assert offenders == {}, (
        f"FR-024: these modules reach a forbidden session member through getattr, which no "
        f"attribute-based assertion would see: {offenders}"
    )


def test_no_session_tool_module_constructs_a_notebook_store_or_a_queue() -> None:
    """Proves thinness at the construction site as well as at the call site.

    Importing nothing forbidden and reaching nothing forbidden still leaves one
    way through: build the object yourself. ``NotebookStore(path)`` in a tool
    module would be a second reader over the person's file with no import of
    ``scistudio.explore.notebook`` at module scope if it were fetched lazily
    from the session package's own re-exports.

    Why the existing tests did not ask: the sibling module asserts that only
    ``_service.py`` mentions ``SessionService``, which covers the service and
    nothing else.

    Pushed here, and the implementation is correct.
    """
    forbidden_constructors = {"NotebookStore", "ExecutionQueue", "KernelBridge", "KernelHandle", "NotebookDocument"}
    offenders: dict[str, list[str]] = {}
    for path in _package_modules():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in forbidden_constructors
            ):
                offenders.setdefault(path.name, []).append(node.func.id)

    assert offenders == {}, f"FR-024: these modules construct the session's own internals: {offenders}"


def test_the_scripted_session_stub_still_matches_the_real_session_api() -> None:
    """Proves the fake the whole sibling suite rests on has not drifted from the real class.

    Every behavioural assertion about the session tools is made against
    ``_Session``. If that fake grows a member the real ``ExploreSession`` does
    not have, or keeps one the real class has renamed, the suite goes on passing
    while the tools break in the app. That is the highest-leverage silent
    failure in this surface, and nothing checks it.

    Why the existing tests did not ask: the sibling module documents each fake as
    "shaped like" its real counterpart and never asserts the shape.

    Pushed here, and the implementation is correct.
    """
    fake = {name for name in dir(_Session) if not name.startswith("_")} - {"calls", "reloaded", "path"}
    real = _public_session_members()

    invented = sorted(fake - real)
    assert not invented, (
        f"the scripted session exposes {invented}, which ExploreSession does not. Every tool test "
        f"that uses them proves nothing about the real session API."
    )
