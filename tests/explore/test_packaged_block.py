"""Packaging a notebook into a Code Block (ADR-054 spec 3, T-014 and T-015).

The acceptance bar for this task is end to end, not a unit test of the
generator: a fixture notebook is packaged, the generated declaration is
**discovered by the block registry**, a workflow runs the block through the real
scheduler, and its outputs equal what the same notebook produces when its cells
are run in written order the way a session runs them. On top of that the
packaged run must execute the **slice** and not the whole notebook, which the
fixture proves with a side effect in a cell the slice excludes: the packaged run
must leave that side effect unperformed while the session run performs it.

Two notes on how the end-to-end tests are wired.

**nbconvert.** The notebook backend runs a notebook through Jupyter
``nbconvert``, which the repository does not depend on. Every existing notebook
test skips when it is absent (``tests/blocks/code/test_codeblock_notebooks.py``)
and these do the same, through ``SCISTUDIO_TEST_NBCONVERT`` — an executable path
— or an ``nbconvert`` on the path. Nothing is mocked in its place: without a
real notebook execution there is nothing here worth asserting, so the test skips
rather than pretending.

**The notebook helpers.** ``scistudio.input`` / ``scistudio.output`` are T-004's
module and are not on this branch yet. The fixture notebook therefore binds the
name ``scistudio`` in its first cell to a small object that reads and writes the
exchange folders through the ``SCISTUDIO_INPUTS_DIR`` / ``SCISTUDIO_OUTPUTS_DIR``
variables the Code Block runtime sets — which is exactly what the packaged-mode
helper will do once it lands. The dependency analysis reads
``scistudio.input(...)`` and ``scistudio.output(...)`` out of the source either
way, so the ports, the slice, and the refusals under test are the real ones.
When T-004 lands, the first cell of the fixture is deleted and nothing else
here changes.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

import scistudio
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.interactive import (
    INTERACTIVE_RESPONSE_KEY,
    InteractionPolicy,
    resolve_interaction_policy,
)
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.blocks.code.backends.notebook import (
    NOTEBOOK_CELL_SELECTION_KEY,
    NOTEBOOK_MODE_ENV_VAR,
    PACKAGED_NOTEBOOK_MODE,
    notebook_cell_selection,
    notebook_run_environment,
    select_notebook_cells,
)
from scistudio.blocks.code.config import CodeBlockConfigError
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.collection import Collection
from scistudio.core.types.text import Text
from scistudio.explore.notebook import (
    NotebookDocument,
    new_code_cell,
    new_notebook,
    read_notebook,
    write_notebook,
)
from scistudio.explore.packaging import (
    AskingPackagedNotebookBlock,
    CellMarks,
    PackagedNotebookBlock,
    PackagingProblemKind,
    PackagingRefusedError,
    block_file_stem,
    check_packaging,
    default_port_extension,
    notebook_at_commit,
    package_notebook,
    reopen_target,
    rewrite_load_to_input,
    slice_for_outputs,
)

pytestmark = pytest.mark.timeout(300)

COMMIT = "0" * 40
OTHER_COMMIT = "1" * 40


class PackagingTestSource(Block):
    """Upstream block that hands the packaged block the text its port reads.

    A packaged block reads its inputs from ports, so proving that a workflow
    runs one needs a node upstream of it. Defined here rather than in a shared
    fixture module because it exists only to feed this one workflow; the worker
    subprocess imports it back out of this module through its block spec, which
    is how every other in-repo fixture block reaches a worker.
    """

    name = "PackagingTestSource"
    description = "Emits a fixed Text for the packaged-block end-to-end test."
    input_ports = []  # noqa: RUF012 - Block declares these as plain class attributes
    output_ports = [OutputPort(name="text", accepted_types=[Text])]  # noqa: RUF012
    config_schema = {"type": "object", "properties": {"text": {"type": "string"}}}  # noqa: RUF012

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:
        return {"text": Collection([Text(content=str(config.get("text", "")))])}


# ---------------------------------------------------------------------------
# The fixture notebook
# ---------------------------------------------------------------------------

#: Binds ``scistudio`` to the packaged-mode file exchange (see the module
#: docstring). Every other cell is written exactly as it would be against the
#: real helpers.
SHIM_CELL = textwrap.dedent(
    """
    import os
    import pathlib


    class _Exchange:
        def input(self, name):
            folder = pathlib.Path(os.environ["SCISTUDIO_INPUTS_DIR"]) / name
            return sorted(folder.iterdir())[0].read_text(encoding="utf-8")

        def output(self, **values):
            root = pathlib.Path(os.environ["SCISTUDIO_OUTPUTS_DIR"])
            for name, value in values.items():
                folder = root / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / (name + ".txt")).write_text(str(value), encoding="utf-8")


    scistudio = _Exchange()
    """
).strip()

READ_CELL = 'raw = scistudio.input("raw")'
COMPUTE_CELL = "total = str(sum(int(line) for line in raw.split()))"
EXCLUDED_CELL = textwrap.dedent(
    """
    marker = pathlib.Path(os.environ["SCISTUDIO_EXCLUDED_MARKER"])
    marker.write_text("the excluded cell ran", encoding="utf-8")
    """
).strip()
DECLARE_CELL = "scistudio.output(total=total)"

KERNEL_METADATA = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "pygments_lexer": "ipython3"},
}


def fixture_notebook(*, kernel_name: str = "python3") -> NotebookDocument:
    """The notebook every end-to-end test packages.

    Five cells: the exchange shim, a port read, a computation, a side effect the
    declared-output slice does not need, and the output declaration. The fourth
    cell is what proves FR-040 — a packaged run must not perform its side effect.
    """
    metadata = json.loads(json.dumps(KERNEL_METADATA))
    metadata["kernelspec"]["name"] = kernel_name
    return new_notebook(
        [
            new_code_cell(SHIM_CELL, cell_id="shim"),
            new_code_cell(READ_CELL, cell_id="read"),
            new_code_cell(COMPUTE_CELL, cell_id="compute"),
            new_code_cell(EXCLUDED_CELL, cell_id="excluded"),
            new_code_cell(DECLARE_CELL, cell_id="declare"),
        ],
        metadata=metadata,
    )


BINDINGS = {"raw": "Text", "total": "Text"}


def run_as_session(document: NotebookDocument, *, raw: str, marker: Path) -> dict[str, str]:
    """Run every cell in written order, the way a session runs a notebook.

    Returns what the notebook declared through ``scistudio.output``. This is the
    "session's outputs" the packaged block's outputs are compared against: the
    same source, executed in the same order, with the helper resolving to the
    session's data instead of to the exchange folders.
    """
    declared: dict[str, str] = {}

    class _Session:
        def input(self, name: str) -> str:
            assert name == "raw"
            return raw

        def output(self, **values: Any) -> None:
            declared.update({key: str(value) for key, value in values.items()})

    namespace: dict[str, Any] = {}
    previous = os.environ.get("SCISTUDIO_EXCLUDED_MARKER")
    os.environ["SCISTUDIO_EXCLUDED_MARKER"] = str(marker)
    try:
        for cell in document.cells:
            if cell.cell_type != "code":
                continue
            if cell.cell_id == "shim":
                # The session supplies the helpers; the packaged run gets them
                # from the shim cell (see the module docstring).
                namespace["scistudio"] = _Session()
                exec(compile(SHIM_CELL.replace("scistudio = _Exchange()", ""), "<shim>", "exec"), namespace)
                namespace["scistudio"] = _Session()
                continue
            exec(compile(cell.source, f"<{cell.cell_id}>", "exec"), namespace)
    finally:
        if previous is None:
            os.environ.pop("SCISTUDIO_EXCLUDED_MARKER", None)
        else:
            os.environ["SCISTUDIO_EXCLUDED_MARKER"] = previous
    return declared


# ---------------------------------------------------------------------------
# The checks that refuse (FR-039)
# ---------------------------------------------------------------------------


def test_a_stale_cell_in_the_slice_refuses_and_names_it() -> None:
    """FR-039: a stale cell inside the declared-output slice refuses, by name."""
    document = fixture_notebook()

    plan = check_packaging(document, marks=CellMarks(stale=["compute"]), bindings=BINDINGS)

    assert not plan.is_packageable
    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.STALE_CELL]
    assert problem.cell_ids == ("compute",)
    assert "compute" in problem.message


def test_a_never_run_cell_in_the_slice_refuses_and_names_it() -> None:
    """FR-039: a never-run cell inside the slice refuses, by name."""
    plan = check_packaging(fixture_notebook(), marks=CellMarks(never_run=["read"]), bindings=BINDINGS)

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.NEVER_RUN_CELL]
    assert problem.cell_ids == ("read",)
    assert "read" in problem.message


def test_an_out_of_order_cell_in_the_slice_refuses_and_names_it() -> None:
    """FR-039: a cell that ran out of written order inside the slice refuses, by name."""
    plan = check_packaging(
        fixture_notebook(),
        marks=CellMarks(out_of_order=["compute", "read"]),
        bindings=BINDINGS,
    )

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.OUT_OF_ORDER_CELL]
    assert problem.cell_ids == ("read", "compute"), "cells are named in written order"


def test_a_mark_outside_the_slice_does_not_refuse() -> None:
    """FR-039 is about the slice: a stale cell the outputs do not depend on is irrelevant.

    The excluded cell is stale, never run, and out of order all at once, and the
    notebook still packages — because nothing the declared output depends on is
    marked. Without this the refusal would be "any mark anywhere", which would
    make a notebook with one abandoned experiment cell unpackageable forever.
    """
    plan = check_packaging(
        fixture_notebook(),
        marks=CellMarks(stale=["excluded"], never_run=["excluded"], out_of_order=["excluded"]),
        bindings=BINDINGS,
    )

    assert plan.is_packageable, plan.problems
    assert "excluded" not in plan.cells


def test_a_notebook_with_no_declared_output_refuses() -> None:
    """FR-039: a notebook that declares no output has nothing to package."""
    document = new_notebook([new_code_cell("import scistudio\ntotal = 1", cell_id="a")], metadata=KERNEL_METADATA)

    plan = check_packaging(document, bindings={"total": "Text"})

    (problem,) = plan.problems
    assert problem.kind is PackagingProblemKind.NO_DECLARED_OUTPUT
    assert plan.cells == ()


def test_an_unresolved_read_in_the_slice_refuses_and_names_the_cell_and_the_name() -> None:
    """FR-039: a slice that would raise NameError refuses before it becomes a block."""
    document = new_notebook(
        [
            new_code_cell("import scistudio\ntotal = missing_name + 1", cell_id="a"),
            new_code_cell("scistudio.output(total=total)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(document, bindings={"total": "Text"})

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.UNRESOLVED_READ]
    assert "a" in problem.cell_ids
    assert "missing_name" in problem.names
    assert "missing_name" in problem.message


def test_a_slice_that_calls_an_interactive_block_refuses_and_names_the_cell() -> None:
    """FR-039 with FR-050: an interactive call cannot run unattended inside a block."""
    document = new_notebook(
        [
            new_code_cell('import blocks\nimport scistudio\ntotal = blocks.run("PickOne", data=1)', cell_id="a"),
            new_code_cell("scistudio.output(total=total)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(
        document,
        bindings={"total": "Text"},
        is_interactive=lambda block_id: block_id == "PickOne",
    )

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.INTERACTIVE_BLOCK_CALL]
    assert problem.cell_ids == ("a",)
    assert "PickOne" in problem.message


def test_a_slice_calling_a_non_interactive_block_is_packageable() -> None:
    """The refusal is about interactive calls, not about block calls."""
    document = new_notebook(
        [
            new_code_cell('import blocks\nimport scistudio\ntotal = blocks.run("Smooth", data=1)', cell_id="a"),
            new_code_cell("scistudio.output(total=total)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(document, bindings={"total": "Text"}, is_interactive=lambda _block_id: False)

    assert plan.is_packageable, plan.problems


def test_a_block_call_that_cannot_be_named_refuses() -> None:
    """FR-039: an identifier that is not a literal cannot be shown to be non-interactive."""
    document = new_notebook(
        [
            new_code_cell(
                "import blocks\nimport scistudio\nchosen = 'PickOne'\ntotal = blocks.run(chosen, data=1)", cell_id="a"
            ),
            new_code_cell("scistudio.output(total=total)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(document, bindings={"total": "Text"}, is_interactive=lambda _block_id: False)

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.UNKNOWN_BLOCK_CALL]
    assert problem.cell_ids == ("a",)


def test_every_refusal_is_reported_not_just_the_first() -> None:
    """A person fixing a notebook wants the whole list, not one problem at a time."""
    plan = check_packaging(
        fixture_notebook(),
        marks=CellMarks(stale=["compute"], never_run=["read"]),
        bindings=BINDINGS,
    )

    kinds = {problem.kind for problem in plan.problems}
    assert PackagingProblemKind.STALE_CELL in kinds
    assert PackagingProblemKind.NEVER_RUN_CELL in kinds


def test_a_port_with_nothing_bound_to_it_refuses(tmp_path: Path) -> None:
    """FR-038: a port's type is the type bound at packaging; with nothing bound there is none."""
    plan = check_packaging(fixture_notebook(), bindings={"raw": "Text"})

    (problem,) = [entry for entry in plan.problems if entry.kind is PackagingProblemKind.UNTYPED_PORT]
    assert "total" in problem.message

    with pytest.raises(PackagingRefusedError):
        package_notebook(
            fixture_notebook(),
            project_dir=tmp_path,
            block_name="Row Total",
            notebook_commit=COMMIT,
            bindings={"raw": "Text"},
        )


def test_a_refused_notebook_writes_nothing(tmp_path: Path) -> None:
    """A refusal leaves the project exactly as it was."""
    with pytest.raises(PackagingRefusedError) as refusal:
        package_notebook(
            fixture_notebook(),
            project_dir=tmp_path,
            block_name="Row Total",
            notebook_commit=COMMIT,
            marks=CellMarks(stale=["compute"]),
            bindings=BINDINGS,
        )

    assert [problem.kind for problem in refusal.value.problems] == [PackagingProblemKind.STALE_CELL]
    assert not (tmp_path / "blocks").exists()


# ---------------------------------------------------------------------------
# The slice and the ports (FR-038, FR-040)
# ---------------------------------------------------------------------------


def test_the_slice_is_the_backward_slice_of_the_declared_outputs() -> None:
    """FR-040: the cells the packaged block runs, and only those."""
    assert slice_for_outputs(fixture_notebook()) == ("shim", "read", "compute", "declare")


def test_ports_come_from_the_declarations_and_are_typed_from_the_bindings() -> None:
    """FR-038: names from the analysis, types from the kernel, extensions from materialisation."""
    plan = check_packaging(fixture_notebook(), bindings=BINDINGS)

    (input_port,) = plan.inputs
    (output_port,) = plan.outputs
    assert (input_port.name, input_port.data_type, input_port.extension) == ("raw", "Text", ".txt")
    assert (output_port.name, output_port.data_type, output_port.extension) == ("total", "Text", ".txt")


def test_a_positional_output_declaration_names_its_own_port() -> None:
    """``scistudio.output(total)`` declares a port called ``total``."""
    document = new_notebook(
        [
            new_code_cell("import scistudio\ntotal = '1'", cell_id="a"),
            new_code_cell("scistudio.output(total)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(document, bindings={"total": "Text"})

    assert [port.name for port in plan.outputs] == ["total"]


def test_a_keyword_output_declaration_types_from_the_bound_variable() -> None:
    """``scistudio.output(result=frame)`` is a port ``result`` carrying ``frame``'s type."""
    document = new_notebook(
        [
            new_code_cell("import scistudio\nframe = 1", cell_id="a"),
            new_code_cell("scistudio.output(result=frame)", cell_id="b"),
        ],
        metadata=KERNEL_METADATA,
    )

    plan = check_packaging(document, bindings={"frame": "DataFrame"})

    (port,) = plan.outputs
    assert (port.name, port.data_type, port.bound_name) == ("result", "DataFrame", "frame")


def test_default_port_extension_answers_for_the_core_types() -> None:
    """FR-038: the extension is the default the materialisation layer assigns."""
    assert default_port_extension("DataFrame") == ".csv"
    assert default_port_extension("Array") == ".npy"
    with pytest.raises(LookupError):
        default_port_extension("NoSuchType")


def test_a_file_opened_sessions_load_line_becomes_a_port_read() -> None:
    """FR-038: a session opened from a file reads a port once it is packaged."""
    rewritten = rewrite_load_to_input('spectra = scistudio.load("data/raw.csv")', {"spectra": "spectra"})

    assert rewritten.strip() == 'spectra = scistudio.input("spectra")'


def test_the_load_rewrite_leaves_a_variable_it_was_not_given_alone() -> None:
    source = 'other = scistudio.load("data/raw.csv")'

    assert rewrite_load_to_input(source, {"spectra": "spectra"}) == source


# ---------------------------------------------------------------------------
# What packaging writes (FR-037, FR-041, FR-042, FR-043)
# ---------------------------------------------------------------------------


def package_fixture(tmp_path: Path, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "project_dir": tmp_path,
        "block_name": "Row Total",
        "notebook_commit": COMMIT,
        "bindings": BINDINGS,
    }
    document = overrides.pop("document", None) or fixture_notebook()
    kwargs.update(overrides)
    return package_notebook(document, **kwargs)


def test_packaging_writes_a_declaration_and_a_copy_directly_in_the_blocks_directory(tmp_path: Path) -> None:
    """FR-037: both files sit in the blocks directory, because the tier-1 scan is not recursive."""
    packaged = package_fixture(tmp_path)

    assert packaged.declaration_path == tmp_path / "blocks" / "row_total.py"
    assert packaged.notebook_path == tmp_path / "blocks" / "row_total.ipynb"
    assert packaged.declaration_path.parent == tmp_path / "blocks"
    source = packaged.declaration_path.read_text(encoding="utf-8")
    assert "class RowTotal(PackagedNotebookBlock):" in source
    assert not packaged.declaration_path.name.startswith("_"), "the tier-1 scan skips files starting with _"


def test_the_declaration_records_the_notebook_commit(tmp_path: Path) -> None:
    """FR-041: the generated block's version is the commit it was packaged from."""
    packaged = package_fixture(tmp_path)

    source = packaged.declaration_path.read_text(encoding="utf-8")
    assert f"version: ClassVar[str] = {COMMIT!r}" in source
    assert f"notebook_commit: ClassVar[str] = {COMMIT!r}" in source
    assert packaged.notebook_commit == COMMIT


def test_packaging_without_a_commit_is_refused(tmp_path: Path) -> None:
    """FR-041: there is no packaged block without the commit it came from."""
    with pytest.raises(ValueError, match="notebook commit"):
        package_fixture(tmp_path, notebook_commit="  ")


def test_packaging_leaves_the_exploration_notebook_untouched(tmp_path: Path) -> None:
    """FR-043: nothing outside the blocks directory is written or changed."""
    explore_dir = tmp_path / "explore"
    explore_dir.mkdir()
    original = explore_dir / "session.ipynb"
    write_notebook(original, fixture_notebook())
    before = original.read_bytes()

    document = read_notebook(original)
    package_fixture(tmp_path, document=document, file_ports={"raw": "raw"})

    assert original.read_bytes() == before
    assert sorted(path.name for path in explore_dir.iterdir()) == ["session.ipynb"]


def test_the_copy_holds_the_whole_notebook_not_the_slice(tmp_path: Path) -> None:
    """FR-042 needs the whole notebook: reopening shows what the person wrote.

    Running only the slice is the cell selection's, not the copy's — which is
    why the copy keeps the excluded cell that the packaged run must not execute.
    """
    packaged = package_fixture(tmp_path)

    copy = read_notebook(packaged.notebook_path)
    assert [cell.cell_id for cell in copy.cells] == ["shim", "read", "compute", "excluded", "declare"]
    assert packaged.cells == ("shim", "read", "compute", "declare")


def test_repackaging_replaces_both_files_in_place(tmp_path: Path) -> None:
    """FR-042: packaging again from the reopened session replaces the copy and the declaration."""
    first = package_fixture(tmp_path)

    changed = fixture_notebook()
    changed.set_cell_source("compute", "total = str(sum(int(line) for line in raw.split()) * 2)")
    second = package_fixture(tmp_path, document=changed, notebook_commit=OTHER_COMMIT)

    assert second.declaration_path == first.declaration_path
    assert second.notebook_path == first.notebook_path
    assert sorted(path.name for path in (tmp_path / "blocks").iterdir()) == ["row_total.ipynb", "row_total.py"]
    assert "* 2" in read_notebook(second.notebook_path).cell("compute").source
    assert f"notebook_commit: ClassVar[str] = {OTHER_COMMIT!r}" in second.declaration_path.read_text(encoding="utf-8")


def test_reopening_from_the_node_names_the_copy_and_the_commit(tmp_path: Path) -> None:
    """FR-042: a packaged block's node opens a session on the block's copy, not the original."""
    packaged = package_fixture(tmp_path)

    target = reopen_target(tmp_path, "Row Total")

    assert target.notebook_path == packaged.notebook_path
    assert target.declaration_path == packaged.declaration_path
    assert target.notebook_commit == COMMIT


def test_reopening_a_block_that_was_never_packaged_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Row Total"):
        reopen_target(tmp_path, "Row Total")


def test_a_file_opened_session_packages_its_load_line_as_a_port(tmp_path: Path) -> None:
    """FR-038: the copy reads a port where the session read a file."""
    document = new_notebook(
        [
            new_code_cell('import scistudio\n\nspectra = scistudio.load("data/raw.csv")', cell_id="load"),
            new_code_cell("scistudio.output(spectra=spectra)", cell_id="declare"),
        ],
        metadata=KERNEL_METADATA,
    )

    packaged = package_notebook(
        document,
        project_dir=tmp_path,
        block_name="From File",
        notebook_commit=COMMIT,
        bindings={"spectra": "DataFrame"},
        file_ports={"spectra": "spectra"},
    )

    copy = read_notebook(packaged.notebook_path)
    assert copy.cell("load").source.splitlines()[-1] == 'spectra = scistudio.input("spectra")'
    assert "scistudio.load" not in copy.cell("load").source
    assert [port.name for port in packaged.inputs] == ["spectra"]
    assert 'scistudio.load("data/raw.csv")' in document.cell("load").source


# ---------------------------------------------------------------------------
# Cell selection in the notebook backend (FR-040)
# ---------------------------------------------------------------------------


def test_the_selection_keeps_the_notebooks_written_order_not_the_callers() -> None:
    """FR-040: a selection cannot reorder a notebook."""
    document = json.loads(fixture_notebook().to_json())

    sliced = select_notebook_cells(document, ["declare", "shim", "compute", "read"])

    assert [cell["id"] for cell in sliced["cells"]] == ["shim", "read", "compute", "declare"]
    assert sliced["metadata"] == document["metadata"], "the kernelspec has to survive the slice"


def test_a_selection_naming_a_missing_cell_fails_loudly() -> None:
    """A selection that silently lost a cell would run a different program than was packaged."""
    document = json.loads(fixture_notebook().to_json())

    with pytest.raises(CodeBlockConfigError, match="gone"):
        select_notebook_cells(document, ["shim", "gone"])


def test_an_absent_selection_means_the_whole_notebook() -> None:
    """Every Code Block written before packaging existed is unaffected."""
    assert notebook_cell_selection({}) is None
    assert notebook_cell_selection({"interpreter_path": "x"}) is None


def test_an_empty_selection_is_rejected_rather_than_widened() -> None:
    """ "Run no cells" is never what a packaged block wants, and never what "all cells" means."""
    with pytest.raises(CodeBlockConfigError, match="empty"):
        notebook_cell_selection({NOTEBOOK_CELL_SELECTION_KEY: []})


def test_a_malformed_selection_is_rejected() -> None:
    with pytest.raises(CodeBlockConfigError):
        notebook_cell_selection({NOTEBOOK_CELL_SELECTION_KEY: "shim"})
    with pytest.raises(CodeBlockConfigError):
        notebook_cell_selection({NOTEBOOK_CELL_SELECTION_KEY: ["shim", 7]})


def test_the_backend_sets_the_exchange_variables_and_the_packaged_mode(tmp_path: Path) -> None:
    """FR-040's packaged-mode environment.

    A notebook locates its declared ports through the ``SCISTUDIO_*`` variables
    every other Code Block script gets, and a run that carries a cell selection
    is additionally marked packaged so the notebook helpers pick their
    file-exchange backend over the session one.
    """
    from scistudio.blocks.code.code_block import CodeBlockRuntimeContext
    from scistudio.blocks.code.config import CodeBlockConfig

    notebook = tmp_path / "analysis.ipynb"
    notebook.write_text(fixture_notebook().to_json(), encoding="utf-8")

    def _resolve(environment: dict[str, Any]) -> dict[str, str]:
        context = CodeBlockRuntimeContext(
            config=CodeBlockConfig(script_path="analysis.ipynb"),
            script_path=notebook,
            project_dir=tmp_path,
            exchange_dir=tmp_path / "exchange" / "run",
            environment_config=environment,
        )
        return notebook_run_environment(context)

    plain = _resolve({})
    assert plain["SCISTUDIO_INPUTS_DIR"].endswith("inputs")
    assert plain["SCISTUDIO_OUTPUTS_DIR"].endswith("outputs")
    assert NOTEBOOK_MODE_ENV_VAR not in plain, "a Code Block with no selection is not a packaged run"

    packaged = _resolve({NOTEBOOK_CELL_SELECTION_KEY: ["shim"]})
    assert packaged[NOTEBOOK_MODE_ENV_VAR] == PACKAGED_NOTEBOOK_MODE


def test_the_file_stem_is_scannable(tmp_path: Path) -> None:
    """The tier-1 scan skips files whose name starts with an underscore."""
    assert block_file_stem("Row Total") == "row_total"
    assert not block_file_stem("__weird name__").startswith("_")
    assert block_file_stem("2024 results").startswith("notebook_")


def test_a_generated_block_is_a_packaged_notebook_block(tmp_path: Path) -> None:
    """The declaration is a declaration: the behaviour lives in the shared base."""
    packaged = package_fixture(tmp_path)

    cls = load_declared_block(packaged.declaration_path)

    assert issubclass(cls, PackagedNotebookBlock)
    assert cls.notebook_filename == "row_total.ipynb"
    assert cls.slice_cells == ("shim", "read", "compute", "declare")


def test_the_packaged_block_configures_the_selection_and_the_packaged_mode(tmp_path: Path) -> None:
    """FR-040: the declaration carries the slice, and the run is marked packaged."""
    packaged = package_fixture(tmp_path)
    block = load_declared_block(packaged.declaration_path)()

    config = block.packaged_config({"project_dir": str(tmp_path)})

    assert config["script_path"] == "blocks/row_total.ipynb"
    assert config["environment"][NOTEBOOK_CELL_SELECTION_KEY] == ["shim", "read", "compute", "declare"]
    assert [port["name"] for port in config["inputs"]] == ["raw"]
    assert [port["name"] for port in config["outputs"]] == ["total"]


# ---------------------------------------------------------------------------
# The ask pause (FR-046, FR-047)
# ---------------------------------------------------------------------------


def test_a_packaged_block_defaults_to_replay(tmp_path: Path) -> None:
    """FR-044: a packaged notebook block replays; it does not pause on new data."""
    packaged = package_fixture(tmp_path)
    block = load_declared_block(packaged.declaration_path)()

    assert resolve_interaction_policy(block, {}) is InteractionPolicy.REPLAY
    assert not isinstance(block, AskingPackagedNotebookBlock)
    assert getattr(type(block), "execution_mode", None) is not ExecutionMode.INTERACTIVE


def test_packaging_to_ask_generates_an_interactive_block(tmp_path: Path) -> None:
    """FR-046: set to ask, the packaged block is an interactive block."""
    packaged = package_fixture(tmp_path, on_new_input="ask")
    cls = load_declared_block(packaged.declaration_path)

    assert issubclass(cls, AskingPackagedNotebookBlock)
    assert cls.execution_mode is ExecutionMode.INTERACTIVE
    assert cls.interactive_panel.panel_id == "core.explore.session"
    assert resolve_interaction_policy(cls(), {}) is InteractionPolicy.ASK


def test_the_ask_prompt_names_the_notebook_the_commit_and_the_runs_inputs(tmp_path: Path) -> None:
    """FR-046: enough for the Explore tab to open a session over this run's inputs."""
    from scistudio.core.types.collection import Collection
    from scistudio.core.types.text import Text

    packaged = package_fixture(tmp_path, on_new_input="ask")
    block = load_declared_block(packaged.declaration_path)()

    payload = block.prepare_prompt({"raw": Collection([Text(content="1 2 3")])}, {})

    assert payload["notebook"] == "blocks/row_total.ipynb"
    assert payload["notebook_commit"] == COMMIT
    assert payload["block_name"] == "Row Total"
    assert list(payload["inputs"]) == ["raw"]
    assert json.dumps(payload), "the panel payload has to be JSON-safe"


def test_an_unchanged_input_signature_replays_the_remembered_commit(tmp_path: Path) -> None:
    """FR-046: under ask, a matching signature replays and does not pause."""
    packaged = package_fixture(tmp_path, on_new_input="ask")
    block = load_declared_block(packaged.declaration_path)()
    decision = {"notebook_commit": COMMIT}

    assert block.remap_saved_decision(decision, {"raw": ["a"]}, {"raw": ["a"]}) == decision
    assert block.remap_saved_decision(decision, {"raw": ["a"]}, {"raw": ["b"]}) is None


def test_a_decision_naming_the_packaged_commit_runs_the_packaged_copy(tmp_path: Path) -> None:
    """FR-047: confirming the commit it was packaged from changes nothing about the run."""
    packaged = package_fixture(tmp_path, on_new_input="ask")
    block = load_declared_block(packaged.declaration_path)()

    script, cells = block.resolve_script(
        tmp_path,
        {INTERACTIVE_RESPONSE_KEY: {"notebook_commit": COMMIT}},
    )

    assert script == "blocks/row_total.ipynb"
    assert cells == ("shim", "read", "compute", "declare")


def test_a_decision_naming_another_commit_runs_that_commits_slice(tmp_path: Path) -> None:
    """FR-047: the compute phase executes the slice of the commit the person confirmed."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not on the path")

    packaged = package_fixture(tmp_path)
    _init_repo(tmp_path)
    first = _commit_all(tmp_path, "packaged")

    # A second notebook version whose slice is one cell shorter: the computation
    # moves into the declaring cell, so ``compute`` drops out of the slice.
    changed = read_notebook(packaged.notebook_path)
    changed.set_cell_source("compute", "unused = 1")
    changed.set_cell_source("declare", "scistudio.output(total=str(sum(int(x) for x in raw.split())))")
    write_notebook(packaged.notebook_path, changed)
    second = _commit_all(tmp_path, "changed")
    assert first != second

    block = load_declared_block(packaged.declaration_path)()
    script, cells = block.resolve_script(tmp_path, {INTERACTIVE_RESPONSE_KEY: {"notebook_commit": second}})

    assert script.startswith("blocks/.packaged/"), "a materialised notebook must not be scanned as a block"
    assert cells == ("shim", "read", "declare")
    assert (tmp_path / script).exists()


def test_notebook_at_commit_reads_the_version_that_was_committed(tmp_path: Path) -> None:
    """FR-047's read: the blob at a commit, without touching the working tree."""
    if shutil.which("git") is None:
        pytest.skip("git is not on the path")

    packaged = package_fixture(tmp_path)
    _init_repo(tmp_path)
    first = _commit_all(tmp_path, "packaged")
    changed = read_notebook(packaged.notebook_path)
    changed.set_cell_source("compute", "total = 'changed'")
    write_notebook(packaged.notebook_path, changed)
    _commit_all(tmp_path, "changed")

    document = notebook_at_commit(tmp_path, "blocks/row_total.ipynb", first)

    assert document.cell("compute").source == COMPUTE_CELL
    assert read_notebook(packaged.notebook_path).cell("compute").source == "total = 'changed'"
    with pytest.raises(FileNotFoundError):
        notebook_at_commit(tmp_path, "blocks/missing.ipynb", first)


# ---------------------------------------------------------------------------
# End to end: registry discovery, a workflow run, and the slice (FR-037, FR-040)
# ---------------------------------------------------------------------------


def test_the_generated_declaration_is_discovered_by_the_registry(tmp_path: Path) -> None:
    """FR-037: the tier-1 scan finds the generated block with its ports."""
    packaged = package_fixture(tmp_path)

    registry = BlockRegistry()
    registry.add_scan_dir(tmp_path / "blocks")
    registry.scan()

    spec = registry.get_spec("Row Total")
    assert spec is not None, sorted(registry.all_specs())
    assert spec.source == "tier1"
    assert [_port_name(port) for port in spec.input_ports] == ["raw"]
    assert [_port_name(port) for port in spec.output_ports] == ["total"]
    assert Path(spec.file_path or "") == packaged.declaration_path


@pytest.mark.timeout(600)
def test_a_workflow_runs_the_packaged_block_and_reproduces_the_session(tmp_path: Path) -> None:
    """The acceptance bar (FR-037, FR-040).

    A fixture notebook is packaged, the registry discovers the declaration, the
    real scheduler runs a workflow over it, and the block's output equals what
    the same notebook produces when a session runs it. The excluded cell's side
    effect proves the packaged run executed the slice and not the notebook.
    """
    nbconvert = _nbconvert_executable()
    if nbconvert is None:
        pytest.skip("Jupyter nbconvert is not installed in this environment.")

    from scistudio.core.lineage.record import RunRecord
    from scistudio.core.lineage.store import LineageStore
    from scistudio.engine.events import EventBus
    from scistudio.engine.lineage_recorder import LineageRecorder
    from scistudio.engine.runners.local import LocalRunner
    from scistudio.engine.runners.process_handle import ProcessRegistry
    from scistudio.engine.scheduler import DAGScheduler
    from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

    raw_text = "1\n2\n3\n4"
    session_marker = tmp_path / "session-marker.txt"
    session_outputs = run_as_session(fixture_notebook(), raw=raw_text, marker=session_marker)
    assert session_outputs == {"total": "10"}
    assert session_marker.exists(), "the session runs every cell, including the excluded one"

    document = fixture_notebook(kernel_name=_kernel_name())
    packaged = package_fixture(tmp_path, document=document)
    assert packaged.cells == ("shim", "read", "compute", "declare"), "the excluded cell is not in the slice"

    packaged_marker = tmp_path / "packaged-marker.txt"
    registry = BlockRegistry()
    registry.add_scan_dir(tmp_path / "blocks")
    registry.scan()
    assert registry.get_spec("Row Total") is not None

    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(id="source", block_type="PackagingTestSource", config={"params": {"text": raw_text}}),
            NodeDef(
                id="packaged",
                block_type="Row Total",
                config={
                    "params": {
                        "interpreter_mode": "existing",
                        "interpreter_path": nbconvert,
                        "environment_variables": {"SCISTUDIO_EXCLUDED_MARKER": str(packaged_marker)},
                    }
                },
            ),
        ],
        edges=[EdgeDef(source="source:text", target="packaged:raw")],
    )

    _register_source_block(registry)
    bus = EventBus()
    process_registry = ProcessRegistry()
    # A real lineage store and recorder, so FR-054's claim is checked against
    # the ``block_executions`` row a run actually writes rather than against
    # the resolver that computes it.
    store = LineageStore(":memory:")
    run_id = "run-packaged-e2e"
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow.id,
            workflow_yaml_snapshot="",
            started_at="2026-09-04T00:00:00",
            status="running",
            environment_snapshot={},
        )
    )
    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=bus,
        resource_manager=_AllowAll(),
        process_registry=process_registry,
        runner=LocalRunner(event_bus=bus, registry=process_registry),
        registry=registry,
        project_dir=str(tmp_path),
        lineage_recorder=LineageRecorder(bus, lineage_store=store, run_id=run_id),
    )
    try:
        asyncio.run(asyncio.wait_for(scheduler.execute(), timeout=480))
    finally:
        scheduler.dispose()

    assert scheduler._block_states.get("source") == BlockState.DONE, str(scheduler._block_states)
    assert scheduler._block_states["packaged"] == BlockState.DONE, _failure_detail(tmp_path)

    # The worker returns its outputs as storage references, so the comparison
    # is against what the packaged block actually persisted for the port.
    (item,) = _reference_items(scheduler._block_outputs["packaged"]["total"])
    assert item["metadata"]["type_chain"][-1] == "Text", item["metadata"]
    assert Path(item["path"]).read_text(encoding="utf-8") == session_outputs["total"]

    assert not packaged_marker.exists(), (
        "the packaged run executed the excluded cell, so it ran the notebook rather than the slice"
    )

    # FR-054: the run is an ordinary run whose block version is the notebook
    # commit, which is how the step points back at the session it came from.
    rows = {row["block_id"]: row for row in store.list_block_executions(run_id)}
    assert set(rows) == {"source", "packaged"}, rows
    assert rows["packaged"]["block_version"] == COMMIT, (
        "the run recorded the distribution version, so nothing connects it to the notebook"
    )
    # And the upstream ordinary block is untouched by that rule.
    assert rows["source"]["block_version"] == scistudio.__version__
    store.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AllowAll:
    """ResourceManager stub that always permits dispatch."""

    def can_dispatch(self, *_args: object, **_kwargs: object) -> bool:
        return True


def load_declared_block(declaration_path: Path) -> Any:
    """Import a generated declaration the way the tier-1 scan does, and return its class."""
    import importlib.util

    from scistudio.blocks.base.block import Block

    spec = importlib.util.spec_from_file_location(f"_packaged_{declaration_path.stem}", declaration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in vars(module).values():
        if isinstance(attr, type) and issubclass(attr, Block) and attr.__module__ == module.__name__:
            return attr
    raise AssertionError(f"{declaration_path} defines no block class")


def _port_name(port: Any) -> str:
    """Read a port name whether the spec carries port objects or their wire form."""
    return str(port["name"] if isinstance(port, dict) else port.name)


def _reference_items(port_output: Any) -> list[dict[str, Any]]:
    """Return the storage references a worker-produced port output carries.

    A block that ran in a worker subprocess hands its outputs back as
    references rather than as live objects, so this is where the packaged
    block's real, persisted output is found.
    """
    if isinstance(port_output, dict) and port_output.get("_collection"):
        return list(port_output.get("items") or [])
    if isinstance(port_output, dict):
        return [port_output]
    return [item if isinstance(item, dict) else {"value": item} for item in port_output]


def _nbconvert_executable() -> str | None:
    configured = os.environ.get("SCISTUDIO_TEST_NBCONVERT")
    if configured and Path(configured).exists():
        return configured
    return shutil.which("jupyter-nbconvert")


def _kernel_name() -> str:
    return os.environ.get("SCISTUDIO_TEST_KERNEL", "python3")


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


def _commit_all(path: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True, capture_output=True)
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _failure_detail(project_dir: Path) -> str:
    """Quote the script's captured stderr so a failing notebook run is diagnosable."""
    logs = sorted(project_dir.glob("exchange/**/logs/stderr.log"))
    if not logs:
        return "no exchange logs were written"
    return logs[-1].read_text(encoding="utf-8")[-4000:]


def _register_source_block(registry: BlockRegistry) -> None:
    """Register the upstream block whose output feeds the packaged block's port."""
    from scistudio.blocks.registry._spec import _spec_from_class

    registry._register_spec(_spec_from_class(PackagingTestSource, source="builtin"))
