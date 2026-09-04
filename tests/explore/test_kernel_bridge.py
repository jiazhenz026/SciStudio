"""The kernel bridge: fingerprints, bindings, memory, windows, installs (T-003, T-010, T-011).

Two halves, matching the module under test.

The **pure** tests call the kernel-side functions directly, because in the
kernel they are called with a plain dict for a namespace and that is exactly
what a test can hand them. They run everywhere, including a checkout with no
Jupyter installed.

The **kernel** tests spawn a real ipykernel, because the claim FR-009 makes —
that a bridge call leaves no cell — is a claim about what ipykernel does with
``silent=True`` and ``store_history=False``, and a double would prove nothing
about it. They carry the ``serial`` marker (#1867, #1896), register every
handle with the ``kernels`` fixture, and kill anything that outlives it.

The two tests that matter most:

* :func:`test_a_bridge_call_leaves_no_cell` reads the kernel's own input
  history and execution counter back out of the kernel after a run of bridge
  calls, rather than trusting a comment that says output is suppressed.
* :func:`test_a_window_equals_the_preview_provider` renders the same object
  through the preview provider directly and compares, rather than against a
  golden file that would still match if both sides drifted together.
"""

from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from scistudio.core.lineage.environment import (
    ENVIRONMENT_REFERENCE_PREFIX,
    EnvironmentSnapshot,
    EnvironmentSnapshotStore,
)
from scistudio.explore import kernel_bridge
from scistudio.explore.kernel_bridge import (
    BRIDGE_PROTOCOL_VERSION,
    Binding,
    bindings,
    cell_installs_packages,
    fingerprints,
    session_kernel_env,
    variable_window,
)

pandas = pytest.importorskip("pandas")
pyarrow = pytest.importorskip("pyarrow")

#: ipykernel and jupyter_client are core dependencies (FR-059, task T-001), but
#: a checkout that predates T-001 has neither, and the pure tests below do not
#: need them. Only the process-spawning tests are skipped.
_HAS_KERNEL = all(importlib.util.find_spec(name) is not None for name in ("jupyter_client", "ipykernel"))
requires_kernel = pytest.mark.skipif(
    not _HAS_KERNEL,
    reason="jupyter_client/ipykernel are not importable; ADR-054 T-001 adds them to pyproject.toml",
)

#: Generous enough that a loaded machine does not flake, short enough that the
#: per-test 60s wall-clock kill is never the thing that fails.
_EXEC_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kernels() -> Iterator[Callable[..., Any]]:
    """Hand out kernel handles and guarantee every process they started is gone.

    The same contract as ``tests/explore/test_kernel_session.py``: cleanup runs
    on the failure path too, each pid is recorded before the polite shutdown,
    and anything that survives is killed.
    """
    from scistudio.explore.kernel import KernelHandle

    made: list[Any] = []

    def make(**kwargs: object) -> Any:
        handle = KernelHandle(**kwargs)  # type: ignore[arg-type]
        made.append(handle)
        return handle

    try:
        yield make
    finally:
        for handle in made:
            pid = handle.pid
            with contextlib.suppress(Exception):  # cleanup must not mask a failure
                handle.stop()
            if pid is not None:
                _kill_if_alive(pid)


def _kill_if_alive(pid: int) -> None:
    """Kill *pid* if it somehow outlived the handle that owned it."""
    import psutil

    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return
    with contextlib.suppress(psutil.Error):
        process.kill()
        process.wait(timeout=10)


@pytest.fixture
def bridge_over_kernel(kernels: Callable[..., Any]) -> Callable[..., Any]:
    """Start a kernel and return a bridge installed on it."""
    from scistudio.explore.kernel_bridge import KernelBridge

    def make(**kwargs: object) -> Any:
        handle = kernels(**kwargs)
        handle.start()
        bridge = KernelBridge(handle, timeout=_EXEC_TIMEOUT)
        bridge.install(mode="session")
        return bridge

    return make


@pytest.fixture
def frame() -> Any:
    """A small table used for windows and helper round trips."""
    return pandas.DataFrame({"value": [1, 2, 3], "label": ["a", "b", "c"]})


# ---------------------------------------------------------------------------
# Detecting an install (T-011, FR-012)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "%pip install scikit-image",
        "!pip install scikit-image",
        "%conda install -c conda-forge scikit-image",
        "import numpy\n    %pip install scikit-image",
        "%pip",
    ],
)
def test_an_install_line_is_detected(source: str) -> None:
    """FR-012's three spellings are each detected, indented or not."""
    assert cell_installs_packages(source)


@pytest.mark.parametrize(
    "source",
    [
        "",
        "df = pipeline(df)",
        "# %pip install scikit-image",
        "note = 'run %pip install scikit-image first'",
        "%pipeline_magic run",
        "print('!pip is a string here')",
    ],
)
def test_an_ordinary_cell_is_not_an_install(source: str) -> None:
    """A mention of pip in a comment or a string does not trigger a re-snapshot."""
    assert not cell_installs_packages(source)


# ---------------------------------------------------------------------------
# The environment snapshot, stored by reference (T-011, FR-034)
# ---------------------------------------------------------------------------


def test_a_reference_is_stable_and_follows_the_environment() -> None:
    """Equal environments reference the same snapshot; a change makes a new one."""
    one = EnvironmentSnapshot(python_version="3.11.9", platform="win", full_freeze="numpy==2.0.0")
    same = EnvironmentSnapshot(python_version="3.11.9", platform="win", full_freeze="numpy==2.0.0")
    changed = EnvironmentSnapshot(python_version="3.11.9", platform="win", full_freeze="numpy==2.1.0")

    assert one.reference() == same.reference()
    assert one.reference() != changed.reference()
    assert one.reference().startswith(ENVIRONMENT_REFERENCE_PREFIX)


def test_a_snapshot_is_stored_once_per_environment(tmp_path: Path) -> None:
    """FR-034: one file per distinct environment however often it is captured."""
    store = EnvironmentSnapshotStore(tmp_path / "environments")
    one = EnvironmentSnapshot(python_version="3.11.9", platform="win", full_freeze="numpy==2.0.0")
    changed = EnvironmentSnapshot(python_version="3.11.9", platform="win", full_freeze="numpy==2.1.0")

    assert store.put(one) == store.put(one) == one.reference()
    assert len(store.references()) == 1
    store.put(changed)
    assert len(store.references()) == 2
    store.put(one)
    assert len(store.references()) == 2
    assert len(list((tmp_path / "environments").glob("*.json"))) == 2


def test_a_stored_snapshot_reads_back(tmp_path: Path) -> None:
    """A record that kept only the reference can recover the whole snapshot."""
    store = EnvironmentSnapshotStore(tmp_path / "environments")
    snapshot = EnvironmentSnapshot.capture(full=False)
    reference = store.put(snapshot)
    assert store.has(reference)
    assert store.get(reference).to_dict() == snapshot.to_dict()


def test_the_store_refuses_a_string_that_is_not_a_reference(tmp_path: Path) -> None:
    """A foreign string never becomes a filename, so the store cannot be walked out of."""
    store = EnvironmentSnapshotStore(tmp_path / "environments")
    for hostile in ("../../etc/passwd", "env:sha256:../escape", "sha256:" + "a" * 64):
        with pytest.raises(ValueError, match="reference"):
            store.has(hostile)


def test_the_store_says_which_reference_is_missing(tmp_path: Path) -> None:
    """An unknown reference is a KeyError naming it, not an empty snapshot."""
    store = EnvironmentSnapshotStore(tmp_path / "environments")
    missing = ENVIRONMENT_REFERENCE_PREFIX + "0" * 64
    with pytest.raises(KeyError, match="0000"):
        store.get(missing)


def _recorded_freeze(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Record what a capture's freeze would run, without running anything."""
    from scistudio.core.lineage import environment as environment_module

    calls: list[tuple[str, Any]] = []

    def fake_which(name: str) -> str:
        calls.append(("which", name))
        return "/somewhere/uv"

    def fake_run(argv: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(("run", list(argv)))
        return subprocess.CompletedProcess(list(argv), 0, "probe==1.0\n", "")

    monkeypatch.setattr(environment_module.shutil, "which", fake_which)
    monkeypatch.setattr(environment_module.subprocess, "run", fake_run)
    return calls


def test_a_capture_can_be_pinned_to_another_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    """``executable`` decides whose packages the freeze describes (FR-012).

    The kernel is a different interpreter from the service, and ``uv pip
    freeze`` resolves an environment from the working directory rather than
    from the caller — so a pinned capture must go straight to that
    interpreter's own ``pip`` and never consult ``uv``.
    """
    calls = _recorded_freeze(monkeypatch)
    pinned = EnvironmentSnapshot.capture(executable="/other/python")

    assert pinned.full_freeze == "probe==1.0\n"
    assert ("which", "uv") not in calls, "a pinned capture consulted uv, which resolves the wrong environment"
    assert calls == [("run", ["/other/python", "-m", "pip", "freeze"])]


def test_an_unpinned_capture_still_prefers_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing callers are unchanged: with no interpreter named, uv still wins."""
    calls = _recorded_freeze(monkeypatch)
    EnvironmentSnapshot.capture()

    assert ("which", "uv") in calls
    assert calls[-1] == ("run", ["/somewhere/uv", "pip", "freeze"])


# ---------------------------------------------------------------------------
# Fingerprints and bindings over a plain namespace
# ---------------------------------------------------------------------------


def test_fingerprints_cover_the_notebook_names_only() -> None:
    """The shell's own names are not the notebook's, so they are not fingerprinted."""
    namespace = {
        "df": [1, 2, 3],
        "__builtins__": {},
        "__name__": "__main__",
        "In": ["", "df = [1, 2, 3]"],
        "Out": {},
        "get_ipython": lambda: None,
        "_i3": "df",
        "_7": 42,
        "_": 42,
    }
    assert set(fingerprints(namespace)) == {"df"}


def test_a_fingerprint_moves_when_the_value_is_mutated_in_place() -> None:
    """The observation FR-021 rests on: an in-place change is visible."""
    values = [1, 2, 3]
    namespace = {"values": values}
    before = fingerprints(namespace)["values"]
    values.append(4)
    after = fingerprints(namespace)["values"]
    assert before != after
    assert before.observable and after.observable


def test_a_name_that_cannot_be_read_is_reported_as_unobservable() -> None:
    """One hostile value does not fail the whole namespace fingerprint."""

    class Hostile:
        def __len__(self) -> int:
            raise RuntimeError("no")

        def __iter__(self) -> Any:
            raise RuntimeError("no")

    namespace = {"ok": 1, "bad": Hostile()}
    result = fingerprints(namespace)
    assert set(result) == {"ok", "bad"}
    assert result["ok"].observable


def test_bindings_report_the_type_and_a_bounded_summary(frame: Any) -> None:
    """FR-009's bindings list: names with their type names, sorted, bounded."""
    namespace = {"df": frame, "count": 3, "names": ["a", "b"], "__name__": "__main__"}
    listed = bindings(namespace)
    assert [binding.name for binding in listed] == ["count", "df", "names"]
    by_name = {binding.name: binding for binding in listed}
    assert by_name["df"].type_name == "DataFrame"
    assert by_name["df"].type_module.startswith("pandas")
    assert by_name["names"].summary == "list of 2"
    assert by_name["count"].summary == "int 3"


def test_a_summary_never_calls_repr() -> None:
    """A binding summary must not run a person's ``__repr__``; it is drawn constantly."""

    class Exploding:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called for a bindings list")

    listed = bindings({"boom": Exploding()})
    assert listed[0].summary == "Exploding"


def test_a_summary_is_bounded() -> None:
    """A number is not automatically short, and one long name would dominate the payload."""
    listed = bindings({"huge": 2**100_000, "wide": "x" * 10_000})
    for binding in listed:
        assert len(binding.summary) <= kernel_bridge._SUMMARY_LIMIT, binding


# ---------------------------------------------------------------------------
# The wire protocol
# ---------------------------------------------------------------------------


def _decode_frame(printed: str) -> dict[str, Any]:
    """Pull the one framed answer out of *printed* and decode it."""
    match = re.search(
        re.escape(kernel_bridge._FRAME_START) + r"([A-Za-z0-9+/=]*)" + re.escape(kernel_bridge._FRAME_END),
        printed,
    )
    assert match is not None, f"no reply frame in {printed!r}"
    return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))


def _request(**payload: Any) -> str:
    """Encode a request the way :class:`KernelBridge` does."""
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def test_a_dispatch_frames_its_answer(capsys: pytest.CaptureFixture[str]) -> None:
    """The answer travels on stdout, framed and base64, because the value cannot."""
    kernel_bridge._dispatch({"df": [1, 2, 3]}, _request(action="bindings"))
    response = _decode_frame(capsys.readouterr().out)
    assert response["ok"] is True
    assert response["version"] == BRIDGE_PROTOCOL_VERSION
    assert [entry["name"] for entry in response["result"]] == ["df"]


def test_a_failing_dispatch_answers_rather_than_raising(capsys: pytest.CaptureFixture[str]) -> None:
    """A silent request's traceback is invisible, so a failure comes back as an answer."""
    kernel_bridge._dispatch({}, _request(action="no-such-action"))
    response = _decode_frame(capsys.readouterr().out)
    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert "no-such-action" in response["error"]["message"]


def test_a_dispatch_leaves_the_namespace_alone(capsys: pytest.CaptureFixture[str]) -> None:
    """A bridge call must not add a name, or the next fingerprint would see it."""
    namespace: dict[str, Any] = {"df": [1, 2, 3]}
    before = dict(namespace)
    kernel_bridge._dispatch(namespace, _request(action="fingerprints"))
    capsys.readouterr()
    assert namespace == before


def test_the_call_source_is_one_expression_that_binds_nothing() -> None:
    """The code a bridge call runs binds no name in the kernel namespace."""
    source = kernel_bridge._bridge_call_source({"action": "memory"})
    module = ast.parse(source)
    assert len(module.body) == 1
    assert isinstance(module.body[0], ast.Expr)
    assert not any(isinstance(node, (ast.Assign, ast.Import, ast.ImportFrom)) for node in ast.walk(module))


def test_session_kernel_env_names_the_mode_variable() -> None:
    """The launcher and the helpers agree on one variable, from one place (FR-010)."""
    from scistudio.explore.notebook_api import MODE_ENV_VAR, SESSION_MODE

    assert session_kernel_env() == {MODE_ENV_VAR: SESSION_MODE}


# ---------------------------------------------------------------------------
# Variable windows (T-010)
# ---------------------------------------------------------------------------


def _render_directly(frame: Any, tmp_path: Path) -> dict[str, Any]:
    """Render *frame* through the preview provider, independently of the bridge.

    Builds the SciStudio type, persists it, and calls the preview session
    manager the workflow preview calls. Nothing in this helper is code the
    bridge runs, which is what makes the comparison meaningful.
    """
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.previewers import get_preview_service
    from scistudio.previewers.models import PreviewTarget, TargetKind

    tmp_path.mkdir(parents=True, exist_ok=True)
    table = pyarrow.Table.from_pandas(frame, preserve_index=False)
    stored = DataFrame(columns=list(table.column_names), row_count=table.num_rows, data=table)
    reference = stored.save(str(tmp_path / "table.parquet"))
    target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref=reference.path,
        recorded_type="DataFrame",
        type_chain=("DataObject", "DataFrame"),
    )
    envelope = get_preview_service().sessions.render_target(
        target,
        {
            "_storage": {
                "backend": reference.backend,
                "path": reference.path,
                "format": reference.format,
                "metadata": reference.metadata,
            }
        },
    )
    return dict(envelope.to_dict())


def test_a_window_equals_the_preview_provider(tmp_path: Path, frame: Any) -> None:
    """FR-009: a window is the existing provider's output for the same object.

    Compared against the provider directly rather than a golden file: a golden
    file would still match if the window and the workflow preview drifted
    together, which is the failure this is here to catch.
    """
    window = variable_window({"df": frame}, "df")
    direct = _render_directly(frame, tmp_path / "direct")

    assert window.get("error") is None
    assert window["kind"] == direct["kind"]
    assert window["previewer_id"] == direct["previewer_id"]
    assert window["payload"] == direct["payload"]


def test_a_window_honours_the_preview_query(tmp_path: Path) -> None:
    """The query reaches the provider, so paging a window pages the same way."""
    frame = pandas.DataFrame({"value": list(range(10))})
    window = variable_window({"df": frame}, "df", query={"page": 2, "page_size": 4})
    assert window["payload"]["page"] == 2
    assert window["payload"]["page_size"] == 4
    assert [row["value"] for row in window["payload"]["rows"]] == [4, 5, 6, 7]


def test_a_window_does_not_touch_the_object_it_renders(frame: Any) -> None:
    """A window must not move the person's variable onto a temporary file.

    ``DataObject.save`` records the reference it wrote. Doing that here would
    leave the person's own object pointing at a path this call then deletes, so
    a window would quietly break the variable it was asked to show.
    """
    from scistudio.core.types.dataframe import DataFrame

    table = pyarrow.Table.from_pandas(frame, preserve_index=False)
    typed = DataFrame(columns=list(table.column_names), row_count=table.num_rows, data=table)
    assert typed.storage_ref is None

    window = variable_window({"typed": typed}, "typed")

    assert window.get("error") is None
    assert typed.storage_ref is None, "the window persisted onto the person's own object"


def test_a_window_renders_the_other_core_kinds() -> None:
    """Text and arrays route to their own providers, not to a table renderer."""
    numpy = pytest.importorskip("numpy")

    assert variable_window({"note": "hello"}, "note")["kind"] == "text"
    assert variable_window({"arr": numpy.arange(12).reshape(3, 4)}, "arr")["kind"] == "array"


def test_a_window_names_a_variable_that_is_not_bound() -> None:
    """Asking for a name the kernel does not have names it."""
    with pytest.raises(KeyError, match="missing"):
        variable_window({"df": 1}, "missing")


def test_a_window_refuses_a_shell_name() -> None:
    """The shell's own names are not offered as windows, so they cannot be asked for."""
    with pytest.raises(KeyError):
        variable_window({"In": ["", "x = 1"]}, "In")


# ---------------------------------------------------------------------------
# Against a real kernel
# ---------------------------------------------------------------------------


@requires_kernel
@pytest.mark.serial
def test_install_reports_the_kernel_it_reached(bridge_over_kernel: Callable[..., Any]) -> None:
    """Installing the bridge proves the kernel can import SciStudio at all.

    The pid the kernel reports for itself is the launched process *or one of
    its children*: on Windows a virtual environment's ``python.exe`` is often a
    redirector that runs the real interpreter as a child and waits for it, the
    same thing :meth:`KernelHandle.memory_bytes` sums a tree for.
    """
    import psutil

    bridge = bridge_over_kernel()
    reported = bridge.install(inputs={}, project_dir=None)
    assert Path(reported["python"]).exists()

    launched = bridge.handle.pid
    assert launched is not None
    tree = {launched} | {child.pid for child in psutil.Process(launched).children(recursive=True)}
    assert reported["pid"] in tree, f"the kernel reported pid {reported['pid']}, outside the launched tree {tree}"


@requires_kernel
@pytest.mark.serial
def test_a_bridge_call_leaves_no_cell(bridge_over_kernel: Callable[..., Any]) -> None:
    """FR-009: bridge requests must not appear as cells.

    Asserted against the kernel's own record of what it ran — its input history
    and its execution counter, read back out of the kernel — because those are
    what a notebook renders as cells. A comment saying output is suppressed
    would prove nothing.
    """
    bridge = bridge_over_kernel()
    handle = bridge.handle

    first = handle.execute("first = 1", timeout=_EXEC_TIMEOUT)
    bridge.fingerprints()
    bridge.bindings()
    bridge.memory_bytes()
    second = handle.execute("second = 2", timeout=_EXEC_TIMEOUT)

    assert first.execution_count is not None
    assert second.execution_count == first.execution_count + 1, "a bridge call advanced the execution counter"

    history = handle.execute(
        "import json as _json; print(_json.dumps([entry for entry in In if entry]))",
        timeout=_EXEC_TIMEOUT,
    )
    printed = "".join(output.text or "" for output in history.outputs if output.output_type == "stream")
    entries = json.loads(printed.strip().splitlines()[-1])
    assert not any("kernel_bridge" in entry for entry in entries), f"a bridge call entered the history: {entries}"
    # The three real cells: the two above and the one asking the question.
    assert len(entries) == 3, entries


@requires_kernel
@pytest.mark.serial
def test_fingerprints_follow_a_real_kernel_namespace(bridge_over_kernel: Callable[..., Any]) -> None:
    """The observation of FR-021 across a real run: a rebound name's digest moves."""
    bridge = bridge_over_kernel()
    handle = bridge.handle

    handle.execute("values = [1, 2, 3]\nother = 'unchanged'", timeout=_EXEC_TIMEOUT)
    before = bridge.fingerprints()
    assert "values" in before and "other" in before

    handle.execute("values.append(4)", timeout=_EXEC_TIMEOUT)
    after = bridge.fingerprints()

    assert after["values"] != before["values"], "an in-place mutation was not observed"
    assert after["other"] == before["other"], "an untouched name appeared to change"


@requires_kernel
@pytest.mark.serial
def test_bindings_and_memory_come_back_from_a_real_kernel(bridge_over_kernel: Callable[..., Any]) -> None:
    """FR-009's bindings list and memory reading, over the real execute channel."""
    bridge = bridge_over_kernel()
    bridge.handle.execute("count = 7\ntext = 'abc'", timeout=_EXEC_TIMEOUT)

    listed = {binding.name: binding for binding in bridge.bindings()}
    assert isinstance(listed["count"], Binding)
    assert listed["count"].type_name == "int"
    assert listed["text"].summary == "str of 3"

    memory = bridge.memory_bytes()
    assert memory is None or memory > 0


@requires_kernel
@pytest.mark.serial
def test_a_window_of_a_kernel_variable_matches_the_provider(
    bridge_over_kernel: Callable[..., Any], tmp_path: Path, frame: Any
) -> None:
    """T-010 end to end: the window a panel would read, rendered in the kernel."""
    bridge = bridge_over_kernel()
    bridge.handle.execute(
        "import pandas\ndf = pandas.DataFrame({'value': [1, 2, 3], 'label': ['a', 'b', 'c']})",
        timeout=_EXEC_TIMEOUT,
    )

    window = bridge.window("df")
    direct = _render_directly(frame, tmp_path / "direct")

    assert window.get("error") is None, window
    assert window["kind"] == direct["kind"]
    assert window["payload"]["rows"] == direct["payload"]["rows"]
    assert window["payload"]["columns"] == direct["payload"]["columns"]


@requires_kernel
@pytest.mark.serial
def test_the_helpers_answer_the_installed_binding(
    bridge_over_kernel: Callable[..., Any], tmp_path: Path, frame: Any
) -> None:
    """The session binding the bridge installs is what ``scistudio.input`` reads (FR-010)."""
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.explore.notebook_api import encode_artefact_reference

    table = pyarrow.Table.from_pandas(frame, preserve_index=False)
    stored = DataFrame(columns=list(table.column_names), row_count=table.num_rows, data=table)
    reference = stored.save(str(tmp_path / "table.parquet"))

    bridge = bridge_over_kernel(env=session_kernel_env())
    bridge.install(
        inputs={
            "table": encode_artefact_reference(
                type_name="DataFrame",
                backend=reference.backend,
                path=reference.path,
                format=reference.format,
            )
        },
        mode="session",
    )

    result = bridge.handle.execute(
        "import scistudio\n"
        'table = scistudio.load(scistudio.input("table"))\n'
        "print(table.to_memory().num_rows)\n"
        "scistudio.output(result=table)",
        timeout=_EXEC_TIMEOUT,
    )
    printed = "".join(output.text or "" for output in result.outputs if output.output_type == "stream")
    assert result.status == "ok", result.error
    assert printed.strip().endswith("3")
    assert bridge.declared_outputs() == ("result",)


@requires_kernel
@pytest.mark.serial
@pytest.mark.timeout(600)
def test_an_install_changes_the_snapshot_and_is_stored_once(kernels: Callable[..., Any], tmp_path: Path) -> None:
    """T-011 end to end: ``%pip`` in a kernel, re-snapshot, stored once (FR-012, FR-034).

    The kernel runs from a throwaway virtual environment built for this test,
    so the install is a real ``pip`` install into a real environment and
    nothing outside ``tmp_path`` changes. The package is a wheel this test
    builds — a zip with a ``dist-info`` and nothing else — installed with
    ``--no-index``, so the test needs no network and no build backend, which is
    the local index spec §5 SC-002 asks for.
    """
    from scistudio.explore.kernel_bridge import KernelBridge

    interpreter = _throwaway_environment(tmp_path / "kernelenv")
    wheel = _build_probe_wheel(tmp_path / "index")

    handle = kernels(python_executable=str(interpreter))
    handle.start()
    bridge = KernelBridge(handle, timeout=300.0)
    bridge.install(mode="session")

    store = EnvironmentSnapshotStore(tmp_path / "environments")
    before = bridge.environment_snapshot()
    assert store.put(before) == store.put(before)
    assert len(store.references()) == 1
    assert "scistudio_probe_pkg" not in (before.full_freeze or "")

    source = f'%pip install --no-index --no-deps "{wheel.as_posix()}"'
    assert cell_installs_packages(source), "the cell the session re-snapshots after was not detected"
    installed = handle.execute(source, timeout=300.0)
    assert installed.status == "ok", installed.error

    after = bridge.environment_snapshot()
    assert "scistudio_probe_pkg" in (after.full_freeze or ""), after.full_freeze
    assert after.reference() != before.reference(), "the snapshot did not change after an install"

    store.put(after)
    store.put(after)
    assert len(store.references()) == 2, "the changed environment was stored more than once"
    assert store.get(after.reference()).full_freeze == after.full_freeze


def _throwaway_environment(root: Path) -> Path:
    """Build a virtual environment this test may install into, and return its python.

    ``--system-site-packages`` so the kernel finds ipykernel and jupyter_client
    without a download; the install below lands in this environment's own
    ``site-packages`` and is gone with ``tmp_path``.
    """
    subprocess.run(  # sys.executable is this test's own interpreter
        [sys.executable, "-m", "venv", "--system-site-packages", str(root)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    interpreter = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.exists():  # pragma: no cover - a venv layout we do not know
        pytest.skip(f"no interpreter at {interpreter} after creating a virtual environment")
    return interpreter


def _build_probe_wheel(directory: Path, name: str = "scistudio_probe_pkg", version: str = "0.0.1") -> Path:
    """Write a minimal, installable wheel and return its path.

    A wheel is a zip with a ``dist-info`` directory, so one can be built here
    without a build backend, a network, or a compiler — which is what keeps the
    install in this test hermetic.
    """
    directory.mkdir(parents=True, exist_ok=True)
    dist_info = f"{name}-{version}.dist-info"
    members = {
        f"{name}/__init__.py": f'__version__ = "{version}"\n',
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nGenerator: scistudio-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    records = []
    for arcname, text in members.items():
        payload = text.encode("utf-8")
        digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")
        records.append(f"{arcname},sha256={digest},{len(payload)}")
    records.append(f"{dist_info}/RECORD,,")
    members[f"{dist_info}/RECORD"] = "\n".join(records) + "\n"

    path = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for arcname, text in members.items():
            archive.writestr(arcname, text)
    return path


@requires_kernel
@pytest.mark.serial
def test_a_bridge_call_waits_behind_a_running_cell(bridge_over_kernel: Callable[..., Any]) -> None:
    """The shallow freeze of ADR-054 §6.3, stated as a test rather than a note.

    A bridge call shares the execute channel with cells, so it completes after
    the cell ahead of it and reports the namespace as of *then* — which is why
    a panel keeps its last window while a long cell runs.
    """
    import threading

    bridge = bridge_over_kernel()
    handle = bridge.handle
    finished: list[float] = []

    def slow_cell() -> None:
        handle.execute("import time\ntime.sleep(1.5)\nlate = 'bound by the slow cell'", timeout=_EXEC_TIMEOUT)
        finished.append(time.monotonic())

    worker = threading.Thread(target=slow_cell, daemon=True)
    worker.start()
    time.sleep(0.2)
    listed = {binding.name for binding in bridge.bindings()}
    answered = time.monotonic()
    worker.join(timeout=_EXEC_TIMEOUT)

    assert finished, "the slow cell never finished"
    assert answered >= finished[0], "the bridge answered before the cell ahead of it"
    assert "late" in listed, "the bridge did not see the namespace the cell left"
