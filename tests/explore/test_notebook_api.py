"""The three notebook helpers in both modes (ADR-054 T-004, FR-010, FR-011).

The test this module exists for is
:func:`test_the_same_notebook_runs_in_both_modes`: one fixture notebook, one
source string, executed once in session mode and once in packaged mode, with
the outputs compared. Everything else here is the detail that test rests on.
It runs the source through ``exec`` in a fresh namespace, which is what a
kernel does with a cell and what ``nbconvert`` does with a packaged notebook —
and it runs the *same* string both times, so a change that breaks the promise
of FR-010/FR-011 breaks this test rather than passing two mode-specific ones.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scistudio.explore import notebook_api
from scistudio.explore.notebook_api import (
    EXCHANGE_DIR_ENV_VAR,
    INPUTS_DIR_ENV_VAR,
    MODE_ENV_VAR,
    OUTPUTS_DIR_ENV_VAR,
    PACKAGED_MODE,
    SESSION_MODE,
    NotebookLoadError,
    NotebookModeError,
    NotebookPortError,
    SessionBinding,
    current_mode,
    decode_artefact_reference,
    encode_artefact_reference,
    is_artefact_reference,
    wrap_native,
)

pandas = pytest.importorskip("pandas")
pyarrow = pytest.importorskip("pyarrow")
numpy = pytest.importorskip("numpy")


#: The fixture notebook. One string, run unchanged in both modes: this is the
#: contract of FR-010 and FR-011 written down as source. It imports
#: ``scistudio`` the way a notebook does, so the lazy top-level exposure is
#: part of what is under test.
NOTEBOOK_SOURCE = """import scistudio

table = scistudio.load(scistudio.input("table"))
frame = table.to_memory().to_pandas()
frame["doubled"] = frame["value"] * 2
scistudio.output(result=frame)
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_helper_state() -> Iterator[None]:
    """Reset the module's process state and the environment around every test.

    The helpers keep the session binding and the declared outputs in module
    globals, because inside a kernel there is one of each per process. A test
    that left either behind would make the next one pass for the wrong reason.
    """
    saved_env = dict(os.environ)
    notebook_api.clear_session()
    try:
        yield
    finally:
        notebook_api.clear_session()
        os.environ.clear()
        os.environ.update(saved_env)


@pytest.fixture
def frame() -> Any:
    """The three-row table both modes are fed."""
    return pandas.DataFrame({"value": [1, 2, 3]})


def run_notebook(source: str, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute *source* the way a kernel executes a cell, and return its namespace."""
    namespace = namespace if namespace is not None else {"__name__": "__main__"}
    # Executing notebook source is the subject of this module, not a hazard in it.
    exec(compile(source, "<notebook>", "exec"), namespace)
    return namespace


def session_inputs(tmp_path: Path, frame: Any) -> dict[str, str]:
    """Persist *frame* as a session's bound input artefact and reference it."""
    from scistudio.core.types.dataframe import DataFrame

    tmp_path.mkdir(parents=True, exist_ok=True)
    table = pyarrow.Table.from_pandas(frame, preserve_index=False)
    stored = DataFrame(columns=list(table.column_names), row_count=table.num_rows, data=table)
    reference = stored.save(str(tmp_path / "table.parquet"))
    return {
        "table": encode_artefact_reference(
            type_name="DataFrame",
            backend=reference.backend,
            path=reference.path,
            format=reference.format,
        )
    }


def packaged_exchange(tmp_path: Path, frame: Any) -> Path:
    """Build a Code Block exchange folder holding *frame* on the ``table`` port."""
    exchange = tmp_path / "exchange"
    input_folder = exchange / "inputs" / "table"
    output_folder = exchange / "outputs" / "result"
    input_folder.mkdir(parents=True)
    output_folder.mkdir(parents=True)
    (exchange / "tmp").mkdir(parents=True)
    frame.to_csv(input_folder / "table.csv", index=False)
    manifest = {
        "ports": {
            "input:table": _port_record("table", "input", input_folder),
            "output:result": _port_record("result", "output", output_folder),
        }
    }
    (exchange / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return exchange


def _port_record(name: str, direction: str, folder: Path) -> dict[str, Any]:
    """One manifest port record, in the shape the Code Block runtime writes."""
    return {
        "name": name,
        "direction": direction,
        "object_type": "DataFrame",
        "folder": str(folder),
        "format_hint": ".csv",
        "capability_id": None,
        "required": True,
        "status": "materialised" if direction == "input" else "folder_created",
        "files": [],
    }


def enter_session_mode(inputs: dict[str, str]) -> None:
    """Put this process in session mode with *inputs* bound, as the bridge does."""
    os.environ[MODE_ENV_VAR] = SESSION_MODE
    notebook_api.bind_session(SessionBinding(inputs=inputs))


def enter_packaged_mode(exchange: Path) -> None:
    """Put this process in packaged mode, as the Code Block runtime does."""
    os.environ[MODE_ENV_VAR] = PACKAGED_MODE
    os.environ[EXCHANGE_DIR_ENV_VAR] = str(exchange)
    os.environ[INPUTS_DIR_ENV_VAR] = str(exchange / "inputs")
    os.environ[OUTPUTS_DIR_ENV_VAR] = str(exchange / "outputs")


# ---------------------------------------------------------------------------
# The test this module exists for
# ---------------------------------------------------------------------------


def test_the_same_notebook_runs_in_both_modes(tmp_path: Path, frame: Any) -> None:
    """One source string, two modes, equal outputs (FR-010, FR-011).

    This is the two-mode design's whole claim: a person explores, packages, and
    the block runs the notebook they wrote. It is one test rather than two
    because two tests that each assert their own mode in isolation would both
    still pass if the modes diverged.
    """
    enter_session_mode(session_inputs(tmp_path / "session", frame))
    session_namespace = run_notebook(NOTEBOOK_SOURCE)
    declared = notebook_api.declared_outputs()
    assert [entry.name for entry in declared] == ["result"]
    session_result = declared[0].value

    notebook_api.clear_session()
    exchange = packaged_exchange(tmp_path / "packaged", frame)
    enter_packaged_mode(exchange)
    packaged_namespace = run_notebook(NOTEBOOK_SOURCE)

    # The declaration wrote a file in packaged mode and nothing in session mode
    # (FR-010: "without writing anything"), which is the one visible difference.
    written = sorted((exchange / "outputs" / "result").iterdir())
    assert [path.name for path in written] == ["result.csv"]
    packaged_result = pandas.read_csv(written[0])

    pandas.testing.assert_frame_equal(
        session_result.reset_index(drop=True),
        packaged_result.reset_index(drop=True),
        check_dtype=False,
    )
    # The cell *before* the declaration must agree too, or the loads differed
    # and the outputs only happened to match.
    pandas.testing.assert_frame_equal(
        session_namespace["frame"].reset_index(drop=True),
        packaged_namespace["frame"].reset_index(drop=True),
        check_dtype=False,
    )


def test_session_mode_declares_without_writing(tmp_path: Path, frame: Any) -> None:
    """A session's ``scistudio.output`` writes nothing anywhere (FR-010)."""
    session_dir = tmp_path / "session"
    enter_session_mode(session_inputs(session_dir, frame))
    before = sorted(path.name for path in session_dir.rglob("*"))
    run_notebook(NOTEBOOK_SOURCE)
    assert sorted(path.name for path in session_dir.rglob("*")) == before


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


def test_mode_comes_from_the_environment() -> None:
    """The launcher's variable, and nothing else, selects the mode (FR-010)."""
    os.environ[MODE_ENV_VAR] = SESSION_MODE
    assert current_mode() == SESSION_MODE
    os.environ[MODE_ENV_VAR] = PACKAGED_MODE
    assert current_mode() == PACKAGED_MODE


def test_no_mode_is_an_error_not_a_default() -> None:
    """An unset mode refuses rather than guessing, and names the variable."""
    os.environ.pop(MODE_ENV_VAR, None)
    with pytest.raises(NotebookModeError, match=MODE_ENV_VAR):
        current_mode()


def test_an_unknown_mode_is_refused() -> None:
    """A misspelt mode is an error; silently falling back would write the wrong place."""
    os.environ[MODE_ENV_VAR] = "packaging"
    with pytest.raises(NotebookModeError, match="packaging"):
        current_mode()


def test_helpers_refuse_outside_a_notebook() -> None:
    """Each helper refuses with the same explanation when no mode is set."""
    os.environ.pop(MODE_ENV_VAR, None)
    with pytest.raises(NotebookModeError):
        notebook_api.input("x")
    with pytest.raises(NotebookModeError):
        notebook_api.output(x=1)


def test_session_mode_without_a_binding_says_so() -> None:
    """Session mode with no binding installed names the bridge, not the variable."""
    os.environ[MODE_ENV_VAR] = SESSION_MODE
    with pytest.raises(NotebookModeError, match="bridge"):
        notebook_api.input("table")


def test_packaged_mode_without_exchange_folders_says_so() -> None:
    """Packaged mode outside the Code Block runtime names the missing variable."""
    os.environ[MODE_ENV_VAR] = PACKAGED_MODE
    os.environ.pop(EXCHANGE_DIR_ENV_VAR, None)
    os.environ.pop(INPUTS_DIR_ENV_VAR, None)
    with pytest.raises(NotebookModeError, match=INPUTS_DIR_ENV_VAR):
        notebook_api.input("table")


# ---------------------------------------------------------------------------
# Artefact references
# ---------------------------------------------------------------------------


def test_artefact_reference_round_trips() -> None:
    """A reference carries the type and the storage pointer, both ways."""
    reference = encode_artefact_reference(
        type_name="DataFrame", backend="arrow", path="a b/c.parquet", format="parquet"
    )
    assert is_artefact_reference(reference)
    type_name, storage = decode_artefact_reference(reference)
    assert type_name == "DataFrame"
    assert (storage.backend, storage.path, storage.format) == ("arrow", "a b/c.parquet", "parquet")


def test_a_plain_path_is_not_an_artefact_reference() -> None:
    """A path never looks like a reference, so ``load`` cannot confuse the two."""
    assert not is_artefact_reference("data/raw/table.csv")
    assert not is_artefact_reference(Path("data/raw/table.csv"))
    with pytest.raises(ValueError, match="Not an artefact reference"):
        decode_artefact_reference("data/raw/table.csv")


def test_a_reference_without_a_path_is_refused() -> None:
    """A reference that points at nothing is an error, not an empty load."""
    with pytest.raises(ValueError, match="path"):
        decode_artefact_reference("scistudio+artefact:?type=DataFrame&backend=arrow")


# ---------------------------------------------------------------------------
# Wrapping native objects
# ---------------------------------------------------------------------------


def test_wrap_native_returns_a_data_object_unchanged() -> None:
    """Wrapping is idempotent, so ``output`` accepts either kind of value."""
    from scistudio.core.types.text import Text

    original = Text(content="already typed")
    assert wrap_native(original) is original


def test_wrap_native_covers_the_core_kinds(tmp_path: Path, frame: Any) -> None:
    """Each native kind becomes the SciStudio type the IO loaders already use."""
    from scistudio.core.types.array import Array
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.core.types.series import Series
    from scistudio.core.types.text import Text

    assert isinstance(wrap_native("note"), Text)
    assert isinstance(wrap_native(tmp_path), Artifact)
    assert isinstance(wrap_native(frame), DataFrame)
    assert isinstance(wrap_native(pyarrow.Table.from_pandas(frame, preserve_index=False)), DataFrame)
    assert isinstance(wrap_native(frame["value"]), Series)

    array = wrap_native(numpy.zeros((2, 3)))
    assert isinstance(array, Array)
    assert array.axes == ["axis_0", "axis_1"]
    assert array.shape == (2, 3)


def test_wrap_native_names_the_type_it_cannot_wrap() -> None:
    """An unwrappable value says which type it was, not that "something failed"."""

    class Widget:
        pass

    with pytest.raises(TypeError, match="Widget"):
        wrap_native(Widget())


def test_wrap_native_keeps_a_series_single_column(frame: Any) -> None:
    """A Series is a single-column Arrow table, the repository's own convention."""
    series = wrap_native(frame["value"])
    assert series.value_name == "value"
    assert series.length == 3


# ---------------------------------------------------------------------------
# Session mode
# ---------------------------------------------------------------------------


def test_session_input_returns_the_bound_reference(tmp_path: Path, frame: Any) -> None:
    """``input`` hands back the reference the session bound (FR-010)."""
    inputs = session_inputs(tmp_path, frame)
    enter_session_mode(inputs)
    assert notebook_api.input("table") == inputs["table"]


def test_session_input_names_the_ports_that_exist(tmp_path: Path, frame: Any) -> None:
    """A typo names the ports the session actually has."""
    enter_session_mode(session_inputs(tmp_path, frame))
    with pytest.raises(NotebookPortError, match="table"):
        notebook_api.input("tabel")


def test_session_load_resolves_through_storage(tmp_path: Path, frame: Any) -> None:
    """``load`` turns a reference into a storage-backed object (FR-010)."""
    inputs = session_inputs(tmp_path, frame)
    enter_session_mode(inputs)
    loaded = notebook_api.load(notebook_api.input("table"))
    assert loaded.storage_ref is not None
    pandas.testing.assert_frame_equal(loaded.to_memory().to_pandas(), frame, check_dtype=False)


def test_the_later_declaration_of_a_name_wins(tmp_path: Path, frame: Any) -> None:
    """A name declared twice keeps the later value and the later position."""
    enter_session_mode(session_inputs(tmp_path, frame))
    notebook_api.output(first=1)
    notebook_api.output(second=2)
    notebook_api.output(first=99)
    declared = notebook_api.declared_outputs()
    assert [entry.name for entry in declared] == ["second", "first"]
    assert declared[-1].value == 99


def test_a_restart_drops_the_declarations(tmp_path: Path, frame: Any) -> None:
    """``clear_session`` resets declarations, as a kernel restart resets marks (FR-023)."""
    enter_session_mode(session_inputs(tmp_path, frame))
    notebook_api.output(result=1)
    assert notebook_api.declared_outputs()
    notebook_api.clear_session()
    assert notebook_api.declared_outputs() == ()
    assert notebook_api.session_binding() is None


# ---------------------------------------------------------------------------
# Packaged mode
# ---------------------------------------------------------------------------


def test_packaged_input_returns_the_materialised_file(tmp_path: Path, frame: Any) -> None:
    """``input`` hands back the file the exchange materialised (FR-011)."""
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    path = notebook_api.input("table")
    assert isinstance(path, Path)
    assert path == exchange / "inputs" / "table" / "table.csv"


def test_packaged_input_without_a_manifest_uses_the_folder_name(tmp_path: Path, frame: Any) -> None:
    """A hand-made exchange folder still works; the manifest is an optimisation."""
    exchange = packaged_exchange(tmp_path, frame)
    (exchange / "manifest.json").unlink()
    enter_packaged_mode(exchange)
    assert notebook_api.input("table").name == "table.csv"


def test_packaged_input_refuses_an_ambiguous_port(tmp_path: Path, frame: Any) -> None:
    """Two files on one port is refused, not resolved by a filename sort."""
    exchange = packaged_exchange(tmp_path, frame)
    frame.to_csv(exchange / "inputs" / "table" / "extra.csv", index=False)
    enter_packaged_mode(exchange)
    with pytest.raises(NotebookPortError, match="2 files"):
        notebook_api.input("table")


def test_packaged_input_refuses_an_empty_port(tmp_path: Path, frame: Any) -> None:
    """An empty port folder says so rather than loading nothing."""
    exchange = packaged_exchange(tmp_path, frame)
    (exchange / "inputs" / "table" / "table.csv").unlink()
    enter_packaged_mode(exchange)
    with pytest.raises(NotebookPortError, match="empty"):
        notebook_api.input("table")


def test_packaged_input_names_an_unknown_port(tmp_path: Path, frame: Any) -> None:
    """An unknown port names the folders that exist."""
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    with pytest.raises(NotebookPortError, match="signal"):
        notebook_api.input("signal")


def test_packaged_load_is_storage_backed(tmp_path: Path, frame: Any) -> None:
    """A packaged load reads like a session load, which is what makes cells portable."""
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    loaded = notebook_api.load(notebook_api.input("table"))
    assert loaded.storage_ref is not None
    pandas.testing.assert_frame_equal(loaded.to_memory().to_pandas(), frame, check_dtype=False)


def test_packaged_load_stages_inside_the_exchange_folder(tmp_path: Path, frame: Any) -> None:
    """The staging copy goes in the run's own scratch folder and nowhere else."""
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    loaded = notebook_api.load(notebook_api.input("table"))
    staged = Path(loaded.storage_ref.path).resolve()
    assert staged.is_relative_to((exchange / "tmp").resolve())


def test_packaged_output_writes_through_the_adapters(tmp_path: Path, frame: Any) -> None:
    """``output`` writes the declared object into its port folder (FR-011)."""
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    notebook_api.output(result=frame)
    written = sorted((exchange / "outputs" / "result").iterdir())
    assert [path.name for path in written] == ["result.csv"]
    pandas.testing.assert_frame_equal(pandas.read_csv(written[0]), frame, check_dtype=False)


def test_packaged_output_refuses_a_name_that_is_not_a_port(tmp_path: Path, frame: Any) -> None:
    """A declaration the block has no port for is refused, not written somewhere.

    The manifest is authoritative in a real run, so a name it does not carry is
    not a port; inventing a folder for it would write the person's result where
    nothing collects it from and the run would report success.
    """
    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    with pytest.raises(NotebookPortError, match="result"):
        notebook_api.output(surprise=frame)
    assert sorted(path.name for path in (exchange / "outputs").iterdir()) == ["result"]


def test_packaged_output_without_a_manifest_says_what_is_missing(tmp_path: Path, frame: Any) -> None:
    """Writing needs the port's declared format, and only the manifest carries it.

    A ``DataFrame`` has six registered savers and the block registry refuses to
    pick between them; picking one here would decide a person's output format
    by accident, so the refusal names the file that would have decided it.
    """
    exchange = packaged_exchange(tmp_path, frame)
    (exchange / "manifest.json").unlink()
    enter_packaged_mode(exchange)
    with pytest.raises(NotebookPortError, match=r"manifest\.json"):
        notebook_api.output(result=frame)
    assert not list((exchange / "outputs" / "result").iterdir())


def test_packaged_output_accepts_a_typed_object(tmp_path: Path, frame: Any) -> None:
    """A cell that built the SciStudio type itself is written the same way."""
    from scistudio.core.types.dataframe import DataFrame

    exchange = packaged_exchange(tmp_path, frame)
    enter_packaged_mode(exchange)
    table = pyarrow.Table.from_pandas(frame, preserve_index=False)
    notebook_api.output(result=DataFrame(columns=list(table.column_names), row_count=3, data=table))
    assert sorted(path.name for path in (exchange / "outputs" / "result").iterdir()) == ["result.csv"]


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def test_load_returns_a_data_object_unchanged(tmp_path: Path, frame: Any) -> None:
    """``load(load(x))`` is harmless, so a cell may over-apply it."""
    from scistudio.core.types.text import Text

    enter_session_mode({})
    original = Text(content="hello")
    assert notebook_api.load(original) is original


def test_load_refuses_a_value_it_cannot_resolve(tmp_path: Path, frame: Any) -> None:
    """A value that is neither a reference, a path, nor an object names its type."""
    enter_session_mode({})
    with pytest.raises(NotebookLoadError, match="int"):
        notebook_api.load(7)


def test_load_names_a_missing_file(tmp_path: Path) -> None:
    """A session opened over a file that no longer exists fails with the path."""
    enter_session_mode({})
    missing = tmp_path / "gone.csv"
    with pytest.raises(NotebookLoadError, match=r"gone\.csv"):
        notebook_api.load(missing)


def test_load_reads_a_file_the_notebook_named(tmp_path: Path, frame: Any) -> None:
    """FR-004's file case: the first cell loads a path, in session mode."""
    enter_session_mode({})
    path = tmp_path / "table.csv"
    frame.to_csv(path, index=False)
    loaded = notebook_api.load(str(path))
    pandas.testing.assert_frame_equal(loaded.to_memory().to_pandas(), frame, check_dtype=False)


# ---------------------------------------------------------------------------
# The top-level exposure
# ---------------------------------------------------------------------------


def test_the_helpers_are_the_top_level_ones() -> None:
    """``scistudio.input`` is this module's ``input`` (FR-010, A-006)."""
    import scistudio

    assert scistudio.input is notebook_api.input
    assert scistudio.output is notebook_api.output
    assert scistudio.load is notebook_api.load
    assert {"input", "output", "load"} <= set(scistudio.__all__)


def test_an_unknown_top_level_attribute_still_raises() -> None:
    """The lazy hook answers for three names and refuses everything else."""
    import scistudio

    with pytest.raises(AttributeError, match="no attribute"):
        scistudio.__getattr__("not_a_helper")
