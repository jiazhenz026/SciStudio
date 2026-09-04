"""A branch change retires every explore kernel — FR-014, wired at the route (#2240).

ADR-054 spec 3 FR-014: "Switching the project's branch MUST retire every kernel
after writing every open notebook to disk, and each session MUST report that it
needs a restart." ``SessionService.retire_kernels`` implemented all of that and
nothing called it; ``POST /api/git/branch/switch`` is the wiring point.

Three things these tests are deliberately picky about.

**The ordering is the correctness, not a detail.** Retirement *writes* each open
notebook to disk. Called after the checkout, that write puts the departing
branch's notebook on top of the file the arriving branch just checked out — a
silent overwrite dressed up as a save. So
:func:`test_the_kernels_are_retired_before_the_checkout` does not assert "it was
called"; it records which branch was checked out *at the moment of the call*.

**A kernel is a process, so the real-kernel case asserts on the process.** A
session flag reading "retired" is exactly what a leaked kernel looks like from
the inside. :func:`test_a_branch_switch_kills_the_real_kernel_process` records
the pid through the route, switches the branch, and asks the operating system.

**The failure mode is a decision, so it is tested.** A kernel that will not die
must not become a branch the person cannot leave: the switch proceeds and the
response reports the failure under ``explore_kernels``. The alternative — a
request that fails after the auto-commit has already landed — leaves the tree
half-moved with no recovery in the UI.
"""

from __future__ import annotations

import importlib.util
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil
import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import explore

needs_kernel = pytest.mark.skipif(
    importlib.util.find_spec("jupyter_client") is None or importlib.util.find_spec("ipykernel") is None,
    reason="jupyter_client/ipykernel are not importable in this interpreter",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain(client: TestClient) -> None:
    """Commit any residual untracked state so the tree is clean before a switch."""
    if client.get("/api/git/status").json()["dirty"]:
        client.post("/api/git/commit", json={"message": "drain"})


def _current_branch(project: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _process_gone(pid: int, timeout: float = 15.0) -> bool:
    """Whether ``pid`` is no longer a running process."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        try:
            if not psutil.Process(pid).is_running():
                return True
        except psutil.Error:
            return True
        time.sleep(0.05)
    return False


class _RecordingService:
    """A stand-in for the project's session service that records when it was called.

    Registered directly in ``explore._services`` so the git route finds it
    exactly as it finds a real one. The subject here is the git route's call,
    not the service behind it — the service's own retirement behaviour, down to
    the kernel processes, is covered in ``tests/explore/test_explore_session.py``.
    """

    def __init__(self, project: Path, *, retired: tuple[str, ...] = ("session-1",)) -> None:
        self._project = project
        self._retired = retired
        self.branch_at_call: str | None = None
        self.calls = 0

    def retire_kernels(self) -> tuple[str, ...]:
        self.calls += 1
        self.branch_at_call = _current_branch(self._project)
        return self._retired

    def shutdown(self, *, commit: bool = False) -> None:
        """Application teardown calls this; nothing here needs it to do anything."""


class _AngryService(_RecordingService):
    """A service whose kernel will not die."""

    def retire_kernels(self) -> tuple[str, ...]:
        self.calls += 1
        self.branch_at_call = _current_branch(self._project)
        raise RuntimeError("kernel 4242 ignored SIGTERM")


def _register(monkeypatch: pytest.MonkeyPatch, project: Path, service: Any) -> None:
    monkeypatch.setitem(explore._services, str(project.resolve()), service)


# ---------------------------------------------------------------------------
# The wiring, and its ordering
# ---------------------------------------------------------------------------


def test_the_kernels_are_retired_before_the_checkout(
    client: TestClient,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-014, and the half of it that a "was it called" assertion would miss.

    Retirement writes every open notebook to disk. If it ran after the checkout
    those writes would land the departing branch's notebooks on top of the
    arriving branch's files. So this asserts on the branch that was checked out
    when the call happened, not merely that the call happened.
    """
    _drain(client)
    service = _RecordingService(opened_project, retired=("session-a", "session-b"))
    _register(monkeypatch, opened_project, service)
    starting_branch = _current_branch(opened_project)
    client.post("/api/git/branch/create", json={"name": "feature"})

    response = client.post("/api/git/branch/switch", json={"branch_name": "feature"})

    assert response.status_code == 200, response.text
    assert service.calls == 1
    assert service.branch_at_call == starting_branch, (
        "the kernels were retired after the checkout; the notebooks they write on "
        f"the way out would land on '{service.branch_at_call}' instead of "
        f"'{starting_branch}'"
    )
    assert response.json()["explore_kernels"] == {"retired": ["session-a", "session-b"], "error": None}
    assert _current_branch(opened_project) == "feature"


def test_a_refused_branch_switch_costs_nobody_their_kernels(
    client: TestClient,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A switch to a branch that does not exist retires nothing.

    Same reasoning as the #1378 fix that moved the target-branch check above the
    auto-commit: a request that is going to be refused must not have mutated
    anything first, and a retired kernel is a mutation the person notices.
    """
    _drain(client)
    service = _RecordingService(opened_project)
    _register(monkeypatch, opened_project, service)

    response = client.post("/api/git/branch/switch", json={"branch_name": "no-such-branch"})

    assert response.status_code == 404, response.text
    assert service.calls == 0


def test_a_branch_switch_survives_a_kernel_that_will_not_die(
    client: TestClient,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chosen failure mode: report the kernel, complete the switch.

    Refusing the switch would strand the person on a branch they cannot leave
    because a subprocess is wedged, with no recovery except killing the backend
    — which loses that kernel anyway. So the switch completes and the failure is
    named in the response rather than swallowed.
    """
    _drain(client)
    service = _AngryService(opened_project)
    _register(monkeypatch, opened_project, service)
    client.post("/api/git/branch/create", json={"name": "feature"})

    response = client.post("/api/git/branch/switch", json={"branch_name": "feature"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_branch"] == "feature"
    assert _current_branch(opened_project) == "feature", "the switch did not complete"
    assert body["explore_kernels"]["retired"] == []
    assert "kernel 4242 ignored SIGTERM" in body["explore_kernels"]["error"]


def test_a_project_nobody_explored_retires_nothing(
    client: TestClient,
    opened_project: Path,
) -> None:
    """The ordinary case: no session service, so the switch reports an empty retirement.

    It must also not *build* one. A branch switch is not a reason to start a
    session service and its commit thread for a project with no notebooks open;
    ``tests/api/test_explore_mount.py`` pins that the lookup never constructs.
    """
    _drain(client)
    client.post("/api/git/branch/create", json={"name": "feature"})

    response = client.post("/api/git/branch/switch", json={"branch_name": "feature"})

    assert response.status_code == 200, response.text
    assert response.json()["explore_kernels"] == {"retired": [], "error": None}


# ---------------------------------------------------------------------------
# The real kernel
# ---------------------------------------------------------------------------


@needs_kernel
@pytest.mark.serial
def test_a_branch_switch_kills_the_real_kernel_process(
    client: TestClient,
    opened_project: Path,
) -> None:
    """FR-014 end to end: a real ipykernel process does not survive the switch.

    The session is opened through its route and the branch is changed through
    its route. The one thing done off-route is starting the kernel: no FR-056
    operation is "start a kernel" (a kernel starts when a cell runs), and
    running a cell would make this test about execution rather than about
    retirement.
    """
    _drain(client)
    opened = client.post("/api/explore/sessions", json={"source": "file", "path": "data/raw/signal.csv"})
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["session_id"]

    services = list(explore._services.values())
    assert len(services) == 1, f"expected one session service, found {len(services)}"
    service = services[0]
    session = service.session_for(session_id)
    session.start_kernel()
    pid = session.kernel_status().pid
    assert pid is not None and psutil.pid_exists(pid)

    client.post("/api/git/branch/create", json={"name": "feature"})
    response = client.post("/api/git/branch/switch", json={"branch_name": "feature"})

    assert response.status_code == 200, response.text
    assert response.json()["explore_kernels"] == {"retired": [session_id], "error": None}
    assert _process_gone(pid), f"the kernel process {pid} survived the branch change"
    assert session.needs_restart is True
    assert service.kernels() == ()
