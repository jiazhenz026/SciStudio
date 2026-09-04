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

Two things live here that a reader might expect to find elsewhere.

The **environment snapshot's** reference and store are
:mod:`scistudio.core.lineage.environment`'s code, and their tests are here
because they are T-011's evidence and T-011 is this module's task: the snapshot
is captured through the bridge, from inside the kernel, and stored once per
distinct environment. Splitting the capture from what is done with it would put
the two halves of one requirement in two files.

The **block call** is answered by this module and performed by
:mod:`scistudio.explore.block_call` (spec §4.2; see that split's rationale in
the bridge's own docstring). The adapter's behaviour is
``tests/explore/test_block_call_adapter.py``'s subject and is not repeated
here; what is tested here is the wiring across the frame.
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
from dataclasses import dataclass
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


def test_bindings_carry_the_scistudio_type_and_the_native_one(frame: Any) -> None:
    """FR-038's answer and the person's, side by side (#2240).

    A packaged port is typed by "the SciStudio type of the object bound to that
    name at packaging", and this side of the bridge is the only one holding the
    object. Reporting only ``type(value).__name__`` handed packaging a name that
    resolves against nothing, and the person was told their ``str`` output "is
    bound to nothing in the kernel".

    The native name has to survive the translation: ``text`` is a ``str`` in the
    namespace the person is reading, whatever a port would call it.
    """
    namespace = {"text": "hello", "df": frame, "count": 3}
    by_name = {binding.name: binding for binding in bindings(namespace)}

    assert by_name["text"].type_name == "Text"
    assert by_name["text"].native_type_name == "str"
    assert by_name["df"].type_name == "DataFrame"
    assert by_name["df"].native_type_name == "DataFrame"
    assert by_name["count"].type_name == "int", "a value with no SciStudio type keeps its own name"
    assert by_name["count"].native_type_name == "int"


def test_the_type_name_is_the_one_wrap_native_would_produce(frame: Any) -> None:
    """The translation and the wrapping must not drift apart.

    :func:`~scistudio.explore.kernel_bridge.scistudio_type_name` answers *which*
    SciStudio type a value would become without building one, because a bindings
    list is redrawn on every namespace change and
    :func:`~scistudio.explore.notebook_api.wrap_native` on a pandas frame copies
    the person's data into Arrow. Two implementations of one mapping is exactly
    the shape of the bug this replaced, so they are pinned to each other here
    rather than trusted to stay in step.
    """
    import numpy

    from scistudio.core.types.text import Text
    from scistudio.explore.kernel_bridge import scistudio_type_name
    from scistudio.explore.notebook_api import wrap_native

    values: list[Any] = [
        "hello",
        Path("some/file.txt"),
        frame,
        frame["value"],
        pyarrow.table({"value": [1, 2]}),
        numpy.arange(6).reshape(2, 3),
        Text(content="already typed"),
    ]
    for value in values:
        assert scistudio_type_name(value) == type(wrap_native(value)).__name__, (
            f"the two disagree about {type(value).__name__}"
        )


def test_a_value_with_no_scistudio_type_is_answered_as_none() -> None:
    """``None`` where ``wrap_native`` would raise, which is the honest answer.

    A port of that type cannot be materialised, and saying so at packaging —
    where the cell can still be named — beats guessing a type that fails at the
    exchange layer.
    """
    from scistudio.explore.kernel_bridge import scistudio_type_name
    from scistudio.explore.notebook_api import wrap_native

    class Bespoke:
        pass

    for value in (3, {"a": 1}, [1, 2], Bespoke()):
        assert scistudio_type_name(value) is None
        with pytest.raises(TypeError):
            wrap_native(value)


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


# ---------------------------------------------------------------------------
# The block-call action (FR-049, FR-051)
#
# The adapter's behaviour is ``tests/explore/test_block_call_adapter.py``'s
# subject and is not repeated here. What is tested here is the *wiring*: that a
# payload's shape is understood, that inputs resolve to this kernel's
# variables, that outputs land back in it, and that a result and a failure both
# survive the base64 frame this module's protocol travels in.
# ---------------------------------------------------------------------------


class _Doubler:
    """A stand-in adapter: enough of the block-call surface for the wiring under test.

    A real :class:`~scistudio.explore.block_call.BlockCallAdapter` needs a
    registry and a registered block, and reaching for one here would test that
    module a second time. What the action needs from an adapter is one method
    and one result shape, so that is what this provides — and the assertions
    below are then about the bridge alone.
    """

    def __init__(self, outputs: dict[str, Any] | None = None, raises: Exception | None = None) -> None:
        self.outputs = outputs if outputs is not None else {"doubled": [2, 4, 6]}
        self.raises = raises
        self.seen: dict[str, Any] = {}

    def call_detailed(self, identifier: str, /, *, inputs: Any = None, config: Any = None) -> Any:
        """Record the call, then fail or return a result carrying lineage."""
        self.seen = {"identifier": identifier, "inputs": dict(inputs or {}), "config": dict(config or {})}
        if self.raises is not None:
            raise self.raises
        return _Result(outputs=dict(self.outputs), lineage=_lineage_for(identifier))

    def call(self, identifier: str, /, **kwargs: Any) -> Any:
        """The notebook-facing form ``blocks.run`` delegates to."""
        self.seen = {"identifier": identifier, "kwargs": dict(kwargs)}
        if self.raises is not None:
            raise self.raises
        return next(iter(self.outputs.values()))


@dataclass(frozen=True)
class _Result:
    """The two fields of ``BlockCallResult`` the action reads."""

    outputs: dict[str, Any]
    lineage: Any


def _lineage_for(identifier: str) -> Any:
    """A real :class:`BlockCallLineage` with one edge, to render across the frame."""
    from scistudio.explore.block_call import BlockCallEdge, BlockCallLineage

    return BlockCallLineage(
        session_id="session-1",
        block_identifier=identifier,
        block_type="doubler",
        block_version="1.0.0",
        block_config_resolved={"factor": 2},
        started_at="2026-09-04T00:00:00Z",
        finished_at="2026-09-04T00:00:01Z",
        duration_ms=1000,
        termination="completed",
        edges=(
            BlockCallEdge(
                direction="output",
                port_name="doubled",
                object_id="object-1",
                position=0,
                type_name="Array",
                # An object that could never be JSON: the point of the assertion below.
                data_object=object(),
            ),
        ),
    )


@pytest.fixture
def stub_adapter() -> Iterator[Callable[..., _Doubler]]:
    """Install a stand-in adapter for the duration of one test, then drop it."""

    def install(**kwargs: Any) -> _Doubler:
        adapter = _Doubler(**kwargs)
        kernel_bridge.set_block_call_adapter(adapter)
        return adapter

    try:
        yield install
    finally:
        kernel_bridge.set_block_call_adapter(None)


def test_a_block_call_reads_its_inputs_from_the_kernel_namespace(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """An input names a variable, and the object behind that name is what runs (FR-049).

    Values cannot cross the frame, so the payload carries names. This is the
    half of the wiring that turns one into the other.
    """
    adapter = stub_adapter()
    values = [1, 2, 3]
    namespace: dict[str, Any] = {"data": values}

    kernel_bridge._dispatch(
        namespace,
        _request(action="block_call", identifier="Doubler", inputs={"img": "data"}, config={"factor": 2}),
    )
    response = _decode_frame(capsys.readouterr().out)

    assert response["ok"] is True
    assert adapter.seen["identifier"] == "Doubler"
    assert adapter.seen["inputs"]["img"] is values, "the adapter got a copy, not the kernel's own object"
    assert adapter.seen["config"] == {"factor": 2}


def test_a_block_call_binds_its_result_back_into_the_kernel(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """The output stays in the kernel under the name the caller asked for."""
    stub_adapter()
    namespace: dict[str, Any] = {"data": [1, 2, 3]}

    kernel_bridge._dispatch(
        namespace,
        _request(action="block_call", identifier="Doubler", inputs={"img": "data"}, bind="result"),
    )
    response = _decode_frame(capsys.readouterr().out)

    assert namespace["result"] == [2, 4, 6]
    assert response["result"]["bound"] == {"doubled": "result"}
    assert response["result"]["outputs"] == {"doubled": "list"}


def test_a_block_call_binds_several_outputs_by_port(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """A block with two outputs is bound by a mapping, one variable per port."""
    stub_adapter(outputs={"left": "L", "right": "R"})
    namespace: dict[str, Any] = {}

    kernel_bridge._dispatch(
        namespace,
        _request(action="block_call", identifier="Two", bind={"left": "a", "right": "b"}),
    )
    _decode_frame(capsys.readouterr().out)

    assert (namespace["a"], namespace["b"]) == ("L", "R")


def test_a_block_call_refuses_one_name_for_several_outputs(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """One name and two outputs is ambiguous, so it is refused rather than guessed."""
    stub_adapter(outputs={"left": "L", "right": "R"})
    namespace: dict[str, Any] = {}

    kernel_bridge._dispatch(namespace, _request(action="block_call", identifier="Two", bind="result"))
    response = _decode_frame(capsys.readouterr().out)

    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"
    assert "left, right" in response["error"]["message"]
    assert namespace == {}


def test_a_block_call_that_binds_nothing_still_reports(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """A call made for its lineage alone leaves the namespace untouched."""
    stub_adapter()
    namespace: dict[str, Any] = {"data": [1, 2, 3]}

    kernel_bridge._dispatch(namespace, _request(action="block_call", identifier="Doubler"))
    response = _decode_frame(capsys.readouterr().out)

    assert response["result"]["bound"] == {}
    assert list(namespace) == ["data"]


def test_a_block_calls_lineage_survives_the_frame(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """FR-051's facts reach the caller; the edge's data object deliberately does not.

    The reply has been through ``json.dumps`` and base64 by the time it is read
    here, so this asserts what actually survives rather than what the dataclass
    holds. The data object exists only in the kernel and no serialisation of it
    would be the same object, so the frame carries facts and the caller takes
    objects from the adapter's own callback inside the kernel.
    """
    stub_adapter()

    kernel_bridge._dispatch({"data": [1]}, _request(action="block_call", identifier="Doubler"))
    lineage = _decode_frame(capsys.readouterr().out)["result"]["lineage"]

    assert lineage["session_id"] == "session-1"
    assert lineage["block_type"] == "doubler"
    assert lineage["block_version"] == "1.0.0"
    assert lineage["block_config_resolved"] == {"factor": 2}
    assert lineage["termination"] == "completed"
    assert lineage["duration_ms"] == 1000
    assert lineage["edges"] == [
        {
            "direction": "output",
            "port_name": "doubled",
            "object_id": "object-1",
            "position": 0,
            "type_name": "Array",
        }
    ]


def test_a_block_call_names_an_input_the_kernel_does_not_have(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """An input naming an unbound variable is refused before the block runs."""
    adapter = stub_adapter()

    kernel_bridge._dispatch({}, _request(action="block_call", identifier="Doubler", inputs={"img": "missing"}))
    response = _decode_frame(capsys.readouterr().out)

    assert response["ok"] is False
    assert "missing" in response["error"]["message"]
    assert adapter.seen == {}, "the block ran despite an unresolvable input"


def test_a_block_call_failure_comes_back_as_an_answer(
    capsys: pytest.CaptureFixture[str], stub_adapter: Callable[..., _Doubler]
) -> None:
    """A block that raises reaches the caller as a named error, not a lost traceback."""
    from scistudio.explore.block_call import BlockNotFoundError

    stub_adapter(raises=BlockNotFoundError("no block named 'Nope'"))

    kernel_bridge._dispatch({}, _request(action="block_call", identifier="Nope"))
    response = _decode_frame(capsys.readouterr().out)

    assert response["ok"] is False
    assert response["error"]["type"] == "BlockNotFoundError"
    assert "Nope" in response["error"]["message"]


@pytest.fixture
def injected_blocks() -> Iterator[Any]:
    """Install the ``blocks`` binding into a bare namespace and hand both back."""
    namespace: dict[str, Any] = {}
    kernel_bridge._inject_blocks(namespace)
    try:
        yield namespace
    finally:
        kernel_bridge.set_block_call_adapter(None)


def test_the_bound_name_is_the_one_the_analysis_matches() -> None:
    """The graph records calls to ``blocks.run``; the kernel binds that name (FR-049).

    Read from the analysis's own constant rather than spelled twice, so the two
    cannot drift into recording calls to a name nothing binds.
    """
    from scistudio.explore.dependency_analysis import BLOCK_CALL_PATHS

    assert kernel_bridge.BLOCKS_NAME == BLOCK_CALL_PATHS[0][0] == "blocks"


def test_installing_the_bridge_binds_blocks(capsys: pytest.CaptureFixture[str]) -> None:
    """A cell can call a block because install put the name there (FR-049)."""
    namespace: dict[str, Any] = {}
    kernel_bridge._dispatch(namespace, _request(action=kernel_bridge.INSTALL_PROBE))
    response = _decode_frame(capsys.readouterr().out)

    assert response["ok"] is True
    assert response["result"]["blocks"] == "blocks"
    assert hasattr(namespace["blocks"], "run")
    kernel_bridge.set_block_call_adapter(None)


def test_the_blocks_binding_is_not_a_notebook_variable(injected_blocks: dict[str, Any]) -> None:
    """All three reports leave it out: the person did not put it there.

    Asserted on the three surfaces separately, because they are three call
    sites and a fix applied to one of them would leave the others leaking.
    """
    injected_blocks["df"] = [1, 2, 3]

    assert set(fingerprints(injected_blocks)) == {"df"}
    assert [binding.name for binding in bindings(injected_blocks)] == ["df"]
    with pytest.raises(KeyError, match="blocks"):
        variable_window(injected_blocks, "blocks")


def test_a_cells_own_blocks_wins_and_stops_being_hidden(injected_blocks: dict[str, Any]) -> None:
    """A rebound ``blocks`` is the person's variable, and is reported as one.

    Their assignment wins because the namespace is theirs and Jupyter's
    semantics are that a cell binds what it binds. The consequence is that the
    name stops being hidden: at that point it holds a value they created, so
    leaving it out of the bindings list would hide one of their own variables
    from them — a worse failure than losing ``blocks.run``, which is the same
    cost as shadowing ``list``.
    """
    injected_blocks["blocks"] = "mine now"

    assert set(fingerprints(injected_blocks)) == {"blocks"}
    listed = bindings(injected_blocks)
    assert [binding.name for binding in listed] == ["blocks"]
    assert listed[0].summary == "str of 8"
    window = variable_window(injected_blocks, "blocks")
    assert window.get("error") is None
    assert window["payload"]["content"] == "mine now"


def test_the_blocks_binding_resolves_its_adapter_per_call(
    injected_blocks: dict[str, Any], stub_adapter: Callable[..., _Doubler]
) -> None:
    """Kernel start binds a name, not an adapter, so installing one later still works.

    Binding an adapter at install would scan the whole block registry in front
    of the person's first cell; this is what keeps that off the start path and
    what lets a session attach its own registry and interaction channel
    afterwards (FR-050).
    """
    adapter = stub_adapter(outputs={"out": "ran"})

    assert injected_blocks["blocks"].run("Doubler", value=1) == "ran"
    assert adapter.seen["identifier"] == "Doubler"


def test_the_adapter_is_built_once_and_replaceable() -> None:
    """The kernel keeps one adapter, because a kernel serves one session (FR-001).

    A registry and an interaction channel are objects, so they cannot cross the
    frame; the adapter has to be built kernel-side and installed there.
    """
    kernel_bridge.set_block_call_adapter(None)
    try:
        stand_in = object()
        kernel_bridge.set_block_call_adapter(stand_in)
        assert kernel_bridge.block_call_adapter() is stand_in
        assert kernel_bridge.block_call_adapter("another-session") is stand_in
    finally:
        kernel_bridge.set_block_call_adapter(None)


def test_the_driver_sends_only_what_it_was_given(stub_adapter: Callable[..., _Doubler]) -> None:
    """``KernelBridge.block_call`` builds the payload the dispatcher reads.

    The driver and the dispatcher are the two ends of one contract, so this
    runs the payload the driver would send straight into the dispatcher rather
    than asserting on its shape.
    """
    from scistudio.explore.kernel_bridge import KernelBridge

    sent: dict[str, Any] = {}

    class _Recorder:
        def execute_silent(self, code: str, *, timeout: float | None = None) -> Any:
            sent["code"] = code
            raise AssertionError("not reached: the payload is decoded below instead")

    bridge = KernelBridge(_Recorder())  # type: ignore[arg-type]
    with contextlib.suppress(AssertionError):
        bridge.block_call("Doubler", inputs={"img": "data"}, bind="result", session_id="s1")

    encoded = re.search(r'_dispatch\(globals\(\), "([A-Za-z0-9+/=]*)"\)', sent["code"])
    assert encoded is not None
    payload = json.loads(base64.b64decode(encoded.group(1)).decode("utf-8"))
    assert payload == {
        "action": "block_call",
        "identifier": "Doubler",
        "inputs": {"img": "data"},
        "bind": "result",
        "session_id": "s1",
    }


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


#: A block, and the registration that makes it findable, written into a
#: directory the kernel is given on ``PYTHONPATH``. The kernel is a separate
#: process and cannot import this test module, and the registry resolves a spec
#: to ``module_path`` + ``class_name`` at instantiation time, so the block has
#: to live in a module the kernel can import under exactly that name.
_PROBE_BLOCK_MODULE = '''
"""A block and its registration, for the cell-facing block call (FR-049)."""

from typing import Any, ClassVar

from scistudio.blocks.base import Block, BlockConfig, OutputPort
from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.core.types import Text
from scistudio.explore.block_call import BlockCallAdapter
from scistudio.explore.kernel_bridge import set_block_call_adapter


class Greeter(Block):
    """Returns its ``greeting`` configuration as a Text output."""

    name = "Greeter"
    version = "1.0.0"
    input_ports: ClassVar[list] = []
    output_ports: ClassVar[list[OutputPort]] = [OutputPort(name="out", accepted_types=[Text])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Return the configured greeting."""
        return {"out": Text(content=config.get("greeting", "hello"))}


def install() -> None:
    """Register Greeter and hand the kernel an adapter that can resolve it."""
    registry = BlockRegistry()
    spec = BlockSpec(
        name=Greeter.name,
        type_name=Greeter.name.lower(),
        version=Greeter.version,
        module_path=__name__,
        class_name=Greeter.__name__,
        base_category="process",
        input_ports=[],
        output_ports=list(Greeter.output_ports),
        execution_mode=Greeter.execution_mode.value,
    )
    registry._registry[spec.name] = spec
    registry._aliases[spec.type_name] = spec.name
    set_block_call_adapter(BlockCallAdapter(registry=registry, session_id="session-1"))
'''


@requires_kernel
@pytest.mark.serial
def test_a_cell_calls_a_block_through_the_bound_name(kernels: Callable[..., Any], tmp_path: Path) -> None:
    """FR-049 end to end: a cell writes ``blocks.run(...)`` and gets an object back.

    The point of the binding is a cell reaching a block, so this is a cell —
    executed on a real kernel, with a real block in a real registry — rather
    than a unit test of the binding. It also pins the two exclusions that
    matter once the name exists: ``blocks`` is not reported as one of the
    person's variables, and the value the cell bound is.
    """
    from scistudio.explore.kernel_bridge import KernelBridge

    module_dir = tmp_path / "probe"
    module_dir.mkdir()
    (module_dir / "scistudio_probe_block.py").write_text(_PROBE_BLOCK_MODULE, encoding="utf-8")
    inherited = os.environ.get("PYTHONPATH", "")
    handle = kernels(env={"PYTHONPATH": os.pathsep.join(filter(None, [str(module_dir), inherited]))})
    handle.start()
    bridge = KernelBridge(handle, timeout=_EXEC_TIMEOUT)
    bridge.install(mode="session")

    prepared = handle.execute("import scistudio_probe_block\nscistudio_probe_block.install()", timeout=_EXEC_TIMEOUT)
    assert prepared.status == "ok", prepared.error

    result = handle.execute(
        'greeting = blocks.run("Greeter", greeting="from a cell")\nprint(greeting)',
        timeout=_EXEC_TIMEOUT,
    )
    printed = "".join(output.text or "" for output in result.outputs if output.output_type == "stream")

    assert result.status == "ok", result.error
    assert printed.strip() == "from a cell"

    listed = {binding.name: binding for binding in bridge.bindings()}
    assert "greeting" in listed, "the cell's own variable is missing from the bindings list"
    assert "blocks" not in listed, "the injected name was reported as one of the person's variables"
    assert "blocks" not in bridge.fingerprints()


@requires_kernel
@pytest.mark.serial
def test_a_cell_that_rebinds_blocks_keeps_its_own_value(bridge_over_kernel: Callable[..., Any]) -> None:
    """The person's assignment wins, and the name is then reported as theirs.

    Jupyter's semantics are that a cell binds what it binds, and this is their
    namespace. Once ``blocks`` holds a value they made, hiding it would hide
    one of their own variables from them.
    """
    bridge = bridge_over_kernel()

    assert "blocks" not in {binding.name for binding in bridge.bindings()}, "it starts hidden"
    bridge.handle.execute("blocks = [1, 2, 3]", timeout=_EXEC_TIMEOUT)

    listed = {binding.name: binding for binding in bridge.bindings()}
    assert listed["blocks"].summary == "list of 3"
    assert "blocks" in bridge.fingerprints()


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
