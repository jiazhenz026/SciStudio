"""The notebook store loses nothing (ADR-054 spec 3, T-005).

The store's whole job is a lossless round trip, so a test that round-trips a
notebook the store itself produced proves almost nothing: the store would
agree with its own idea of a notebook even if that idea threw half the file
away. Every round-trip test here therefore starts from a notebook **written
by something else**:

* :data:`_JUPYTERLAB_NOTEBOOK` is serialised by :func:`_nbformat_bytes`, an
  independent re-implementation of ``nbformat.writes``' documented recipe, so
  the expected bytes never come from the code under test.
* :data:`_HAND_EDITED_NOTEBOOK_TEXT` is a verbatim file: two-space indent,
  unsorted keys, a top-level key nbformat has never heard of. It is what a
  merge tool, a script, or a person with an editor leaves behind.

Both carry keys the store does not model, at every level the format has one —
notebook metadata, cell metadata, inside the ``scistudio`` namespace, inside
outputs, and on the cell itself.

Requirements exercised: FR-005 (external reload), FR-027 (outputs kept on
disk), FR-032 (analysis records preserved; stripping does not disturb the
file), FR-033 (unrecognised metadata keys survive; the enabled flag),
assumption A-012 (the store's own write is not an external edit).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from scistudio.explore.notebook import (
    ANALYSIS_METADATA_KEY,
    ENABLED_METADATA_KEY,
    NotebookDocument,
    NotebookStore,
    NotebookStoreError,
    new_code_cell,
    new_markdown_cell,
    new_notebook,
    read_notebook,
    strip_outputs,
    write_notebook,
)

# ---------------------------------------------------------------------------
# Fixtures written by something other than the code under test
# ---------------------------------------------------------------------------


def _nbformat_bytes(document: dict[str, Any]) -> bytes:
    """Serialise *document* the way ``nbformat.writes`` does.

    Re-implemented here on purpose. If the store's writer drifts from
    Jupyter's, the byte-identity tests must fail — which they cannot do if the
    expected bytes come from the store.
    """
    text = json.dumps(document, indent=1, sort_keys=True, separators=(",", ": "), ensure_ascii=False)
    return (text + "\n").encode("utf-8")


#: A session notebook as JupyterLab would leave it, carrying every kind of
#: baggage the store must not touch: a vendor key on the cell itself, vendor
#: keys in cell metadata, an unknown key inside the ``scistudio`` namespace
#: beside the analysis record, unknown keys inside an output, unknown
#: notebook-level metadata, and an unknown top-level key.
_JUPYTERLAB_NOTEBOOK: dict[str, Any] = {
    "cells": [
        {
            "cell_type": "markdown",
            "id": "intro-cell",
            "metadata": {
                "editable": True,
                "jp-MarkdownHeadingCollapsed": True,
                "tags": ["intro"],
                "vendor-x": {"pinned": True},
            },
            "source": ["# Peak fitting\n", "\n", "Notes on the run — 峰位 and émojis 🧪.\n"],
        },
        {
            "cell_type": "code",
            "deepnote_cell_type": "code",
            "execution_count": 3,
            "id": "load-cell",
            "metadata": {
                "collapsed": False,
                "execution": {"iopub.status.busy": "2026-09-02T10:00:00.000000Z"},
                "jupyter": {"outputs_hidden": False, "source_hidden": False},
                ANALYSIS_METADATA_KEY: {
                    "analysis_version": 1,
                    "assigned": ["spectrum"],
                    "flags": ["star_import"],
                    "observation": {
                        "changed": ["spectrum"],
                        "source_hash": "0f1e2d3c",
                        "unobservable": [],
                    },
                    "read": ["scistudio"],
                    "source_hash": "0f1e2d3c",
                    "unrecognised_future_key": {"written_by": "a later SciStudio", "keep": [1, 2, 3]},
                },
                "vendor-y": "keep me",
            },
            "outputs": [
                {
                    "name": "stdout",
                    "output_type": "stream",
                    "text": ["loaded 2048 points\n"],
                },
                {
                    "data": {
                        "image/png": "iVBORw0KGgoAAAANSUhEUg==",
                        "text/plain": ["<Figure size 640x480>"],
                    },
                    "execution_count": 3,
                    "metadata": {"image/png": {"height": 480, "width": 640}, "needs_background": "light"},
                    "output_type": "execute_result",
                },
                {
                    "ename": "ValueError",
                    "evalue": "bad peak",
                    "output_type": "error",
                    "traceback": ["Traceback (most recent call last):", "ValueError: bad peak"],
                },
            ],
            "source": ["import scistudio\n", "\n", "spectrum = scistudio.load(scistudio.input('spectrum'))\n"],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "id": "fit-cell",
            "metadata": {
                ANALYSIS_METADATA_KEY: {
                    ENABLED_METADATA_KEY: False,
                    "assigned": ["fit"],
                    "read": ["spectrum"],
                    "source_hash": "abcd1234",
                }
            },
            "outputs": [],
            "source": "fit = spectrum.fit()\n",
        },
        {
            "cell_type": "raw",
            "id": "raw-cell",
            "metadata": {"format": "text/restructuredtext", "raw_mimetype": "text/restructuredtext"},
            "source": [".. note:: kept verbatim\n"],
        },
    ],
    "metadata": {
        "authors": [{"name": "A Scientist"}],
        "celltoolbar": "Tags",
        "kernelspec": {"display_name": "SciStudio", "language": "python", "name": "scistudio"},
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.11.9",
        },
        ANALYSIS_METADATA_KEY: {"analysis_version": 1, "session_id": "s-9f2c41", "vendor_note": "kept"},
        "widgets": {"application/vnd.jupyter.widget-state+json": {"state": {}, "version_major": 2}},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
    "unknown_top_level_key": {"written_by": "some other tool"},
}


#: The same content a person or a merge tool would leave: two-space indent,
#: keys in the order they were typed rather than sorted, a top-level key the
#: schema does not define, and a cell with no ``id`` (nbformat 4.4 and older).
_HAND_EDITED_NOTEBOOK_TEXT = """{
  "nbformat": 4,
  "nbformat_minor": 4,
  "x-merged-by": "some-merge-tool",
  "metadata": {
    "kernelspec": {"name": "scistudio", "display_name": "SciStudio"},
    "x-unknown": [1, 2, {"deep": "value"}]
  },
  "cells": [
    {
      "source": "a = 1\\n",
      "cell_type": "code",
      "outputs": [],
      "execution_count": null,
      "metadata": {"x-cell": "kept"}
    },
    {
      "cell_type": "markdown",
      "metadata": {},
      "source": ["done\\n"]
    }
  ]
}
"""


@pytest.fixture
def notebook_path(tmp_path: Path) -> Path:
    """A JupyterLab-shaped notebook on disk, written without the store."""
    path = tmp_path / "explore" / "session.ipynb"
    path.parent.mkdir(parents=True)
    path.write_bytes(_nbformat_bytes(_JUPYTERLAB_NOTEBOOK))
    return path


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _key_orders(value: Any, trail: str = "") -> dict[str, list[str]]:
    """Collect the key order of every mapping in *value*, keyed by its path."""
    orders: dict[str, list[str]] = {}
    if isinstance(value, dict):
        orders[trail] = list(value)
        for key, item in value.items():
            orders.update(_key_orders(item, f"{trail}/{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            orders.update(_key_orders(item, f"{trail}[{index}]"))
    return orders


# ---------------------------------------------------------------------------
# Round trip (FR-027, FR-032, FR-033)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """A notebook the store did not write comes back exactly as it went in."""

    def test_reading_and_writing_a_jupyter_notebook_is_byte_identical(self, notebook_path: Path) -> None:
        original = notebook_path.read_bytes()

        store = NotebookStore(notebook_path)
        store.write(store.read())

        assert notebook_path.read_bytes() == original

    def test_the_serialiser_matches_the_nbformat_recipe(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        assert document.to_bytes() == _nbformat_bytes(_JUPYTERLAB_NOTEBOOK)

    def test_every_unrecognised_key_survives_a_round_trip(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        write_notebook(notebook_path, document)

        reloaded = _load(notebook_path)
        assert reloaded == _JUPYTERLAB_NOTEBOOK
        assert reloaded["unknown_top_level_key"] == {"written_by": "some other tool"}
        assert reloaded["metadata"]["widgets"]["application/vnd.jupyter.widget-state+json"]["version_major"] == 2
        assert reloaded["cells"][1]["deepnote_cell_type"] == "code"
        assert reloaded["cells"][1]["metadata"]["vendor-y"] == "keep me"
        assert reloaded["cells"][1]["metadata"][ANALYSIS_METADATA_KEY]["unrecognised_future_key"] == {
            "written_by": "a later SciStudio",
            "keep": [1, 2, 3],
        }
        assert reloaded["cells"][1]["outputs"][1]["metadata"]["needs_background"] == "light"

    def test_the_analysis_record_survives_a_round_trip(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        write_notebook(notebook_path, document)

        record = _load(notebook_path)["cells"][1]["metadata"][ANALYSIS_METADATA_KEY]
        assert record == _JUPYTERLAB_NOTEBOOK["cells"][1]["metadata"][ANALYSIS_METADATA_KEY]

    def test_outputs_are_kept_on_disk(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        write_notebook(notebook_path, document)

        outputs = _load(notebook_path)["cells"][1]["outputs"]
        assert [output["output_type"] for output in outputs] == ["stream", "execute_result", "error"]
        assert outputs[1]["data"]["image/png"] == "iVBORw0KGgoAAAANSUhEUg=="
        assert _load(notebook_path)["cells"][1]["execution_count"] == 3

    def test_a_hand_edited_notebook_keeps_its_content_and_key_order(self, tmp_path: Path) -> None:
        path = tmp_path / "hand.ipynb"
        path.write_text(_HAND_EDITED_NOTEBOOK_TEXT, encoding="utf-8", newline="\n")
        expected = json.loads(_HAND_EDITED_NOTEBOOK_TEXT)

        write_notebook(path, read_notebook(path))

        written = _load(path)
        assert written == expected
        assert _key_orders(written) == _key_orders(expected)

    def test_writing_a_hand_edited_notebook_twice_is_stable(self, tmp_path: Path) -> None:
        path = tmp_path / "hand.ipynb"
        path.write_text(_HAND_EDITED_NOTEBOOK_TEXT, encoding="utf-8", newline="\n")

        write_notebook(path, read_notebook(path))
        once = path.read_bytes()
        write_notebook(path, read_notebook(path))

        assert path.read_bytes() == once

    def test_non_ascii_is_written_unescaped(self, notebook_path: Path) -> None:
        write_notebook(notebook_path, read_notebook(notebook_path))

        assert "峰位" in notebook_path.read_text(encoding="utf-8")
        assert "🧪" in notebook_path.read_text(encoding="utf-8")

    def test_line_endings_are_never_translated(self, notebook_path: Path) -> None:
        write_notebook(notebook_path, read_notebook(notebook_path))

        assert b"\r\n" not in notebook_path.read_bytes()

    def test_a_cell_without_an_id_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "hand.ipynb"
        path.write_text(_HAND_EDITED_NOTEBOOK_TEXT, encoding="utf-8", newline="\n")

        document = read_notebook(path)

        assert [cell.cell_id for cell in document.cells] == [None, None]
        assert document.index_of("anything") is None


# ---------------------------------------------------------------------------
# Reading cells (FR-033)
# ---------------------------------------------------------------------------


class TestCellViews:
    """Cells read as cells, with their metadata intact."""

    def test_cells_report_their_type_source_and_id(self, notebook_path: Path) -> None:
        cells = read_notebook(notebook_path).cells

        assert [cell.cell_type for cell in cells] == ["markdown", "code", "code", "raw"]
        assert [cell.cell_id for cell in cells] == ["intro-cell", "load-cell", "fit-cell", "raw-cell"]
        assert cells[1].source == ("import scistudio\n\nspectrum = scistudio.load(scistudio.input('spectrum'))\n")
        assert cells[2].source == "fit = spectrum.fit()\n"

    def test_a_cell_reports_its_outputs_and_execution_count(self, notebook_path: Path) -> None:
        cells = read_notebook(notebook_path).cells

        assert len(cells[1].outputs) == 3
        assert cells[1].execution_count == 3
        assert cells[2].outputs == ()
        assert cells[2].execution_count is None
        assert cells[0].outputs == ()

    def test_cell_metadata_carries_keys_the_store_does_not_model(self, notebook_path: Path) -> None:
        cell = read_notebook(notebook_path).cells[1]

        assert cell.metadata["vendor-y"] == "keep me"
        assert cell.scistudio_metadata["assigned"] == ["spectrum"]
        assert cell.scistudio_metadata["unrecognised_future_key"]["keep"] == [1, 2, 3]

    def test_views_are_read_only(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        with pytest.raises(TypeError):
            document.metadata["celltoolbar"] = "None"  # type: ignore[index]
        with pytest.raises(TypeError):
            document.cells[0].metadata["tags"] = []  # type: ignore[index]
        with pytest.raises(TypeError):
            document.raw["nbformat"] = 5  # type: ignore[index]

    def test_a_document_copy_is_independent(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        clone = document.copy()

        clone.set_cell_source("fit-cell", "fit = None\n")

        assert document.cell("fit-cell").source == "fit = spectrum.fit()\n"
        assert clone.cell("fit-cell").source == "fit = None\n"

    def test_nbformat_version_is_reported(self, notebook_path: Path) -> None:
        assert read_notebook(notebook_path).nbformat_version == (4, 5)


# ---------------------------------------------------------------------------
# The enabled flag (FR-033)
# ---------------------------------------------------------------------------


class TestEnabledFlag:
    """The notebook owns the flag; the analysis only reads it."""

    def test_a_cell_with_no_flag_is_enabled(self, notebook_path: Path) -> None:
        cells = read_notebook(notebook_path).cells

        assert cells[0].enabled is True
        assert cells[1].enabled is True

    def test_a_disabled_cell_reads_as_disabled(self, notebook_path: Path) -> None:
        assert read_notebook(notebook_path).cell("fit-cell").enabled is False

    def test_toggling_the_flag_changes_nothing_else_in_the_file(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_enabled("load-cell", enabled=False)
        write_notebook(notebook_path, document)

        written = _load(notebook_path)
        expected = json.loads(json.dumps(_JUPYTERLAB_NOTEBOOK))
        expected["cells"][1]["metadata"][ANALYSIS_METADATA_KEY][ENABLED_METADATA_KEY] = False
        assert written == expected

    def test_the_flag_lands_beside_the_analysis_record(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_enabled("load-cell", enabled=False)

        namespace = document.cell("load-cell").scistudio_metadata
        assert namespace[ENABLED_METADATA_KEY] is False
        assert namespace["source_hash"] == "0f1e2d3c"
        assert namespace["unrecognised_future_key"]["keep"] == [1, 2, 3]

    def test_the_flag_can_be_set_on_a_cell_with_no_metadata(self, tmp_path: Path) -> None:
        document = new_notebook([new_code_cell("a = 1", cell_id="c1")])

        document.set_cell_enabled("c1", enabled=False)
        path = write_notebook(tmp_path / "n.ipynb", document)

        assert read_notebook(path).cell("c1").enabled is False


# ---------------------------------------------------------------------------
# Cell edits (FR-005)
# ---------------------------------------------------------------------------


class TestCellEdits:
    """Edits received through the API are persisted without collateral damage."""

    def test_setting_a_source_keeps_the_line_list_form(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_source("load-cell", "x = 1\ny = 2\n")
        write_notebook(notebook_path, document)

        assert _load(notebook_path)["cells"][1]["source"] == ["x = 1\n", "y = 2\n"]

    def test_setting_a_source_keeps_the_plain_string_form(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_source("fit-cell", "x = 1\ny = 2\n")
        write_notebook(notebook_path, document)

        assert _load(notebook_path)["cells"][2]["source"] == "x = 1\ny = 2\n"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "a = 1",
            "a = 1\n",
            "a = 1\n\n\n",
            "def f():\n    return 1\n",
            "s = '峰位 🧪'\n",
            "a = 1\rb = 2\n",
            "a = 1\x0cb = 2\n",
        ],
    )
    def test_a_source_round_trips_through_the_file_exactly(self, tmp_path: Path, text: str) -> None:
        document = new_notebook([new_code_cell("placeholder", cell_id="c1")])
        document.set_cell_source("c1", text)
        path = write_notebook(tmp_path / "n.ipynb", document)

        assert read_notebook(path).cell("c1").source == text

    def test_an_edit_leaves_the_cells_metadata_alone(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_source("load-cell", "x = 1\n")

        assert document.cell("load-cell").metadata["vendor-y"] == "keep me"
        assert document.cell("load-cell").scistudio_metadata["source_hash"] == "0f1e2d3c"

    def test_an_analysis_record_merges_without_dropping_siblings(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_enabled("load-cell", enabled=False)
        document.set_analysis_record("load-cell", {"source_hash": "ffff0000", "assigned": ["spectrum", "peaks"]})

        namespace = document.cell("load-cell").scistudio_metadata
        assert namespace["source_hash"] == "ffff0000"
        assert namespace["assigned"] == ["spectrum", "peaks"]
        assert namespace[ENABLED_METADATA_KEY] is False
        assert namespace["unrecognised_future_key"]["keep"] == [1, 2, 3]

    def test_an_analysis_record_is_copied_not_aliased(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        record: dict[str, Any] = {"observation": {"changed": ["a"]}}

        document.set_analysis_record("load-cell", record)
        record["observation"]["changed"].append("b")

        assert document.cell("load-cell").scistudio_metadata["observation"] == {"changed": ["a"]}

    def test_a_cell_can_be_inserted_after_the_current_one(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.insert_cell_after("load-cell", new_code_cell("peaks = fit.peaks", cell_id="new-cell"))

        assert [cell.cell_id for cell in document.cells] == [
            "intro-cell",
            "load-cell",
            "new-cell",
            "fit-cell",
            "raw-cell",
        ]

    def test_a_cell_can_be_appended_and_removed(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.append_cell(new_markdown_cell("tail", cell_id="tail-cell"))
        document.remove_cell("raw-cell")

        assert [cell.cell_id for cell in document.cells] == [
            "intro-cell",
            "load-cell",
            "fit-cell",
            "tail-cell",
        ]

    def test_an_inserted_cell_is_copied_not_aliased(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        cell = new_code_cell("a = 1", cell_id="new-cell")

        document.append_cell(cell)
        cell["metadata"]["mutated"] = True

        assert "mutated" not in document.cell("new-cell").metadata

    @pytest.mark.parametrize(
        "operation",
        [
            lambda doc: doc.cell("missing"),
            lambda doc: doc.set_cell_source("missing", "a = 1"),
            lambda doc: doc.set_cell_enabled("missing", enabled=False),
            lambda doc: doc.set_analysis_record("missing", {}),
            lambda doc: doc.insert_cell_after("missing", new_code_cell()),
            lambda doc: doc.remove_cell("missing"),
        ],
    )
    def test_an_unknown_cell_id_raises(self, notebook_path: Path, operation: Any) -> None:
        document = read_notebook(notebook_path)

        with pytest.raises(KeyError, match="missing"):
            operation(document)

    def test_the_session_id_is_written_into_notebook_metadata(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_scistudio_metadata("session_id", "s-000001")
        write_notebook(notebook_path, document)

        namespace = _load(notebook_path)["metadata"][ANALYSIS_METADATA_KEY]
        assert namespace["session_id"] == "s-000001"
        assert namespace["vendor_note"] == "kept"


# ---------------------------------------------------------------------------
# Recording what a run produced (FR-027)
# ---------------------------------------------------------------------------


class TestSetCellOutputs:
    """The document can be told what a run produced, so the file on disk keeps it.

    The counterpart of stripping, and the half that was missing until #2240:
    without it every "the commit is stripped of outputs" assertion held for a
    notebook that never had an output, and a notebook reopened here or in
    JupyterLab showed every cell as never having run.
    """

    def test_outputs_and_the_execution_count_reach_the_file(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_outputs(
            "fit-cell",
            [{"output_type": "stream", "name": "stdout", "text": "fitted 3 peaks\n"}],
            execution_count=11,
        )
        write_notebook(notebook_path, document)

        cell = _load(notebook_path)["cells"][2]
        assert cell["outputs"] == [{"output_type": "stream", "name": "stdout", "text": "fitted 3 peaks\n"}]
        assert cell["execution_count"] == 11

    def test_the_new_outputs_replace_the_old_ones(self, notebook_path: Path) -> None:
        """A rerun's outputs are what the cell shows, not those plus the last run's."""
        document = read_notebook(notebook_path)
        assert len(document.cell("load-cell").outputs) == 3

        document.set_cell_outputs("load-cell", [{"output_type": "stream", "name": "stdout", "text": "again\n"}])

        assert [dict(output) for output in document.cell("load-cell").outputs] == [
            {"output_type": "stream", "name": "stdout", "text": "again\n"}
        ]
        assert document.cell("load-cell").execution_count is None

    def test_the_caller_keeps_no_handle_into_the_document(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        payload: dict[str, Any] = {"output_type": "stream", "name": "stdout", "text": "first\n"}

        document.set_cell_outputs("fit-cell", [payload])
        payload["text"] = "mutated after the call"

        assert document.cell("fit-cell").outputs[0]["text"] == "first\n"

    def test_a_markdown_cell_is_refused_rather_than_given_output_keys(self, notebook_path: Path) -> None:
        """nbformat allows ``outputs`` on a code cell alone, so this cannot be silent."""
        document = read_notebook(notebook_path)

        with pytest.raises(NotebookStoreError, match="not a code cell"):
            document.set_cell_outputs("intro-cell", [{"output_type": "stream", "name": "stdout", "text": "x"}])

        assert "outputs" not in document.cell("intro-cell").raw

    def test_an_unknown_cell_is_a_key_error(self, notebook_path: Path) -> None:
        with pytest.raises(KeyError):
            read_notebook(notebook_path).set_cell_outputs("no-such-cell", [])

    def test_recorded_outputs_are_stripped_from_the_committed_form(self, notebook_path: Path) -> None:
        """FR-027 and FR-028 together: the file keeps them, the commit does not."""
        document = read_notebook(notebook_path)
        document.set_cell_outputs(
            "fit-cell",
            [{"output_type": "stream", "name": "stdout", "text": "fitted\n"}],
            execution_count=11,
        )

        stripped = strip_outputs(document)

        assert stripped.cell("fit-cell").outputs == ()
        assert stripped.cell("fit-cell").execution_count is None
        assert document.cell("fit-cell").outputs[0]["text"] == "fitted\n"

    def test_the_analysis_record_and_the_enabled_flag_survive(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        document.set_cell_outputs("fit-cell", [{"output_type": "stream", "name": "stdout", "text": "x\n"}])

        namespace = document.cell("fit-cell").scistudio_metadata
        assert namespace["source_hash"] == "abcd1234"
        assert document.cell("fit-cell").enabled is False


# ---------------------------------------------------------------------------
# Output stripping (FR-028, FR-032)
# ---------------------------------------------------------------------------


class TestStripOutputs:
    """The committed form has no outputs; nothing else differs and the file is untouched."""

    def test_only_outputs_and_execution_counts_change(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        stripped = json.loads(strip_outputs(document).to_json())

        expected = json.loads(json.dumps(_JUPYTERLAB_NOTEBOOK))
        expected["cells"][1]["outputs"] = []
        expected["cells"][1]["execution_count"] = None
        assert stripped == expected

    def test_the_document_and_the_file_are_untouched(self, notebook_path: Path) -> None:
        before = notebook_path.read_bytes()
        document = read_notebook(notebook_path)

        strip_outputs(document)

        assert notebook_path.read_bytes() == before
        assert document.to_bytes() == before
        assert len(document.cell("load-cell").outputs) == 3
        assert document.cell("load-cell").execution_count == 3

    def test_a_markdown_or_raw_cell_gains_no_output_keys(self, notebook_path: Path) -> None:
        stripped = json.loads(strip_outputs(read_notebook(notebook_path)).to_json())

        for index in (0, 3):
            assert "outputs" not in stripped["cells"][index]
            assert "execution_count" not in stripped["cells"][index]

    def test_analysis_records_and_unknown_keys_survive_stripping(self, notebook_path: Path) -> None:
        stripped = strip_outputs(read_notebook(notebook_path))

        namespace = stripped.cell("load-cell").scistudio_metadata
        assert namespace["source_hash"] == "0f1e2d3c"
        assert namespace["unrecognised_future_key"]["keep"] == [1, 2, 3]
        assert stripped.cell("fit-cell").enabled is False
        assert stripped.raw["unknown_top_level_key"] == {"written_by": "some other tool"}
        assert stripped.raw["metadata"]["widgets"] != {}

    def test_the_stripped_document_is_independent(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)
        stripped = strip_outputs(document)

        stripped.set_cell_source("fit-cell", "changed\n")

        assert document.cell("fit-cell").source == "fit = spectrum.fit()\n"

    def test_stripping_twice_is_idempotent(self, notebook_path: Path) -> None:
        once = strip_outputs(read_notebook(notebook_path))

        assert strip_outputs(once).to_bytes() == once.to_bytes()


# ---------------------------------------------------------------------------
# External change detection (FR-005, A-012)
# ---------------------------------------------------------------------------


class TestExternalChange:
    """The store tells its own writes from everybody else's."""

    def test_the_stores_own_write_is_not_an_external_change(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        document = store.read()

        document.set_cell_source("fit-cell", "fit = spectrum.fit(model='voigt')\n")
        store.write(document)

        assert store.has_external_change() is False
        assert store.reload() is None

    def test_a_fresh_read_is_not_an_external_change(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        store.read()

        assert store.has_external_change() is False

    def test_a_store_that_has_read_nothing_reports_a_change(self, notebook_path: Path) -> None:
        assert NotebookStore(notebook_path).has_external_change() is True

    def test_an_external_edit_is_detected_and_reloaded(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        store.read()

        edited = json.loads(json.dumps(_JUPYTERLAB_NOTEBOOK))
        edited["cells"].append(
            {
                "cell_type": "code",
                "execution_count": None,
                "id": "added-outside",
                "metadata": {},
                "outputs": [],
                "source": ["report(fit)\n"],
            }
        )
        notebook_path.write_bytes(_nbformat_bytes(edited))

        assert store.has_external_change() is True
        reloaded = store.reload()
        assert reloaded is not None
        assert [cell.cell_id for cell in reloaded.cells] == [
            "intro-cell",
            "load-cell",
            "fit-cell",
            "raw-cell",
            "added-outside",
        ]
        assert store.has_external_change() is False

    def test_a_reload_keeps_the_cell_ids_the_marks_are_kept_by(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        before = {cell.cell_id for cell in store.read().cells}

        edited = json.loads(json.dumps(_JUPYTERLAB_NOTEBOOK))
        edited["cells"][2]["source"] = ["fit = spectrum.fit(model='voigt')\n"]
        notebook_path.write_bytes(_nbformat_bytes(edited))

        reloaded = store.reload()
        assert reloaded is not None
        assert {cell.cell_id for cell in reloaded.cells} == before

    def test_an_edit_written_in_the_same_clock_tick_is_still_detected(self, notebook_path: Path) -> None:
        # A stat-based check would miss this: the Windows system clock advances
        # roughly every 15 ms, so two writes can share an mtime, and this edit
        # keeps the file's size. Content is the only reliable question.
        store = NotebookStore(notebook_path)
        store.read()
        stamp = notebook_path.stat()
        original = notebook_path.read_text(encoding="utf-8")
        edited = original.replace("fit = spectrum.fit()", "fit = spectrum.FIT()")
        assert edited != original

        notebook_path.write_text(edited, encoding="utf-8", newline="\n")
        os.utime(notebook_path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

        assert notebook_path.stat().st_size == stamp.st_size
        assert notebook_path.stat().st_mtime_ns == stamp.st_mtime_ns
        assert store.has_external_change() is True
        reloaded = store.reload()
        assert reloaded is not None
        assert reloaded.cell("fit-cell").source == "fit = spectrum.FIT()\n"

    def test_a_rewrite_that_restores_identical_bytes_is_not_a_change(self, notebook_path: Path) -> None:
        # What a git checkout of the same commit looks like from here.
        store = NotebookStore(notebook_path)
        store.read()
        payload = notebook_path.read_bytes()

        notebook_path.write_bytes(payload)

        assert store.has_external_change() is False
        assert store.reload() is None

    def test_a_deleted_notebook_is_a_change(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        store.read()

        notebook_path.unlink()

        assert store.has_external_change() is True
        with pytest.raises(FileNotFoundError):
            store.reload()

    def test_a_never_seen_missing_notebook_is_not_a_change(self, tmp_path: Path) -> None:
        # Nothing to reload: the store has seen no bytes and there are none.
        assert NotebookStore(tmp_path / "absent.ipynb").has_external_change() is False

    def test_a_damaged_file_keeps_the_previous_digest(self, notebook_path: Path) -> None:
        store = NotebookStore(notebook_path)
        store.read()
        notebook_path.write_text("{ not json", encoding="utf-8")

        with pytest.raises(NotebookStoreError):
            store.reload()

        # The damage was not accepted as the new baseline, so a later
        # well-formed write still reads as a change rather than being missed.
        assert store.has_external_change() is True
        repaired = json.loads(json.dumps(_JUPYTERLAB_NOTEBOOK))
        repaired["cells"][2]["source"] = "fit = spectrum.fit(model='voigt')\n"
        notebook_path.write_bytes(_nbformat_bytes(repaired))
        reloaded = store.reload()
        assert reloaded is not None
        assert reloaded.cell("fit-cell").source == "fit = spectrum.fit(model='voigt')\n"

    def test_store_reports_its_path_and_presence(self, tmp_path: Path, notebook_path: Path) -> None:
        assert NotebookStore(notebook_path).path == notebook_path
        assert NotebookStore(notebook_path).exists() is True
        assert NotebookStore(tmp_path / "absent.ipynb").exists() is False
        assert NotebookStore(notebook_path).last_seen_digest is None


# ---------------------------------------------------------------------------
# Creating a notebook (FR-004's seam) and rejecting a non-notebook
# ---------------------------------------------------------------------------


class TestNewNotebook:
    """A generated notebook is the shape Jupyter writes."""

    def test_a_new_notebook_is_nbformat_4_5(self, tmp_path: Path) -> None:
        document = new_notebook([new_code_cell("import scistudio\n", cell_id="first")])
        path = write_notebook(tmp_path / "n.ipynb", document)

        assert path.read_bytes() == _nbformat_bytes(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "id": "first",
                        "metadata": {},
                        "outputs": [],
                        "source": ["import scistudio\n"],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        )

    def test_generated_cell_ids_are_unique_and_schema_safe(self) -> None:
        ids = {str(new_code_cell()["id"]) for _ in range(50)}

        assert len(ids) == 50
        assert all(cell_id.isalnum() and 1 <= len(cell_id) <= 64 for cell_id in ids)

    def test_a_markdown_cell_carries_no_output_keys(self) -> None:
        cell = new_markdown_cell("# title\n")

        assert "outputs" not in cell
        assert "execution_count" not in cell

    def test_notebook_metadata_can_be_seeded(self, tmp_path: Path) -> None:
        document = new_notebook(metadata={"kernelspec": {"name": "scistudio"}})
        path = write_notebook(tmp_path / "n.ipynb", document)

        assert read_notebook(path).metadata["kernelspec"] == {"name": "scistudio"}

    def test_seeded_cells_and_metadata_are_copied(self) -> None:
        cell = new_code_cell("a = 1", cell_id="c1")
        metadata: dict[str, Any] = {"kernelspec": {"name": "scistudio"}}

        document = new_notebook([cell], metadata=metadata)
        cell["metadata"]["mutated"] = True
        metadata["kernelspec"]["name"] = "other"

        assert "mutated" not in document.cell("c1").metadata
        assert document.metadata["kernelspec"] == {"name": "scistudio"}


class TestRejections:
    """A file that is not a notebook says so, and a missing one is a different error."""

    def test_a_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_notebook(tmp_path / "absent.ipynb")
        with pytest.raises(FileNotFoundError):
            NotebookStore(tmp_path / "absent.ipynb").read()

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("{ not json", "not valid JSON"),
            ("[1, 2, 3]", "top level is list"),
            ('{"metadata": {}}', "no 'cells' array"),
            ('{"cells": {}}', "'cells' is dict"),
            ('{"cells": ["a string"]}', "cell 0 is str"),
        ],
    )
    def test_a_non_notebook_is_rejected_with_its_path(self, tmp_path: Path, content: str, message: str) -> None:
        path = tmp_path / "broken.ipynb"
        path.write_text(content, encoding="utf-8")

        with pytest.raises(NotebookStoreError, match=message) as excinfo:
            read_notebook(path)

        assert "broken.ipynb" in str(excinfo.value)

    def test_the_document_constructor_rejects_a_non_notebook(self) -> None:
        with pytest.raises(NotebookStoreError):
            NotebookDocument({"metadata": {}})

    def test_the_document_constructor_rejects_a_non_mapping(self) -> None:
        with pytest.raises(NotebookStoreError, match="top level is list"):
            NotebookDocument(["cells"])  # type: ignore[arg-type]


class TestDamagedButReadableCells:
    """A cell missing a key the format says is required still reads and writes."""

    def test_a_cell_with_no_metadata_can_be_written_to(self, tmp_path: Path) -> None:
        document = NotebookDocument({"cells": [{"cell_type": "code", "id": "c1", "source": "a = 1\n"}]})

        document.set_cell_enabled("c1", enabled=False)
        document.set_analysis_record("c1", {"assigned": ["a"]})
        path = write_notebook(tmp_path / "n.ipynb", document)

        cell = read_notebook(path).cell("c1")
        assert cell.enabled is False
        assert cell.scistudio_metadata["assigned"] == ["a"]

    def test_a_notebook_with_no_metadata_can_be_written_to(self, tmp_path: Path) -> None:
        document = NotebookDocument({"cells": []})

        document.set_notebook_metadata("kernelspec", {"name": "scistudio"})
        document.set_scistudio_metadata("session_id", "s-1")
        path = write_notebook(tmp_path / "n.ipynb", document)

        reloaded = read_notebook(path)
        assert reloaded.metadata["kernelspec"] == {"name": "scistudio"}
        assert reloaded.scistudio_metadata["session_id"] == "s-1"

    def test_metadata_that_is_not_a_mapping_is_replaced_not_crashed_on(self, tmp_path: Path) -> None:
        document = NotebookDocument({"cells": [{"cell_type": "code", "id": "c1", "metadata": []}], "metadata": "junk"})

        document.set_cell_enabled("c1", enabled=True)
        document.set_notebook_metadata("kernelspec", {"name": "scistudio"})

        assert document.cell("c1").enabled is True
        assert document.metadata["kernelspec"] == {"name": "scistudio"}

    def test_a_cell_with_a_null_source_reads_as_empty(self) -> None:
        document = NotebookDocument({"cells": [{"cell_type": "code", "id": "c1", "source": None}]})

        assert document.cell("c1").source == ""
        assert document.cell("c1").cell_type == "code"

    def test_a_cell_with_no_type_reads_as_empty(self) -> None:
        document = NotebookDocument({"cells": [{"id": "c1"}]})

        assert document.cell("c1").cell_type == ""
        assert document.cell("c1").outputs == ()
        assert document.cell("c1").execution_count is None

    def test_a_notebook_with_no_version_reports_the_default(self) -> None:
        assert NotebookDocument({"cells": []}).nbformat_version == (4, 0)

    def test_a_boolean_is_not_mistaken_for_an_execution_count(self) -> None:
        document = NotebookDocument({"cells": [{"cell_type": "code", "id": "c1", "execution_count": True}]})

        assert document.cell("c1").execution_count is None

    def test_an_output_that_is_not_a_mapping_is_skipped_but_kept(self, tmp_path: Path) -> None:
        raw = {"cells": [{"cell_type": "code", "id": "c1", "outputs": ["junk", {"output_type": "stream"}]}]}
        document = NotebookDocument(json.loads(json.dumps(raw)))

        assert len(document.cell("c1").outputs) == 1
        path = write_notebook(tmp_path / "n.ipynb", document)
        assert _load(path)["cells"][0]["outputs"] == ["junk", {"output_type": "stream"}]


class TestValueSemantics:
    """Equality and repr, so a failing assertion elsewhere reads."""

    def test_documents_compare_by_content(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        assert document == read_notebook(notebook_path)
        assert document != strip_outputs(document)
        assert document != "not a document"

    def test_cells_compare_by_content(self, notebook_path: Path) -> None:
        cells = read_notebook(notebook_path).cells

        assert cells[0] == read_notebook(notebook_path).cells[0]
        assert cells[0] != cells[1]
        assert cells[0] != "not a cell"

    def test_reprs_name_what_they_are(self, notebook_path: Path) -> None:
        document = read_notebook(notebook_path)

        assert repr(document) == "NotebookDocument(cells=4)"
        assert repr(document.cell("load-cell")) == "NotebookCell(id='load-cell', cell_type='code')"
        assert "session.ipynb" in repr(NotebookStore(notebook_path))

    def test_a_cells_raw_view_carries_keys_the_store_does_not_model(self, notebook_path: Path) -> None:
        cell = read_notebook(notebook_path).cell("load-cell")

        assert cell.raw["deepnote_cell_type"] == "code"
        with pytest.raises(TypeError):
            cell.raw["cell_type"] = "markdown"  # type: ignore[index]
