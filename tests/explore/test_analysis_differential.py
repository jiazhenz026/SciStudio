"""T-010: the differential test that defends the backward slice (ADR-054 spec 2 §4.4).

Every other test in ``tests/explore`` asks the analysis what it believes. This
one asks the interpreter. For each fixture notebook it

1. executes every enabled cell in written order **in a subprocess**, with the
   whole module namespace fingerprinted before and after each cell so that the
   observation of FR-026 is a real one rather than a literal written by the test;
2. feeds those observations back into :func:`build_graph` and asks for the
   backward slice of the cells that declare outputs (FR-021);
3. executes **only that slice**, in a second subprocess with a namespace that
   has never seen the other cells, and records the declared outputs again.

The two sets of outputs MUST be equal (SC-003). A difference means the slice
omitted a cell whose effect the outputs depend on, which is the failure User
Story 2 exists to prevent and which nothing else in the suite can detect: a
missed edge is invisible to a test that asserts the edges the analysis produced.

Two fixtures are here because they **fail**. ``global_counter.ipynb`` and
``wrapped_operator.ipynb`` are ordinary notebooks whose slice raises
``NameError`` when it runs, and each has its own named test rather than a row in
the parametrised list, so that the pytest summary names the defect rather than
hiding it behind a fixture id. Their docstrings carry the finding.

The executing half lives in ``fixtures/_run_notebook.py``; this module never
runs notebook code in the pytest process. Spawning a fresh interpreter is not
ceremony: a slice that "passed" only because the full run had already imported
numpy, or because a name the slice dropped was still lying around in the test
process, would be exactly the false pass this test exists to rule out.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from functools import cache
from typing import Any

import pytest

import scistudio
from scistudio.explore.dependency_analysis import CellFacts, DependencyGraph, analyse_cells, build_graph

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
RUNNER = FIXTURES / "_run_notebook.py"
SRC_ROOT = pathlib.Path(scistudio.__file__).resolve().parent.parent

RESULT_BEGIN = "<<<SCISTUDIO-DIFFERENTIAL-RESULT"
RESULT_END = "SCISTUDIO-DIFFERENTIAL-RESULT>>>"

#: The fixtures whose slice is expected to reproduce the notebook. The four
#: Story 2 variants come first: the spec requires the in-place, subscript,
#: library-function, and helper mutations each to be *proven* caught by the
#: observation rather than assumed.
SOUND_FIXTURES = (
    "story_two_in_place.ipynb",
    "story_two_subscript.ipynb",
    "story_two_library_function.ipynb",
    "story_two_helper.ipynb",
    "alternatives_disabled.ipynb",
    "alias_mutation.ipynb",
    "deletion_and_reuse.ipynb",
    "line_magic.ipynb",
)

STORY_TWO_FIXTURES = SOUND_FIXTURES[:4]

#: The name each Story 2 variant's third cell mutates without assigning it.
STORY_TWO_MUTATED_NAME = {
    "story_two_in_place.ipynb": "df",
    "story_two_subscript.ipynb": "df",
    "story_two_library_function.ipynb": "values",
    "story_two_helper.ipynb": "df",
}


# ---------------------------------------------------------------------------
# Driving the runner
# ---------------------------------------------------------------------------


def run_notebook(name: str, *, mode: str, cells: tuple[str, ...] = ()) -> dict[str, Any]:
    """Run *name* in a fresh interpreter and return the runner's JSON result."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC_ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    argv = [sys.executable, str(RUNNER), str(FIXTURES / name), "--mode", mode]
    if cells:
        argv += ["--cells", ",".join(cells)]
    completed = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=300, check=False)
    assert completed.returncode == 0, f"runner failed for {name}:\n{completed.stdout}\n{completed.stderr}"
    body = completed.stdout.split(RESULT_BEGIN, 1)[1].split(RESULT_END, 1)[0]
    result: dict[str, Any] = json.loads(body)
    return result


def cell_sources(name: str) -> list[tuple[str, str, bool]]:
    """``(cell_id, source, enabled)`` for every code cell of *name*, in written order."""
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    rows: list[tuple[str, str, bool]] = []
    for index, cell in enumerate(payload["cells"]):
        if cell.get("cell_type") != "code":
            continue
        source = cell["source"]
        rows.append(
            (
                cell.get("id") or f"cell-{index}",
                "".join(source) if isinstance(source, list) else source,
                bool(cell.get("metadata", {}).get("scistudio", {}).get("enabled", True)),
            )
        )
    return rows


@cache
def observed_run(name: str) -> dict[str, Any]:
    """The whole-notebook run, cached so one fixture costs one interpreter."""
    result = run_notebook(name, mode="full")
    assert result["error"] is None, f"the whole notebook failed for {name}: {result['error']}"
    return result


@cache
def analysed(name: str) -> tuple[tuple[CellFacts, ...], dict[str, bool], dict[str, Any]]:
    """The facts, the enabled map, and the observations the whole run produced."""
    rows = cell_sources(name)
    facts = analyse_cells([(cell_id, source) for cell_id, source, _ in rows])
    enabled = {cell_id: is_enabled for cell_id, _, is_enabled in rows}
    return facts, enabled, observed_run(name)["observations"]


def graph_for(name: str) -> DependencyGraph:
    facts, enabled, observations = analysed(name)
    return build_graph(
        facts,
        enabled=enabled,
        observations={cell_id: frozenset(entry["changed_names"]) for cell_id, entry in observations.items()},
    )


def slice_of_outputs(name: str) -> tuple[str, ...]:
    """The backward slice of every enabled output cell (FR-021)."""
    facts, enabled, _ = analysed(name)
    graph = graph_for(name)
    seeds = [cell.cell_id for cell in facts if cell.is_output_cell and enabled[cell.cell_id]]
    assert seeds, f"{name} declares no outputs, so there is nothing to slice"
    cells: tuple[str, ...] = graph.backward_slice(seeds).cells
    return cells


def differential(name: str) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    """The whole-notebook outputs, the slice outputs, and the slice."""
    whole = observed_run(name)
    cells = slice_of_outputs(name)
    sliced = run_notebook(name, mode="slice", cells=cells)
    assert sliced["error"] is None, f"the backward slice {cells} of {name} failed to run: {sliced['error']}"
    return whole["outputs"], sliced["outputs"], cells


# ---------------------------------------------------------------------------
# SC-003 — the slice reproduces the notebook
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", SOUND_FIXTURES)
def test_sc003_the_slice_reproduces_the_whole_notebook_outputs(name: str) -> None:
    """SC-003: running only the backward slice on a fresh namespace produces equal outputs."""
    whole, sliced, cells = differential(name)
    assert whole, f"{name} declared no outputs, so the comparison would be vacuous"
    assert sliced == whole, f"the slice {cells} of {name} did not reproduce the notebook's outputs"


@pytest.mark.parametrize("name", STORY_TWO_FIXTURES)
def test_sc002_the_story_two_slice_is_one_two_three_four_and_six(name: str) -> None:
    """SC-002 / US2 scenario 1: the slice is cells 1, 2, 3, 4, and 6 in written order.

    Cell 5 is the ``df.head()`` the person left in. It changes nothing, so nothing
    depends on it and the packaged block must not run it.
    """
    assert slice_of_outputs(name) == ("c1", "c2", "c3", "c4", "c6")


@pytest.mark.parametrize("name", STORY_TWO_FIXTURES)
def test_us2_the_mutating_cell_is_observed_to_change_the_name(name: str) -> None:
    """US2 scenarios 2 to 4: the mutation is *seen*, not assumed.

    Cell 3 assigns nothing its source shows, so it is a definer only because the
    fingerprint comparison in the subprocess reported the name as changed. The
    observation this asserts on came out of a real run, which is the difference
    between this test and its unit counterpart.
    """
    facts, _, observations = analysed(name)
    static = {cell.cell_id: cell.assigned for cell in facts}
    mutated = STORY_TWO_MUTATED_NAME[name]
    assert mutated not in static["c3"], "the static estimate was supposed to be blind to this mutation"
    assert mutated in observations["c3"]["changed_names"]
    assert graph_for(name).definer_for("c4", mutated) == "c3"


@pytest.mark.parametrize("name", SOUND_FIXTURES)
def test_us2_a_slice_that_runs_clean_reports_no_unresolved_read(name: str) -> None:
    """US2 scenario 5 / FR-021: packaging's check agrees with what the slice actually does.

    Every fixture in ``SOUND_FIXTURES`` runs its slice without a ``NameError``,
    so FR-021's unresolved list must be empty for all of them. The pair matters
    more than either half: an unresolved list that is empty for a slice that
    raises is the false negative the two failing fixtures below are made of, and
    a list that names something for a slice that runs would make packaging refuse
    a notebook that works.
    """
    facts, enabled, _ = analysed(name)
    seeds = [cell.cell_id for cell in facts if cell.is_output_cell and enabled[cell.cell_id]]
    result = graph_for(name).backward_slice(seeds)
    assert [(read.cell_id, read.name) for read in result.unresolved_reads] == []


def test_a_disabled_cell_neither_runs_nor_enters_the_slice() -> None:
    """FR-014 / US4: the disabled alternative filter is absent from both runs."""
    name = "alternatives_disabled.ipynb"
    assert "c3" not in observed_run(name)["executed"]
    assert "c3" not in slice_of_outputs(name)
    assert slice_of_outputs(name) == ("c1", "c2", "c4", "c5")


def test_the_alias_mutation_is_attributed_to_the_cell_that_made_it() -> None:
    """US3: a mutation through an alias moves both names, and the reader follows the mutating cell."""
    name = "alias_mutation.ipynb"
    observations = analysed(name)[2]
    assert {"alias", "df"} <= set(observations["c2"]["changed_names"])
    assert graph_for(name).definer_for("c3", "df") == "c2"


# ---------------------------------------------------------------------------
# The harness must be able to fail
# ---------------------------------------------------------------------------


def test_the_harness_detects_a_slice_that_dropped_a_mutating_cell() -> None:
    """The negative control, without which every assertion above proves nothing.

    A differential test that cannot fail is worth less than no test at all,
    because it reads like coverage. This runs the Story 2 slice with cell 3 —
    the ``dropna(inplace=True)`` — removed, and requires the outputs to differ.
    If this test ever passes-by-equality, the fixture has stopped exercising the
    in-place mutation and every SC-003 row above has gone quiet with it.
    """
    name = "story_two_in_place.ipynb"
    whole = observed_run(name)["outputs"]
    crippled = run_notebook(name, mode="slice", cells=("c1", "c2", "c4", "c6"))
    assert crippled["error"] is None
    assert crippled["outputs"] != whole


def test_the_harness_detects_a_slice_that_dropped_a_definer() -> None:
    """The other half of the control: a dropped definer must surface as an error, not silence."""
    crippled = run_notebook("story_two_in_place.ipynb", mode="slice", cells=("c2", "c3", "c4", "c6"))
    assert crippled["error"] is not None
    assert "NameError" in crippled["error"]


def test_every_fixture_is_covered_by_a_test() -> None:
    """A fixture nobody runs is a fixture that rots. This is the ratchet."""
    on_disk = {path.name for path in FIXTURES.glob("*.ipynb")}
    named = set(SOUND_FIXTURES) | {"global_counter.ipynb", "wrapped_operator.ipynb"}
    assert on_disk == named


# ---------------------------------------------------------------------------
# The two fixtures that fail — findings, not fixtures to be quietly removed
# ---------------------------------------------------------------------------


def test_sc003_global_counter_slice_reproduces_the_notebook() -> None:
    """FINDING P1 — a slice that raises ``NameError``: a nested-scope augmented assignment.

    ``global_counter.ipynb`` is five ordinary cells::

        c1  import scistudio
        c2  counter = 0
        c3  def bump():
                global counter
                counter += 1
        c4  bump(); bump()
        c5  scistudio.output(n=counter)

    FR-006 requires the analysis to record "the names the cell reads at module
    scope, **including names read inside a nested scope that resolve to the
    module scope**". ``counter += 1`` inside ``bump`` reads ``counter``, and
    :mod:`symtable` reports that symbol as assigned and global but *not* as
    referenced, so cell 3's read set comes back empty. Cell 3 is then a definer
    of ``counter`` that reads nothing, the slice stops there, and cell 2 — the
    only cell that gives ``counter`` its initial value — is left out. The slice
    runs, calls ``bump()``, and raises ``NameError: name 'counter' is not
    defined``. No unresolved read is reported, so packaging would have accepted
    the notebook.

    ``_collect_module_level_reads`` already repairs exactly this blind spot for
    augmented assignment and ``del`` at module scope; it does not walk into a
    nested scope, and a ``global`` declaration is the case where it must.

    I believe the product is wrong and this test is right: FR-006's sentence
    names this case, and SC-003 is the criterion it fails.
    """
    whole, sliced, cells = differential("global_counter.ipynb")
    assert sliced == whole, f"the slice {cells} did not reproduce the notebook's outputs"


def test_sc003_wrapped_operator_slice_reproduces_the_notebook() -> None:
    """FINDING P1 — a slice that raises ``NameError``: a formatter-wrapped operator.

    ``wrapped_operator.ipynb`` holds the output of any ``black``- or
    ``ruff format``-shaped formatter on a long binary expression::

        ratio = (
            total
            % count
        )

    FR-011 says a line whose first non-blank character is ``%`` or ``!`` MUST be
    removed before parsing. The continuation line ``    % count`` is such a line,
    so it is removed, the cell still parses — as ``ratio = (total)`` — and no flag
    is raised, because the strip is only meant to make magics parseable. What is
    lost is silent: ``count`` disappears from the cell's read set, the cell that
    defines ``count`` is not in the slice, and the slice then executes the cell's
    *original* source, which still says ``% count``, and raises ``NameError``.
    The same happens for ``!=`` at the start of a wrapped comparison.

    Only reads are lost, so FR-002's one guarantee — never omit an assignment the
    code shows — still holds; the guarantee simply does not cover this. FR-006
    does, and so does SC-003.

    Spec and product disagree here rather than product being alone at fault: the
    implementation obeys FR-011 exactly as written, and FR-011 as written is too
    broad, because a kernel tokenises before it decides what a magic is. I
    believe the test is right about the required outcome and that the fix belongs
    in FR-011 — strip a magic line only where the cell does not parse without it,
    or only at a statement boundary — rather than in a rule the implementer
    invented.
    """
    whole, sliced, cells = differential("wrapped_operator.ipynb")
    assert sliced == whole, f"the slice {cells} did not reproduce the notebook's outputs"


def test_the_wrapped_operator_read_is_lost_without_a_flag() -> None:
    """The root cause of the fixture above, isolated from the execution harness.

    Kept separate so that the finding survives even if the differential fixture
    is later rewritten, and so that a reader can see the loss without reading a
    subprocess transcript. ``count`` is read; nothing says it is not.
    """
    facts = analyse_cells([("c3", "ratio = (\n    total\n    % count\n)\n")])[0]
    assert facts.flags == (), "the strip raised no flag, which is FR-011 working as specified"
    assert "count" in facts.read, "FR-006: the cell reads count, and the analysis must say so"
