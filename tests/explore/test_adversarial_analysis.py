"""Adversarial coverage for the ADR-054 dependency analysis and fingerprint.

``test_dependency_analysis.py`` and ``test_fingerprint.py`` test the rules their
implementers set out to satisfy. This file tests the places nobody wanted the
answer to: the assertions that hold for a reason other than the one they claim,
the invariants that were only ever checked against an input that could not break
them, and the two honest limits the spec states but no test pins down.

Where the tests came from
-------------------------

Half of what is here came from **mutation testing**. The production modules were
copied to a scratch tree, fifty-one behavioural mutations were applied one at a
time, and ``tests/explore/test_dependency_analysis.py`` and
``tests/explore/test_fingerprint.py`` were run against each. Forty-two mutations
were caught. Nine survived. Four of the nine turned out to be **equivalent
mutants**, where the behaviour is held by a second mechanism and the removed one
is dead: the node ceiling is already enforced by the container loops'
``_exhausted`` check; no reachable pair of integers collides when the width
prefix is dropped; ``downstream``'s ``seen.discard(start)`` cannot be reached
because every edge runs upward; and ``_digest_sequence``'s length feed is
redundant with the per-index feed it sits beside. Each of those has a test below
whose docstring says so, so that the next reader does not re-derive it.

The other **five are genuine coverage holes** — the set fold, the sampled string
tail, the dict key, cycle detection, and the categorical storage path — and each
has a test in the section below that kills its mutant.

A second, independent round of mutation testing — the no-context audit of this
change, fifty-seven mutations over two rounds — left ten more standing, and the
six behavioural ones are in the same section: the descent into ``except`` and
``match_case`` bodies, FR-029's check on the *after* snapshot, the string
*stride* (as opposed to its tail, above), and the two cost guards that every
``hashed_bytes`` assertion is blind to by construction. The dict and set half of
FR-025 was the one survivor that was a defect rather than a hole, and it is fixed
rather than pinned.

The other half came from reading the spec's MUSTs against the code that claims
them. Those tests are grouped by requirement, and the ones that found a defect
carry a ``FINDING`` line in the first sentence of their docstring with the
severity. They were written **failing**, on purpose: a fix agent owned the
repairs, and a test that is skipped, xfailed, or softened to pass is a finding
that has been filed and closed in the same motion.

Every one of them now passes, and each of those docstrings has been rewritten in
the past tense to say what was found, that it is closed, and what closed it.
Three ``FINDING`` lines remain in the present tense and all three say why in
their first paragraph: the process-dependent digest of a large set of strings
and the record that carries no cell id are both boundaries the spec does not
state rather than defects, and were filed as documented-not-failed from the
start; FR-015's second exception is an open owner decision tracked as ``#2243``.
Nothing in this file fails. If a docstring here describes the product as broken
without saying it is deliberate or naming the issue that tracks it, the docstring
is stale and the product is not.

What is deliberately *not* asserted here is anything the spec admits it cannot
do. The fingerprint misses a change confined to bytes its stride skipped, and
§4.5 says so. The test for that case therefore documents the miss, and asserts
the thing that makes the miss survivable — FR-002's union — rather than
pretending the miss is caught.
"""

from __future__ import annotations

import builtins
import io
import json
import math
import os
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import pytest

from scistudio.explore import fingerprint as fingerprint_module
from scistudio.explore.dependency_analysis import (
    AnalysisFlag,
    DependencyGraph,
    EdgeOrigin,
    analyse_cell,
    analyse_cells,
    build_graph,
    decode_cell_record,
    encode_cell_record,
    observation_flags,
    source_hash,
)
from scistudio.explore.fingerprint import (
    FINGERPRINT_BUDGET,
    ObservedChange,
    compare_namespaces,
    fingerprint,
)
from scistudio.explore.fingerprint import _fingerprint_context as fingerprint_context
from scistudio.explore.fingerprint import _flat as flat_handle

from .test_fingerprint import TIMING_RUNS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def graph_of(*cells: tuple[str, str], **kwargs: object) -> DependencyGraph:
    return build_graph(analyse_cells(cells), **kwargs)  # type: ignore[arg-type]


def edge_tuples(graph: DependencyGraph) -> set[tuple[str, str, str]]:
    return {(edge.reader, edge.definer, edge.name) for edge in graph.edges}


def unresolved_names(graph: DependencyGraph) -> set[tuple[str, str]]:
    return {(read.cell_id, read.name) for read in graph.unresolved_reads}


def digests(*values: object) -> list[str]:
    return [fingerprint(value).digest for value in values]


def run_probe(script: str, *, seed: str = "0") -> str:
    """Run *script* in a fresh interpreter with a chosen hash seed, and return stdout."""
    import scistudio

    src_root = os.path.dirname(os.path.dirname(os.path.abspath(scistudio.__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([src_root, env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["PYTHONHASHSEED"] = seed
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120, check=False
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


# ---------------------------------------------------------------------------
# FR-004 — purity, asserted rather than asserted about
# ---------------------------------------------------------------------------

PURITY_NOTEBOOK = (
    ("c1", "import pandas as pd\ndf = pd.read_csv('f')\n"),
    ("c2", "%pip install x\ndf = df[df.a > 1]\n"),
    ("c3", "df.dropna(inplace=True)"),
    ("c4", "scistudio.output(table=df)\nblocks.run('peak-finder', df)\n"),
    ("c5", "from numpy import *"),
    ("c6", "broken = ("),
)


def _refuse(name: str) -> Callable[..., object]:
    def boom(*args: object, **kwargs: object) -> object:
        raise AssertionError(f"FR-004: the analysis reached {name}, which it must never do")

    return boom


def test_fr004_the_analysis_executes_nothing_and_touches_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-004: source in, facts and graph out. Nothing runs, nothing is read from disk.

    A comment saying the module is pure is worth less than a test that removes
    the ability to be impure. ``open``, ``exec``, ``eval``, ``os.open`` and
    ``subprocess.Popen`` are replaced with functions that raise, and the whole
    analysis — every flag path, the graph, the queries, and the codec — is driven
    with them in place.

    ``compile`` is *not* patched. :func:`ast.parse` is a call to it, and
    compiling source is not executing it; FR-004 forbids execution, a kernel, and
    the filesystem, and each of those is covered above.
    """
    monkeypatch.setattr(builtins, "open", _refuse("open"))
    monkeypatch.setattr(builtins, "exec", _refuse("exec"))
    monkeypatch.setattr(builtins, "eval", _refuse("eval"))
    monkeypatch.setattr(io, "open", _refuse("io.open"))
    monkeypatch.setattr(os, "open", _refuse("os.open"))
    monkeypatch.setattr(subprocess, "Popen", _refuse("subprocess.Popen"))

    facts = analyse_cells(PURITY_NOTEBOOK)
    graph = build_graph(
        facts,
        enabled={"c5": False},
        observations={"c3": ObservedChange("c3", frozenset({"df"}), frozenset(), facts[2].source_hash)},
    )
    graph.downstream("c1")
    graph.backward_slice(["c4"])
    graph.definer_for("c4", "df")
    graph.changed_set("c3")
    record = encode_cell_record(facts[2])
    decode_cell_record("c3", PURITY_NOTEBOOK[2][1], record)
    observation_flags(facts[2], ObservedChange("c3", frozenset({"df"}), frozenset({"handle"}), facts[2].source_hash))
    assert graph.cells


def test_fr004_the_fingerprint_executes_nothing_and_touches_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-004: the fingerprint is pure over the object it is given.

    The values and the lazy ``xxhash`` import are built *before* the patch. An
    import is the one file read the module makes and the interpreter makes it
    once per process rather than the fingerprint making it per call; and pandas
    itself reaches ``exec`` while constructing a frame, which would otherwise
    make this test about the fixture rather than about the fingerprint.
    """
    values = {
        "frame": pd.DataFrame({"a": [1.0, None], "b": ["x", "y"]}),
        "series": pd.Series([1, 2, 3]),
        "array": np.arange(64).reshape(8, 8),
        "nested": {"k": [1, (2, 3), {4, 5}], "b": b"bytes"},
        "opaque": object(),
    }
    fingerprint(0)  # warm the lazy xxhash import; see the docstring

    monkeypatch.setattr(builtins, "open", _refuse("open"))
    monkeypatch.setattr(builtins, "exec", _refuse("exec"))
    monkeypatch.setattr(builtins, "eval", _refuse("eval"))
    monkeypatch.setattr(io, "open", _refuse("io.open"))
    monkeypatch.setattr(os, "open", _refuse("os.open"))
    monkeypatch.setattr(subprocess, "Popen", _refuse("subprocess.Popen"))

    before = {name: fingerprint(value) for name, value in values.items()}
    after = {name: fingerprint(value) for name, value in values.items()}
    observed = compare_namespaces(before, after, cell_id="c1", source_hash="abc")
    assert observed.changed_names == frozenset()
    assert observed.unobservable_names == frozenset({"opaque"})


def test_fr004_the_fingerprint_does_not_change_the_object_it_reads() -> None:
    """FR-004: pure means the value is the same afterwards, not merely undamaged.

    A generator or an iterator would be consumed by a fingerprint that walked it;
    the type allowlist is what prevents that, and this is the assertion that the
    allowlist is doing it. A ``dict`` and a ``set`` are included because their
    sampling path *iterates* them, which is where a careless implementation would
    reach for ``pop``.
    """
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": ["x", "y"]})
    mapping = {"a": 1, "b": 2}
    members = {1, 2, 3}
    sequence = [1, [2], (3,)]
    array = np.arange(10)

    snapshot = (frame.to_csv(), dict(mapping), set(members), [1, [2], (3,)], array.copy())
    for value in (frame, mapping, members, sequence, array):
        fingerprint(value)

    assert frame.to_csv() == snapshot[0]
    assert mapping == snapshot[1]
    assert members == snapshot[2]
    assert sequence == snapshot[3]
    assert np.array_equal(array, snapshot[4])


# ---------------------------------------------------------------------------
# FR-017 — determinism, in a process that has never seen these inputs
# ---------------------------------------------------------------------------

DETERMINISM_PROBE = """
import json
from scistudio.explore.dependency_analysis import analyse_cells, build_graph, encode_cell_record

cells = [
    ("c1", "import pandas as pd\\nfrom numpy import *\\ndf = pd.read_csv('f')\\nlookup, spare = load()\\n"),
    ("c2", "df = df[df.zeta > 1]\\ntotal += 1\\n"),
    ("c3", "df.dropna(inplace=True)"),
    ("c4", "alpha = arange(3)\\nomega = df.head()\\ndel spare\\n"),
    ("c5", "scistudio.output(table=df, alpha=alpha, omega=omega)"),
]
facts = analyse_cells(cells)
graph = build_graph(facts, observations={"c3": {"df", "gamma"}})
payload = {
    "cells": list(graph.cells),
    "edges": [[e.reader, e.definer, e.name, e.origin.value] for e in graph.edges],
    "unresolved": [[r.cell_id, r.name] for r in graph.unresolved_reads],
    "version_nodes": [[v.cell_id, v.name] for v in graph.version_nodes],
    "version_edges": [
        [v.source.cell_id, v.source.name, v.target_cell, None if v.target is None else v.target.name, v.origin.value]
        for v in graph.version_edges
    ],
    "unknown_binding_cells": list(graph.unknown_binding_cells),
    "changed_set_keys": list(graph.changed_sets),
    "downstream": {c: list(graph.downstream(c)) for c in graph.cells},
    "slice": list(graph.backward_slice(["c5"]).cells),
    "definers": [[c, graph.definer_for(c, "df")] for c in graph.cells],
    "records": [encode_cell_record(f) for f in facts],
    "flags": [[[x.flag.value, x.message, x.name, x.lineno, x.offset] for x in f.flags] for f in facts],
}
print(json.dumps(payload, sort_keys=True))
"""


def test_fr017_the_graph_is_identical_in_two_fresh_processes() -> None:
    """FR-017: a deterministic function of source, order, enabled flags, and observations.

    Built twice, in two interpreters started with different ``PYTHONHASHSEED``
    values, over a notebook that exercises every ordered collection the API
    exposes: the cells, the edges and their origins, the unresolved reads, the
    version nodes and version edges, the unknown-binding cells, the key order of
    ``changed_sets``, all four queries, and the encoded records. Same process,
    same run is not a determinism test — every set in the module iterates
    identically inside one process, which is the one place the question does not
    arise.
    """
    first = run_probe(DETERMINISM_PROBE, seed="0")
    second = run_probe(DETERMINISM_PROBE, seed="524287")
    assert json.loads(first) == json.loads(second)
    assert first == second, "the ordered collections must be byte-identical, not merely equal as sets"


def test_fr017_the_facts_are_a_function_of_the_source_not_of_the_call_order() -> None:
    """FR-017: analysing a cell twice, and analysing it after its neighbours, agree."""
    source = "df = df[df.a > 1]\nlookup = build(df)\n"
    alone = analyse_cell("c2", source)
    in_context = analyse_cells([("c1", "df = load()"), ("c2", source), ("c3", "use(lookup)")])[1]
    assert alone == in_context


def test_fr024_a_large_set_fingerprints_differently_in_two_processes() -> None:
    """FINDING P3 — the fingerprint of a set above the sample bound is process-dependent.

    A set larger than :attr:`FingerprintBudget.container_items` is sampled by
    striding its *iterator*, and a set of strings iterates in an order that
    depends on ``PYTHONHASHSEED``. Different processes therefore sample different
    members and produce different digests for the same value. Below the bound the
    whole set is folded by XOR and the digest is stable.

    This is documented rather than failed. FR-024 asks the fingerprint to be
    equal for an unchanged object, and every use in this spec compares two
    snapshots taken inside one kernel process, where the seed is fixed and the
    property holds. It matters only if a digest is ever persisted or compared
    across processes — which FR-031's record does not do, it stores changed
    *names* — so the honest place for it is a test that states the boundary
    rather than a failure that would ask for a fix nothing needs.
    """
    probe = (
        "from scistudio.explore.fingerprint import fingerprint\n"
        "print(fingerprint({f'name-{i}' for i in range(4000)}).digest)\n"
        "print(fingerprint({f'name-{i}': i for i in range(4000)}).digest)\n"
        "print(fingerprint([f'name-{i}' for i in range(4000)]).digest)\n"
        "print(fingerprint({f'name-{i}' for i in range(64)}).digest)\n"
    )
    first = run_probe(probe, seed="0").splitlines()
    second = run_probe(probe, seed="524287").splitlines()
    assert first[0] != second[0], "if this passes the sampling became stable and the docstring is stale"
    assert first[1] == second[1], "a dict iterates in insertion order, so its sample is stable"
    assert first[2] == second[2], "a list is indexed, so its sample is stable"
    assert first[3] == second[3], "a set below the bound is folded whole, so its digest is stable"


# ---------------------------------------------------------------------------
# FR-002 / FR-030 — the union, attacked with an observation that would remove an edge
# ---------------------------------------------------------------------------


def test_fr030_an_observation_that_names_a_different_set_cannot_move_the_definer() -> None:
    """FR-002, FR-030: an observation adds; it never replaces.

    The existing suite proves the union survives an observation that is a
    *subset* of the estimate, which a replacement would also survive whenever the
    subset still holds the name under test. This is the construction a
    replacement fails: cell 2's source assigns ``df``, its observation names only
    ``log`` — the conditional never fired, but the cell appended to a log — and a
    replacement would leave ``df``'s nearest definer as cell 1 rather than cell 2.
    """
    cells = [
        ("c1", "df = load()"),
        ("c2", "if flag:\n    df = transform(df)\nlog.append(1)\n"),
        ("c3", "peaks = find(df)"),
    ]
    facts = analyse_cells(cells)
    assert "df" in facts[1].assigned
    graph = build_graph(facts, observations={"c2": {"log"}})
    assert graph.definer_for("c3", "df") == "c2"
    assert ("c3", "c2", "df") in edge_tuples(graph)
    assert graph.changed_set("c2") == frozenset({"df", "log"})


def test_fr030_an_observation_cannot_move_a_definer_by_naming_nothing_at_all() -> None:
    """FR-030: an empty observation is not a claim that the cell changed nothing."""
    cells = [("c1", "df = load()"), ("c2", "if flag:\n    df = transform(df)\n"), ("c3", "peaks = find(df)")]
    graph = build_graph(analyse_cells(cells), observations={"c2": frozenset()})
    assert graph.definer_for("c3", "df") == "c2"


def test_fr030_a_stale_observation_cannot_add_a_definer_either() -> None:
    """FR-027 with FR-030: the union is over the *current* observation only."""
    cells = [("c1", "df = load()"), ("c2", "note = 1"), ("c3", "peaks = find(df)")]
    facts = analyse_cells(cells)
    stale = ObservedChange("c2", frozenset({"df"}), frozenset(), source_hash("something else entirely"))
    graph = build_graph(facts, observations={"c2": stale})
    assert graph.definer_for("c3", "df") == "c1"
    assert "df" not in graph.changed_set("c2")


# ---------------------------------------------------------------------------
# FR-015 — the nearest enabled definer, and the four ways to get it wrong
# ---------------------------------------------------------------------------


def test_fr015_a_definer_below_the_reader_is_not_a_definer() -> None:
    """FR-015: *above* is part of the rule. A later binding cannot satisfy an earlier read."""
    graph = graph_of(("c1", "peaks = find(df)"), ("c2", "df = load()"))
    assert edge_tuples(graph) == set()
    assert ("c1", "df") in unresolved_names(graph)


def test_fr015_a_read_that_shadows_a_builtin_still_draws_an_edge() -> None:
    """FR-015: the builtins exemption applies only when no cell above binds the name.

    A notebook that writes ``list = df.columns.tolist()`` has rebound ``list``,
    and a cell below reading ``list`` reads *that* value. Resolving to the
    builtin instead would drop the edge and with it the stale mark.
    """
    graph = graph_of(("c1", "list = load()"), ("c2", "first = list[0]"), ("c3", "count = len(first)"))
    assert ("c2", "c1", "list") in edge_tuples(graph)
    assert ("c3", "c2", "first") in edge_tuples(graph)
    assert unresolved_names(graph) == {("c1", "load")}, "list resolved to cell 1; only the genuine gap is listed"
    assert "len" not in {name for _, name in unresolved_names(graph)}, "len is still the builtin nobody rebound"


def test_fr015_a_builtin_read_before_the_cell_that_shadows_it_draws_no_edge() -> None:
    """FR-015: the reader above the shadowing cell genuinely does read the builtin."""
    graph = graph_of(("c1", "n = len(rows)"), ("c2", "len = 5"), ("c3", "m = len"))
    assert ("c1", "c2", "len") not in edge_tuples(graph)
    assert ("c3", "c2", "len") in edge_tuples(graph)
    assert {name for _, name in unresolved_names(graph)} == {"rows"}


def test_fr015_a_name_defined_twice_resolves_to_the_nearer_definition() -> None:
    """US1 scenario 2 / FR-015: the nearer of the two, and no other."""
    graph = graph_of(("c1", "df = load()"), ("c2", "df = df.dropna()"), ("c3", "peaks = find(df)"))
    assert ("c3", "c2", "df") in edge_tuples(graph)
    assert ("c3", "c1", "df") not in edge_tuples(graph)
    assert graph.definer_for("c3", "df") == "c2"


def test_fr015_a_self_read_never_resolves_to_the_cell_itself() -> None:
    """US1 scenario 3: ``df = df.dropna()`` reads the ``df`` above, never its own."""
    graph = graph_of(("c1", "df = load()"), ("c2", "df = df.dropna()"))
    assert ("c2", "c2", "df") not in edge_tuples(graph)
    assert ("c2", "c1", "df") in edge_tuples(graph)


def test_fr015_two_disabled_definers_are_skipped_to_reach_a_third() -> None:
    """FR-014, FR-015: the rule walks past every disabled cell, not just one."""
    graph = build_graph(
        analyse_cells(
            [
                ("c1", "df = load()"),
                ("c2", "df = variant_a(df)"),
                ("c3", "df = variant_b(df)"),
                ("c4", "peaks = find(df)"),
            ]
        ),
        enabled={"c2": False, "c3": False},
    )
    assert graph.definer_for("c4", "df") == "c1"
    assert ("c4", "c1", "df") in edge_tuples(graph)


def test_fr015_a_read_only_the_cell_itself_binds_is_not_reported_unresolved() -> None:
    """FINDING P2, open and tracked as ``#2243`` — an exception FR-015 does not authorise.

    FR-015 admits exactly one exception to "a read with no enabled definer above
    it MUST be recorded as unresolved": a name in Python's builtins.
    :func:`build_graph` adds a second — a read of a name the *reading cell's own*
    changed set contains.

    The justification is a cell that binds a name and then uses it, which is how
    people write: ``import pandas as pd`` followed in the same cell by
    ``df = pd.read_csv('f')``, ``total = 0`` followed by ``total += 1``,
    ``def f(n): return f(n - 1)``. Without the exception every one of those would
    report its own name unresolved and packaging would refuse the notebook. A
    *bare* ``import pandas as pd`` would not, and the source comment used to cite
    exactly that: :mod:`symtable` reports ``pd`` there as imported and *not*
    referenced, so the cell reads nothing and this branch is never reached. Both
    ADR-054 spec 2 audits measured the claim and found it false; the second
    assertion below is the proof, and the comment now names the real case.

    What the exception does reach is a first cell that says ``df = df.dropna()``,
    which raises ``NameError`` the moment it runs and which US2 scenario 5 exists
    so that packaging can refuse.

    This test documents the behaviour rather than failing, because removing the
    exception outright would report ``total`` unresolved for the equally ordinary
    ``total = 0; total += 1``, and telling the two apart needs the statement order
    FR-001 forbids the analysis to model. Spec and product genuinely disagree and
    the resolution is the owner's — either FR-015 gains this exception or FR-001
    gains a narrow within-cell ordering rule — which is why this ``FINDING`` line
    is still in the present tense while the rest of this file's are not. The
    thread back to the decision is ``TODO(#2243)`` beside the exception in
    :func:`build_graph`.
    """
    graph = graph_of(("c1", "df = df.dropna()"), ("c2", "peaks = find(df)"))
    assert unresolved_names(graph) == {("c2", "find")}, "df is not listed, and running this notebook fails on it"

    lone_import = analyse_cell("c1", "import pandas as pd")
    assert lone_import.read == frozenset(), "the exception's stated justification does not arise"


def test_fr006_a_global_augmented_assignment_inside_a_function_is_a_module_read() -> None:
    """FINDING P1, closed: a nested-scope read FR-006 requires, now recorded.

    FR-006: "the names the cell reads at module scope, **including names read
    inside a nested scope that resolve to the module scope**". ``counter += 1``
    under a ``global counter`` declaration reads ``counter``; :mod:`symtable`
    reports that symbol as assigned and global but not as referenced.

    This test was written failing. ``_collect_module_level_reads`` — which exists
    precisely because :mod:`symtable` under-reports augmented assignment and
    ``del`` — walked only the module level and never entered a function body, so
    cell 3 of ``tests/explore/fixtures/global_counter.ipynb`` was a definer of
    ``counter`` that read nothing, its backward slice omitted the cell that
    initialises the counter, and running the slice raised ``NameError``. The
    fixture's differential test failed alongside this one; this test was the
    isolated cause.

    It is closed. ``_collect_module_level_reads`` now walks every ``def`` and
    ``class``, reads the names that scope declares ``global``, and counts the
    augmented assignments and deletions among them as module reads — the repair
    it already made at module scope, extended to a nested scope's ``global``
    names. ``test_sc003_global_counter_slice_reproduces_the_notebook`` is the
    end-to-end proof.
    """
    facts = analyse_cell("c2", "def bump():\n    global counter\n\n    counter += 1\n")
    assert "counter" in facts.assigned, "the global assignment is recorded, which is why the edge misleads"
    assert "counter" in facts.read


def test_fr006_a_global_del_inside_a_function_is_a_module_read() -> None:
    """FINDING P2, closed: the ``del`` half of the same blind spot.

    ``del counter`` under a ``global`` declaration requires ``counter`` to exist,
    exactly as ``counter += 1`` does, and was missed for the same reason. It was
    filed separately because a repair aimed only at :class:`ast.AugAssign` would
    have left it standing; ``_augmented_and_deleted_names`` covers both forms, so
    it did not.
    """
    facts = analyse_cell("c2", "def drop():\n    global counter\n\n    del counter\n")
    assert "counter" in facts.read


# ---------------------------------------------------------------------------
# FR-011 to FR-013, FR-036 — the flags, and the cells nobody types on purpose
# ---------------------------------------------------------------------------


def test_fr011_a_cell_that_is_only_a_magic_line_analyses_to_nothing_and_raises_no_flag() -> None:
    """FR-011: a stripped magic line does not by itself produce an error flag."""
    facts = analyse_cell("c1", "%pip install scikit-image\n")
    assert facts.assigned == frozenset()
    assert facts.read == frozenset()
    assert facts.flags == ()


def test_fr011_a_cell_magic_whose_body_is_valid_python_is_still_opaque() -> None:
    """FR-011 / US5 scenario 2, and the cost of the rule, stated where it is visible.

    ``%%time`` over a perfectly ordinary assignment makes the whole cell opaque:
    it assigns nothing, so a cell below that reads ``df`` has no definer and the
    read is reported unresolved. That is FR-011 working as written — the analysis
    has no way to know what a cell magic does to the body it wraps — and the
    second half of this test is here so the consequence is on the record rather
    than discovered by the first person to package such a notebook.
    """
    facts = analyse_cell("c1", "%%time\ndf = load()\npeaks = find(df)\n")
    assert facts.assigned == frozenset()
    assert facts.read == frozenset()
    assert facts.flag_kinds == frozenset({AnalysisFlag.OPAQUE_CELL_MAGIC})

    graph = graph_of(("c1", "%%time\ndf = load()\n"), ("c2", "peaks = find(df)"))
    assert ("c2", "df") in unresolved_names(graph)


def test_fr012_a_syntax_error_on_the_last_line_is_flagged_with_its_position() -> None:
    """FR-012: the flag carries the parser's message and position, wherever the break is."""
    facts = analyse_cell("c1", "df = load()\npeaks = find(\n")
    assert facts.flag_kinds == frozenset({AnalysisFlag.SYNTAX_ERROR})
    assert facts.assigned == frozenset()
    assert facts.flags[0].lineno is not None
    assert facts.flags[0].message


def test_fr013_a_star_import_and_an_unresolved_read_resolve_to_the_star_import() -> None:
    """FR-013 / US5 scenario 4, including the builtin the star import shadows.

    The unknown-binding resolution runs *ahead* of the builtins exemption, so a
    read of ``sum`` below ``from numpy import *`` draws an edge to the star
    import rather than silently resolving to the builtin. That is FR-002's
    "resolve toward the extra edge" applied to a case where the star import
    genuinely does shadow the builtin.
    """
    graph = graph_of(
        ("c1", "from numpy import *"),
        ("c2", "alpha = arange(3)"),
        ("c3", "total = sum(alpha)"),
    )
    assert ("c2", "c1", "arange") in edge_tuples(graph)
    assert ("c3", "c1", "sum") in edge_tuples(graph)
    assert unresolved_names(graph) == set()
    assert all(edge.origin is EdgeOrigin.UNKNOWN_BINDING for edge in graph.edges if edge.name in {"arange", "sum"})


def test_fr013_a_run_magic_binds_unknown_names_the_same_way() -> None:
    """FR-013: ``%run`` is the other unknown binder, and it must reach a read below it."""
    graph = graph_of(("c1", "%run setup.py"), ("c2", "peaks = find(df)"))
    assert ("c2", "c1", "df") in edge_tuples(graph)
    assert unresolved_names(graph) == set()


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("empty", ""),
        ("blank lines only", "\n\n   \n"),
        ("comment only", "# a note the person left\n"),
        ("comment then blank", "# a note\n\n"),
        ("magic only", "%pip install x\n"),
        ("shell only", "!ls -la\n"),
        ("bare cell magic", "%%time"),
        ("docstring only", '"""just prose"""\n'),
    ],
)
def test_a_cell_with_no_code_analyses_without_incident(label: str, source: str) -> None:
    """FR-012's neighbourhood: an empty or contentless cell is not an error.

    Each of these is a cell a person leaves behind while writing, and each must
    analyse to an empty estimate, an empty read set, and — for everything but the
    cell magic, which FR-011 requires to be marked opaque — no flag at all.
    """
    facts = analyse_cell("c1", source)
    assert facts.assigned == frozenset(), label
    assert facts.read == frozenset(), label
    expected = frozenset({AnalysisFlag.OPAQUE_CELL_MAGIC}) if source.lstrip().startswith("%%") else frozenset()
    assert facts.flag_kinds == expected, label


def test_a_non_ascii_identifier_binds_and_reads_like_any_other() -> None:
    """FR-005, FR-006: the analysis is over Python identifiers, not over ASCII.

    The users this feature targets write variable names in their own script, and a
    binding form that stops being recognised because of the alphabet it is
    spelled in would drop edges silently.
    """
    graph = graph_of(
        ("c1", "数据 = load()\n阈值 = 1.0\n"),
        ("c2", "峰值 = find(数据, 阈值)"),
        ("c3", "scistudio.output(peaks=峰值)"),
    )
    assert ("c2", "c1", "数据") in edge_tuples(graph)
    assert ("c2", "c1", "阈值") in edge_tuples(graph)
    assert graph.backward_slice(["c3"]).cells == ("c1", "c2", "c3")


def test_a_very_long_cell_is_analysed_in_one_pass() -> None:
    """FR-018's neighbourhood: cost is linear in names, including inside one cell.

    A cell with five thousand assignments is what a generated notebook or a
    pasted parameter block looks like. It must be analysed, not truncated, and it
    must not be the thing that makes a notebook load feel broken.
    """
    source = "\n".join(f"n{index} = {index}" for index in range(5000))
    started = time.perf_counter()
    facts = analyse_cell("c1", source)
    elapsed = time.perf_counter() - started
    assert len(facts.assigned) == 5000
    assert facts.flags == ()
    assert elapsed < 5.0, f"analysing one 5000-statement cell took {elapsed * 1000:.0f} ms"


def test_a_deeply_nested_cell_does_not_break_the_module_level_walk() -> None:
    """FR-012: ``_iter_module_level`` recurses, and a deep cell must not be how that is found out."""
    depth = 40
    source = "".join("    " * level + f"if flag{level}:\n" for level in range(depth))
    source += "    " * depth + "df = load()\n"
    facts = analyse_cell("c1", source)
    assert "df" in facts.assigned
    assert facts.flags == ()


def test_fr012_a_cell_holding_an_unpaired_surrogate_is_flagged_rather_than_raising() -> None:
    """FINDING P2, closed: ``analyse_cell`` used to raise on a cell a notebook can hold.

    FR-012 requires a cell that does not parse to be *recorded* with the
    syntax-error flag and forbids it from preventing any other cell being
    analysed, and :func:`analyse_cell` says in its own docstring that it never
    raises. It did. ``source_hash`` is computed before the ``try`` and encoded as
    strict UTF-8, so a cell containing an unpaired surrogate raised
    ``UnicodeEncodeError`` straight out of ``analyse_cells`` and took the whole
    notebook load with it.

    ``json.loads('"\\\\ud800"')`` returns exactly such a string, so an ``.ipynb``
    written by anything that escaped a lone surrogate reaches the analysis this
    way; the fingerprint module already encoded with ``surrogatepass`` for the
    same reason, which is where the asymmetry showed.

    One ``errors="surrogatepass"`` on the hash was the difference, and it is what
    closed this: the cell now comes back flagged, and the cell beside it is
    analysed as if nothing had happened, which is the half of FR-012 that
    matters.
    """
    lone_surrogate = json.loads('"\\ud800 = 1"')
    facts = analyse_cells([("c1", lone_surrogate), ("c2", "df = load()")])
    assert facts[0].flag_kinds == frozenset({AnalysisFlag.SYNTAX_ERROR})
    assert facts[1].assigned == frozenset({"df"})


def test_fr011_a_magic_line_inside_a_string_literal_is_left_alone() -> None:
    """The finding above, closed: the strip is lexical, so it stops at a string literal.

    This test was written to record a defect and asserted it: while the strip was
    a line filter over the raw source, a line beginning with ``%`` inside a
    triple-quoted string was removed with the rest, and where that line also
    carried the closing quotes the cell stopped parsing — the very error flag
    FR-011 forbids the strip to produce on its own. Its own docstring said the
    general repair was the one the wrapped-operator finding asked for, and that
    it was recorded here so the repair would be known to cover both.

    It does. FR-011 now identifies a magic by tokenising, and a ``%`` inside a
    string literal is part of that literal's token rather than the first token of
    a logical line. Both halves of the cell survive: the assertions below are the
    inverse of the ones this test was born with, and they are what the narrowed
    rule requires.
    """
    harmless = analyse_cell("c1", 'notes = """\n%matplotlib inline goes here\n"""\ndf = load()\n')
    assert harmless.assigned == frozenset({"notes", "df"})
    assert harmless.flags == ()

    once_harmful = analyse_cell("c2", 'notes = """\n%matplotlib"""\ndf = load()\n')
    assert once_harmful.flags == (), "the strip no longer reaches inside the literal, so it raises nothing"
    assert once_harmful.assigned == frozenset({"notes", "df"}), "df survives, and a read of it below resolves"


def test_fr036_the_seven_flags_are_reachable_and_each_renders_its_own_fields() -> None:
    """FR-036: one enumeration, every member with a message that names what it is about.

    The existing suite checks that each flag *has* a template. This checks that
    the fields the template asks for are the fields the raising site supplies, by
    rendering every one and requiring the cell id and the subject to survive into
    the text. A template whose placeholder nobody fills raises ``KeyError`` at the
    moment a person would have read it.
    """
    rendered = {
        AnalysisFlag.SYNTAX_ERROR: AnalysisFlag.SYNTAX_ERROR.message(cell_id="c1", detail="invalid syntax"),
        AnalysisFlag.OPAQUE_CELL_MAGIC: AnalysisFlag.OPAQUE_CELL_MAGIC.message(cell_id="c1", magic="%%time"),
        AnalysisFlag.UNKNOWN_BINDINGS: AnalysisFlag.UNKNOWN_BINDINGS.message(cell_id="c1", reason="a star import"),
        AnalysisFlag.UNKNOWN_BLOCK_CALL: AnalysisFlag.UNKNOWN_BLOCK_CALL.message(cell_id="c1"),
        AnalysisFlag.UNPREDICTED_CHANGE: AnalysisFlag.UNPREDICTED_CHANGE.message(cell_id="c1", name="df"),
        AnalysisFlag.UNOBSERVABLE_NAME: AnalysisFlag.UNOBSERVABLE_NAME.message(cell_id="c1", name="handle"),
        AnalysisFlag.UNRESOLVED_READ: AnalysisFlag.UNRESOLVED_READ.message(cell_id="c1", name="df"),
    }
    assert set(rendered) == set(AnalysisFlag)
    for flag, message in rendered.items():
        assert "c1" in message, flag
        assert "{" not in message, flag


# ---------------------------------------------------------------------------
# FR-016 — the version graph the dependency view renders
# ---------------------------------------------------------------------------


def test_fr016_every_version_edge_source_is_a_version_node() -> None:
    """FINDING P3, closed: a version edge used to point at a node the graph did not publish.

    FR-016: version nodes are one per name in each enabled cell's changed set, and
    "edges between version nodes [are] derived from the same facts as the edges
    between cells". An unknown-binding edge names a name the star-import cell does
    *not* have in its changed set — a star import binds an unknown set, so its
    changed set is empty — and :func:`_version_edges` built a source node for it
    anyway. The dependency view was handed an edge whose source was not in the
    node list it was given, and every consumer had to discover the dangling
    reference for itself.

    Closed the way FR-002 points: ``build_graph`` tracks the names an
    unknown-binding resolution says a cell produced and publishes a
    ``version_nodes`` entry for each, so the edge keeps its source. The other
    repair — dropping the edge — would have shown the reader unconnected to a
    cell it really does depend on (FR-013).
    """
    graph = graph_of(("c1", "from numpy import *"), ("c2", "alpha = arange(3)"))
    nodes = set(graph.version_nodes)
    dangling = [edge for edge in graph.version_edges if edge.source not in nodes]
    assert dangling == []


def test_fr016_version_edges_agree_with_the_cell_edges_for_an_observed_definer() -> None:
    """FR-016: the observed-change origin reaches the version graph intact.

    The existing agreement test runs over a purely static notebook, where every
    origin is ``static_assignment``; this drives the same assertion through the
    branch an observation creates.
    """
    facts = analyse_cells([("c1", "df = load()"), ("c2", "df.dropna(inplace=True)"), ("c3", "peaks = find(df)")])
    graph = build_graph(facts, observations={"c2": {"df"}})
    assert graph.version_nodes == (
        *(node for node in graph.version_nodes if node.cell_id == "c1"),
        *(node for node in graph.version_nodes if node.cell_id != "c1"),
    )
    observed = [edge for edge in graph.version_edges if edge.origin is EdgeOrigin.OBSERVED_CHANGE]
    assert observed, "the observed-change branch was never taken, so this test proved nothing"
    for edge in observed:
        assert edge.source.cell_id == "c2"
        assert edge.source in set(graph.version_nodes)


# ---------------------------------------------------------------------------
# FR-027 — what an edit does to an observation
# ---------------------------------------------------------------------------


def test_fr027_a_whitespace_only_edit_discards_the_observation() -> None:
    """FR-027, and the cost of keying to the source hash rather than to the parse.

    A trailing newline is a different source hash, so the observation goes and
    the in-place cell stops being a definer of ``df`` until the cell is run again.
    The slice then loses the cell, which is a *smaller* slice than the person
    approved — the one direction FR-002 says the analysis must not resolve
    toward. Nothing here is a defect: the cell is also stale after any edit and
    must run again before it can be packaged, which is the argument §4.1 makes.
    This test exists so that the argument stays true by test rather than by
    memory, and so that any future "the cell is only stale if the *parse*
    changed" optimisation has to face it.
    """
    source = "df.dropna(inplace=True)"
    facts = analyse_cell("c2", source)
    observation = ObservedChange("c2", frozenset({"df"}), frozenset(), facts.source_hash)

    edited = analyse_cell("c2", source + "\n")
    assert edited.source_hash != facts.source_hash
    graph = build_graph(
        [analyse_cell("c1", "df = load()"), edited, analyse_cell("c3", "peaks = find(df)")],
        observations={"c2": observation},
    )
    assert graph.definer_for("c3", "df") == "c1"
    assert graph.backward_slice(["c3"]).cells == ("c1", "c3")


def test_fr027_an_edit_that_restores_the_original_source_restores_the_observation() -> None:
    """FR-027: the key is the source, not the history, so a round trip is a no-op.

    A person who edits a cell and undoes the edit without running it must get the
    graph they had. The observation is keyed to content, so this holds; the test
    is here because an implementation that invalidated on an edit *event* rather
    than on the hash would pass every other FR-027 test and fail this one.
    """
    original = "df.dropna(inplace=True)"
    record = encode_cell_record(
        analyse_cell("c2", original),
        ObservedChange("c2", frozenset({"df"}), frozenset(), source_hash(original)),
    )
    after_edit = decode_cell_record("c2", "pass", record)
    assert after_edit.observation is None
    assert after_edit.reanalysed is True

    after_undo = decode_cell_record("c2", original, record)
    assert after_undo.observation is not None
    assert after_undo.observation.changed_names == frozenset({"df"})
    assert after_undo.reanalysed is False


def test_fr027_two_cells_with_identical_source_share_a_record_shape() -> None:
    """FINDING P3 — a per-cell record carries nothing that ties it to its cell.

    ``encode_cell_record`` deliberately omits the cell id, on the argument that a
    second copy of it could disagree with the cell it is attached to. The
    consequence is that two cells with identical source produce byte-identical
    records, observation included, and a record moved from one to the other
    decodes without complaint — ``decode_cell_record`` takes the cell id from its
    caller and stamps it onto the recovered :class:`ObservedChange`.

    Documented rather than failed. Which record belongs to which cell is the
    notebook's own structure, and the explore-session spec owns loading it; the
    exposure is real only if that binding is ever broken. It is recorded so that
    whoever writes the loader knows the codec will not catch them.
    """
    source = "df.dropna(inplace=True)"
    observation = ObservedChange("c2", frozenset({"df"}), frozenset(), source_hash(source))
    first = encode_cell_record(analyse_cell("c2", source), observation)
    second = encode_cell_record(
        analyse_cell("c4", source), ObservedChange("c4", *list(observation.__dict__.values())[1:])
    )
    assert first == second

    misattributed = decode_cell_record("c4", source, first)
    assert misattributed.observation is not None
    assert misattributed.observation.cell_id == "c4"


def test_fr028_the_unpredicted_change_diagnostic_is_keyed_to_the_current_source() -> None:
    """FR-027 with FR-028: a diagnostic about code the person has since edited is noise."""
    facts = analyse_cell("c2", "clean(df)")
    current = ObservedChange("c2", frozenset({"df"}), frozenset(), facts.source_hash)
    stale = ObservedChange("c2", frozenset({"df"}), frozenset(), source_hash("other"))
    assert [flag.flag for flag in observation_flags(facts, current)] == [AnalysisFlag.UNPREDICTED_CHANGE]
    assert observation_flags(facts, stale) == ()


# ---------------------------------------------------------------------------
# FR-024, FR-025, FR-029 — the fingerprint's honesty
# ---------------------------------------------------------------------------


def test_fr024_an_object_whose_equality_lies_is_still_distinguished() -> None:
    """FR-024: the fingerprint is over content and identity, never over ``__eq__``.

    A value that claims equality with everything must not be able to talk the
    comparison out of reporting a rebinding. The fallback records identity, so
    two distinct instances differ, and the name is reported unobservable so
    nobody reads that difference as proof of a content change.
    """

    class AlwaysEqual:
        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            return 0

    first, second = AlwaysEqual(), AlwaysEqual()
    assert first == second
    assert fingerprint(first) != fingerprint(second)
    assert fingerprint(first).observable is False

    observed = compare_namespaces({"x": fingerprint(first)}, {"x": fingerprint(second)}, cell_id="c1", source_hash="h")
    assert observed.changed_names == frozenset({"x"})
    assert observed.unobservable_names == frozenset({"x"})


def test_fr024_a_lying_equality_inside_a_container_does_not_hide_the_swap() -> None:
    """FR-024: the same, one level down, where a container's own ``==`` would be consulted."""

    class AlwaysEqual:
        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            return 0

    before = [AlwaysEqual()]
    after = [AlwaysEqual()]
    assert before == after
    assert fingerprint(before) != fingerprint(after)


def test_fr024_a_numpy_view_and_its_base_are_separate_values() -> None:
    """FR-024: a view is fingerprinted by the bytes it spans, not by the buffer it borrows.

    A cell that writes ``base[0] = 99`` changed ``base`` and not the slice that
    starts at index two, and the observation must say so or every view in the
    namespace becomes a false definer. The second half is the other direction: a
    write *inside* the view's extent is a change to both.
    """
    base = np.arange(10)
    view = base[2:5]
    before_view, before_base = fingerprint(view), fingerprint(base)

    base[0] = 99
    assert fingerprint(view) == before_view
    assert fingerprint(base) != before_base

    steady = fingerprint(view)
    base[3] = -1
    assert fingerprint(view) != steady


def test_fr024_a_frame_with_unhashable_object_values_is_inspected_by_content() -> None:
    """FR-024: an object column holds pointers, and what they point at is the value.

    A frame whose cells are lists cannot be hashed through its buffer and cannot
    be put in a set. The mutation here is the one a notebook actually performs —
    ``df.at[0, 'a'].append(...)`` — and it rebinds nothing at all.
    """
    frame = pd.DataFrame({"a": [[1, 2], [3, 4]], "b": [{"k": 1}, {"k": 2}]})
    before = fingerprint(frame)
    frame.at[0, "a"].append(9)
    assert fingerprint(frame) != before

    steady = fingerprint(frame)
    frame.at[1, "b"]["k"] = 99
    assert fingerprint(frame) != steady


def test_fr024_nan_is_fingerprint_equal_to_itself_and_minus_zero_is_not_zero() -> None:
    """FR-024: the fingerprint is bit content, which is neither ``==`` nor ``is``.

    Two consequences worth pinning, because each looks like a bug from one angle
    and is the right answer from the other:

    * ``nan != nan``, but a namespace where ``x`` was ``nan`` before and after has
      not changed, and a fingerprint that used ``==`` would report a change on
      every run of every cell for every missing value in the notebook.
    * ``-0.0 == 0.0``, but they are different bit patterns and a cell that turned
      one into the other did something. FR-002 resolves the uncertainty toward the
      extra edge, and this is that direction.
    """
    assert fingerprint(math.nan) == fingerprint(float("nan"))
    assert fingerprint(np.array([np.nan])) == fingerprint(np.array([np.nan]))
    assert fingerprint(0.0) != fingerprint(-0.0)
    assert 0.0 == -0.0

    observed = compare_namespaces(
        {"x": fingerprint(math.nan)}, {"x": fingerprint(float("nan"))}, cell_id="c1", source_hash="h"
    )
    assert observed.changed_names == frozenset()


def test_fr024_an_equal_dict_in_a_different_insertion_order_reports_a_change() -> None:
    """FR-024 against FR-002: a dict is fingerprinted in iteration order, so a reorder shows.

    ``{'a': 1, 'b': 2} == {'b': 2, 'a': 1}`` and their fingerprints differ, so a
    cell that rebuilt a dict in another order is recorded as having changed it.
    That is a false observation in the strict sense and the safe direction in the
    spec's sense — it adds an edge — but it qualifies "a rebinding to an equal
    value is not reported", which is only true for values whose equality and
    whose content agree.
    """
    first = {"a": 1, "b": 2}
    second = {"b": 2, "a": 1}
    assert first == second
    assert fingerprint(first) != fingerprint(second)


def test_fr025_an_array_above_the_bound_misses_a_change_off_its_stride() -> None:
    """FR-025 and §4.5: the admitted miss, documented rather than pretended away.

    An array larger than :attr:`FingerprintBudget.whole_content_bytes` is sampled
    at a fixed stride. A single element changed between two sampled positions is
    not seen, and the spec's own risk register says so. The purpose of this test
    is to keep that statement true by measurement, and to assert the two things
    that make it survivable:

    * the first and the last element are always sampled, so a change at either
      end of the array is still caught; and
    * FR-002's union means a missed observation can only leave the graph where the
      static estimate put it — never remove an edge the estimate drew.

    If this test ever fails because the mutation *is* detected, the fingerprint
    got better and the docstring, not the assertion, is what needs rewriting.
    """
    size = 3_000_000
    assert size > FINGERPRINT_BUDGET.whole_content_bytes

    array = np.zeros(size, dtype=np.int8)
    before = fingerprint(array)
    array[1] = 7
    assert fingerprint(array) == before, "the admitted miss: index 1 falls between two sampled positions"

    ends = np.zeros(size, dtype=np.int8)
    at_ends = fingerprint(ends)
    ends[0] = 7
    assert fingerprint(ends) != at_ends
    ends[0] = 0
    ends[-1] = 7
    assert fingerprint(ends) != at_ends

    facts = analyse_cells([("c1", "big = build()"), ("c2", "big = reshape(big)"), ("c3", "out = use(big)")])
    graph = build_graph(facts, observations={"c2": frozenset()})
    assert graph.definer_for("c3", "big") == "c2", "the union keeps the static edge the missed observation would lose"


def test_fr025_a_frame_above_the_row_bound_misses_a_change_off_its_stride() -> None:
    """FR-025 and §4.5: the same admitted miss for a frame, whose rows are sampled by count.

    A frame long enough to be sampled by row loses a single edited cell between
    two strides. Recorded for the same reason as the array case: the bound is
    chosen so that ordinary frames are hashed whole, and the boundary is where a
    person is entitled to know what the observation stops covering.
    """
    rows = 400_000
    frame = pd.DataFrame({"v": np.zeros(rows)})
    before = fingerprint(frame)
    frame.iloc[1, 0] = 5.0
    assert fingerprint(frame) == before, "the admitted miss: row 1 falls between two sampled rows"

    tail = pd.DataFrame({"v": np.zeros(rows)})
    at_tail = fingerprint(tail)
    tail.iloc[-1, 0] = 5.0
    assert fingerprint(tail) != at_tail, "FR-025: the sample spans the full extent, so the last row is seen"


def test_fr025_a_container_above_the_bound_is_sampled_across_its_full_extent() -> None:
    """FINDING P1, closed: the container sample is a stride across the extent, not a prefix.

    FR-025: above the bound "the content is sampled at fixed strides **across its
    full extent**", and ``_stride_indices``' own docstring says the property
    "holds literally". It did not. The function computed ``step = length // keep``
    and then truncated the resulting index list to ``keep`` entries, so the
    sampled positions stopped at ``(keep - 1) * step`` and the tail index was
    appended alone. For a 1000-element list and a ``container_items`` of 512 the
    step was 1 and the sample was indices 0 to 511 plus 999: **every position
    from 512 to 998 was invisible**, which is half the list. The gap existed for
    any length that is not a multiple of ``keep`` and was widest just under twice
    it.

    A list of a thousand numbers is not a large object; it is what a notebook
    holds. A cell that wrote ``values[600] = 0`` changed it, the fingerprint
    reported no change, the cell was not a definer, and nothing below it was
    marked stale — the stale number ADR-054 §6.1 was written to remove. That is
    outside the miss §4.5 admits, because §4.5 admits a *stride*, and a stride
    across 1000 positions with 513 samples cannot skip 487 consecutive ones.

    Closed by striding at ``ceil(length / keep)`` and taking the indices from
    ``range(0, length, step)`` with no truncation, since a step that already
    bounds the count does not need one. The same repair reached the dict and set
    path a round later, where the floor step also lost the final entry entirely;
    ``test_the_sample_spans_the_full_extent_of_a_mapping`` is its counterpart.
    """
    keep = FINGERPRINT_BUDGET.container_items
    values = list(range(2 * keep - 24))
    before = fingerprint(values)
    values[keep + 88] = -1
    assert fingerprint(values) != before


def test_fr029_the_unobservable_report_survives_a_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-029: one unreachable value anywhere in a value makes the whole name unobservable."""

    class Opaque:
        pass

    assert fingerprint({"rows": [1, 2, Opaque()]}).observable is False
    assert fingerprint(pd.DataFrame({"a": [Opaque()]})).observable is False
    assert fingerprint({"rows": [1, 2, 3]}).observable is True


def test_fr029_a_value_that_raises_on_inspection_is_unobservable_not_an_exception() -> None:
    """FR-024, FR-029: a broken value is a value the observation does not cover, not a crash.

    A closed memory map, a lazy column, a subclass with a wrong ``__len__``: the
    fingerprint must come back with an honest "I cannot see this one" rather than
    turning a readable namespace into a traceback the person cannot act on.
    """

    class BrokenList(list):
        def __len__(self) -> int:
            raise RuntimeError("no length here")

    class BrokenFrame(pd.DataFrame):
        @property
        def shape(self) -> tuple[int, ...]:
            raise RuntimeError("no shape here")

    for value in (BrokenList([1, 2]), BrokenFrame({"a": [1]})):
        result = fingerprint(value)
        assert result.observable is False
        assert result.digest


# ---------------------------------------------------------------------------
# Assertions weaker than the coverage they claim — the mutation survivors
# ---------------------------------------------------------------------------


def test_survivor_downstream_never_reaches_the_starting_cell() -> None:
    """Mutation survivor, reclassified: ``seen.discard(start)`` in ``downstream`` is dead code.

    Deleting that line leaves the whole suite green, and
    ``test_downstream_does_not_contain_the_cell_itself`` passes either way,
    because edges only ever point at a cell above and the traversal therefore
    cannot come back. So the survivor is an *equivalent* mutant rather than a
    coverage hole, and this test deliberately does not kill it: it asserts the
    property that makes the line dead — the graph is acyclic and every edge runs
    upward — which is the claim worth defending. If a future rule ever draws a
    downward edge, this fails and the discard becomes load-bearing again.
    """
    graph = graph_of(
        ("c1", "df = load()"),
        ("c2", "df = df.dropna()\nlookup = build(df)\n"),
        ("c3", "peaks = find(df, lookup)"),
        ("c4", "df = peaks"),
        ("c5", "final = use(df)"),
    )
    order = {cell_id: index for index, cell_id in enumerate(graph.cells)}
    for edge in graph.edges:
        assert order[edge.definer] < order[edge.reader], f"{edge} runs downward"
    for cell_id in graph.cells:
        assert cell_id not in graph.downstream(cell_id)


def test_survivor_every_member_of_a_set_moves_its_fingerprint() -> None:
    """Mutation survivor: the XOR fold can be replaced by "the last element wins".

    ``_digest_set`` promises an order-independent fold in which a swapped member
    "still moves the result", and the existing tests are satisfied by a fold that
    keeps only the element the iterator happened to yield last. This replaces each
    member in turn, which no such fold survives.
    """
    members = {"alpha", "beta", "gamma", "delta", "epsilon"}
    before = fingerprint(members)
    for member in sorted(members):
        swapped = (members - {member}) | {f"{member}-changed"}
        assert fingerprint(swapped) != before, f"replacing {member} left the digest where it was"
    assert fingerprint(set(members)) == before


def test_survivor_a_long_string_is_sampled_to_its_last_character() -> None:
    """Mutation survivor: the sampled *string* tail is fed by code nothing tested.

    ``test_the_sample_spans_the_full_extent_of_...`` covers an array, a container
    and a frame. A string above the whole-content bound takes its own path, and
    dropping the final character from that path left the suite green.
    """
    length = 2 * FINGERPRINT_BUDGET.whole_content_bytes
    text = "a" * length
    before = fingerprint(text)
    assert fingerprint(text[:-1] + "b") != before
    assert fingerprint("b" + text[1:]) != before


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("except", "try:\n    risky()\nexcept Exception:\n    total += 1\n"),
        ("except del", "try:\n    risky()\nexcept Exception:\n    del total\n"),
        ("match case", "match value:\n    case 1:\n        total += 1\n"),
        ("match case del", "match value:\n    case 1:\n        del total\n"),
    ],
)
def test_survivor_an_augmented_assignment_inside_an_except_or_match_body_is_a_read(label: str, source: str) -> None:
    """Mutation survivor: ``_iter_module_level``'s descent into the two non-``stmt`` bodies.

    ``ast.ExceptHandler`` and ``ast.match_case`` are not statements, so
    ``iter_child_nodes`` does not reach their bodies through the ``ast.stmt``
    branch and ``_iter_module_level`` names them explicitly. Deleting that branch
    left the whole suite green while ``total += 1`` inside an ``except`` stopped
    being a read of ``total``.

    The consequence is the one the differential harness exists to catch. A cell
    whose ``except`` body increments a counter is a definer of it that reads
    nothing, the backward slice stops there, the cell that gave the counter its
    initial value is dropped, and the slice raises ``NameError`` — the same
    failure ``global_counter.ipynb`` was written for, in a body nothing walks
    into. Both bodies get both forms, because a repair aimed at ``AugAssign``
    alone would leave ``del`` standing.
    """
    facts = analyse_cell("c2", source)
    assert "total" in facts.read, f"{label}: the body's read of total is not recorded"

    graph = graph_of(("c1", "total = 0"), ("c2", source), ("c3", "scistudio.output(n=total)"))
    assert graph.backward_slice(["c3"]).cells == ("c1", "c2", "c3"), f"{label}: the slice dropped the initialiser"


def test_survivor_a_long_string_is_sampled_across_its_stride_not_its_prefix() -> None:
    """Mutation survivor: the string *stride* was covered by nothing, only its tail.

    ``_digest_text`` takes ``obj[::step]`` and then the final character. The test
    above pins the tail, and the array and frame strides have tests of their own,
    but replacing the string stride with a plain ``obj[:keep]`` prefix left the
    whole suite green — a change anywhere in the middle of a long string was
    invisible to every assertion in it.

    The changed position is a multiple of the step, which is what the stride
    visits, and lies far beyond ``sample_bytes`` characters, which is where a
    prefix stops.
    """
    length = 2 * FINGERPRINT_BUDGET.whole_content_bytes
    step = length // FINGERPRINT_BUDGET.sample_bytes
    position = step * (FINGERPRINT_BUDGET.sample_bytes // 2)
    assert position > FINGERPRINT_BUDGET.sample_bytes, "a prefix of the sample must not reach the change"

    text = "a" * length
    before = fingerprint(text)
    mutated = text[:position] + "b" + text[position + 1 :]
    assert len(mutated) == length
    assert fingerprint(mutated) != before, "a change on the stride, past the prefix, was missed"


def test_survivor_the_whole_content_clamp_bounds_the_bytes_offered_not_just_accepted() -> None:
    """Mutation survivor: every cost assertion read ``hashed_bytes``, which cannot see this.

    ``_feed`` truncates unconditionally, so ``hashed_bytes`` is bounded however
    much content was *materialised* to produce it — which is why removing
    ``_whole_limit``'s clamp against ``_remaining`` left the suite green. The
    clamp's whole purpose is that a call which has nearly spent its byte ceiling
    takes the sampled route rather than calling ``tobytes()`` on another whole
    megabyte first, and the only way to see that is to watch what is handed to
    ``_feed``.

    Six 0.7 MiB arrays: five fit inside the 4 MiB ceiling whole, and the sixth
    must be sampled because only ~0.6 MiB of the ceiling is left. Without the
    clamp the sixth is copied whole and the bytes offered pass the ceiling.
    """
    offered: list[int] = []
    real_feed = fingerprint_module._feed

    def recording_feed(ctx: Any, data: Any) -> None:
        offered.append(len(data))
        real_feed(ctx, data)

    arrays = [np.zeros(89_600, dtype=np.float64) for _ in range(6)]
    assert arrays[0].nbytes < FINGERPRINT_BUDGET.whole_content_bytes, "each array must take the whole route"

    monkeypatched = pytest.MonkeyPatch()
    try:
        monkeypatched.setattr(fingerprint_module, "_feed", recording_feed)
        context = fingerprint_context(arrays)
    finally:
        monkeypatched.undo()

    assert context.hashed_bytes <= FINGERPRINT_BUDGET.max_total_bytes, "the accepted bytes are bounded either way"
    assert sum(offered) <= FINGERPRINT_BUDGET.max_total_bytes, (
        f"{sum(offered)} bytes were materialised for a {FINGERPRINT_BUDGET.max_total_bytes}-byte ceiling"
    )


def test_survivor_the_flat_handle_reads_an_array_rather_than_copying_it() -> None:
    """Mutation survivor: ``_flat``'s copy-avoidance had no assertion at all.

    ``reshape(-1)`` is a view for C-contiguous data and a **full copy** otherwise,
    which is why ``_flat`` hands back ``arr.flat`` — an iterator that materialises
    only the positions the stride selects — for anything else. Replacing the
    branch with an unconditional ``reshape(-1)`` blew that guarantee on exactly
    the large strided arrays the budget exists for, and left the suite green,
    because every cost assertion in the suite reads ``hashed_bytes`` and the
    copy happens before a single byte is fed.
    """

    def reads_the_buffer_of(handle: Any, array: np.ndarray) -> bool:
        buffer = handle if isinstance(handle, np.ndarray) else handle.base
        return bool(np.shares_memory(buffer, array))

    contiguous = np.arange(1_000_000, dtype=np.float64)
    assert reads_the_buffer_of(flat_handle(contiguous), contiguous), "a contiguous array reshapes to a view"

    strided = np.arange(2_000_000, dtype=np.float64)[::2]
    assert not strided.flags["C_CONTIGUOUS"]
    handle = flat_handle(strided)
    assert not isinstance(handle, np.ndarray), "a non-contiguous array must not be reshaped into a copy"
    assert reads_the_buffer_of(handle, strided)


def test_survivor_a_name_that_only_exists_after_the_run_is_reported_unobservable() -> None:
    """Mutation survivor: FR-029's check on the *after* snapshot was untested.

    ``compare_namespaces`` tests ``observable`` on both mappings, and every test
    of the unobservable report used a name present in both. Dropping the check on
    the ``after`` side left the suite green — so a name a cell *creates*, whose
    value the fingerprint cannot inspect, was reported as changed and not
    reported as uncovered, which is precisely the pair FR-029 exists to keep
    together.
    """
    opaque = fingerprint(object())
    assert opaque.observable is False

    observed = compare_namespaces({}, {"handle": opaque}, cell_id="c1", source_hash="h")
    assert observed.changed_names == frozenset({"handle"})
    assert observed.unobservable_names == frozenset({"handle"}), "a name that appeared is still uncovered"

    disappeared = compare_namespaces({"handle": opaque}, {}, cell_id="c1", source_hash="h")
    assert disappeared.unobservable_names == frozenset({"handle"})


def test_survivor_a_removed_element_changes_a_sampled_container() -> None:
    """Mutation survivor, reclassified: the ``len`` feed in ``_digest_sequence`` is redundant.

    Deleting it left the suite green, and it leaves this test green too, which is
    the finding: ``_digest_sequence`` feeds each sampled *index* before its
    element, and ``_stride_indices`` always ends on ``length - 1``, so the index
    stream already carries the length and no two lengths can produce the same
    one. An equivalent mutant, not a coverage hole.

    The assertion is kept because the behaviour is worth holding regardless of
    which feed delivers it: removing an element from a position the stride does
    not sample must still move the digest, and if the index feed is ever dropped
    as "redundant with the length" this is what catches the pair being removed
    one at a time.
    """
    keep = FINGERPRINT_BUDGET.container_items
    values = [0] * (2 * keep)
    before = fingerprint(values)
    del values[keep + 5]
    assert fingerprint(values) != before


def test_survivor_a_dict_key_is_part_of_its_value() -> None:
    """Mutation survivor: nothing checked that ``_digest_mapping`` digests its keys.

    ``{'a': 1}`` and ``{'b': 1}`` are different values, and renaming a key in
    place is a mutation a cell performs. Dropping the key from the digest left the
    suite green.
    """
    assert fingerprint({"a": 1}) != fingerprint({"b": 1})

    mapping = {"a": 1, "b": 2}
    before = fingerprint(mapping)
    mapping["renamed"] = mapping.pop("a")
    assert fingerprint(mapping) != before


def test_survivor_a_cycle_is_recorded_rather_than_hitting_the_depth_ceiling() -> None:
    """Mutation survivor: cycle detection can be deleted and every cycle test still passes.

    ``test_a_self_referential_value_terminates`` asserts termination, and the
    depth ceiling terminates a cycle on its own, so deleting ``_enter``'s
    membership check left the suite green. The difference is visible in the
    counters: with the check the cycle is closed after a handful of nodes and
    nothing is truncated; without it the walk descends to the depth ceiling and
    reports the value as truncated, which is a different — and false — statement
    about how much of the value was inspected.
    """
    cyclic: list[object] = [1]
    cyclic.append(cyclic)
    ctx = fingerprint_context(cyclic)
    assert ctx.truncated is False, "a cycle is a closed loop, not content the budget ran out on"
    assert ctx.nodes <= 8, f"the walk visited {ctx.nodes} nodes for a two-element cycle"
    assert fingerprint(cyclic).observable is True


def test_survivor_a_categorical_is_read_through_its_codes_and_categories() -> None:
    """Mutation survivor: routing a categorical through ``to_numpy`` left the suite green.

    ``to_numpy`` on a categorical yields the category *values*, so two
    categoricals that differ only in their category set — which is what
    ``add_categories`` and ``reorder_categories`` change — come out identical.
    Both are real mutations of the object, and both are invisible unless the
    codes and the categories are digested as the storage they are.
    """
    series = pd.Series(pd.Categorical(["a", "b", "a"], categories=["a", "b"]))
    before = fingerprint(series)

    widened = pd.Series(pd.Categorical(["a", "b", "a"], categories=["a", "b", "c"]))
    assert list(widened) == list(series)
    assert fingerprint(widened) != before

    reordered = pd.Series(pd.Categorical(["a", "b", "a"], categories=["b", "a"]))
    assert list(reordered) == list(series)
    assert fingerprint(reordered) != before


# ---------------------------------------------------------------------------
# SC-007 and SC-010 — the measured bounds
# ---------------------------------------------------------------------------


def generated_notebook(count: int) -> list[tuple[str, str]]:
    """A notebook of *count* cells, each assigning and reading a few names."""
    cells = [("c0", "import pandas as pd\nbase = pd.read_csv('f')\nscale = 1.0\n")]
    for index in range(1, count):
        previous = index - 1
        cells.append(
            (
                f"c{index}",
                f"frame_{index} = transform(frame_{previous} if {previous} else base, scale)\n"
                f"total_{index} = frame_{index}.sum()\n"
                f"label_{index} = f'step {index}'\n",
            )
        )
    return cells


def test_sc010_a_five_hundred_cell_notebook_is_analysed_and_built_under_the_bound() -> None:
    """SC-010: five hundred cells, analysed and built in under five hundred milliseconds.

    The ceiling is SC-010's own number and it covers both halves, which is what
    the criterion says: "**analysing** a generated notebook of five hundred
    cells … **builds the graph** in under five hundred milliseconds". Nothing
    here is invented.

    Both halves matter because they are not the same size. The analysis is ~57 ms
    and the build ~9 ms, so a bound on the build alone — which is what both timed
    tests used to assert — governs a sixth of the work with fifty times the
    headroom it needs, and the ADR-054 spec 2 audit found this test guarding the
    other five sixths with a **2000 ms** ceiling that appears in no spec at all.

    The measurement is the fastest of ``TIMING_RUNS`` passes after a warm-up, for
    the reason ``test_fingerprint.best_of`` sets out: the minimum is what the
    machine can do, which is the claim a wall-clock bound makes, while a single
    sample on a runner shared with other suites measures their load as much as
    this code's cost. **Measured minimum: 67 ms — analyse 57, build 9 — against
    500 ms, which is 7.5x**, and 6.2x under bursty co-tenant load, where the worst
    single sample was 87 ms and the worst best-of-five 81 ms. That is the margin
    the next reader has before this number starts to mean something; it is the
    tightest wall-clock assertion on the analysis side of this delivery, and a
    change that takes it past ~200 ms should be read as a regression long before
    it fails. The split is reported on failure so the reader knows which half
    moved.
    """
    cells = generated_notebook(500)

    def one_pass() -> tuple[float, float]:
        started = time.perf_counter()
        facts = analyse_cells(cells)
        analysed = time.perf_counter()
        graph = build_graph(facts)
        finished = time.perf_counter()
        assert len(graph.cells) == 500
        return (analysed - started) * 1000, (finished - analysed) * 1000

    one_pass()  # warm-up, unmeasured
    runs = [one_pass() for _ in range(TIMING_RUNS)]
    total_ms = min(analyse + build for analyse, build in runs)
    analyse_ms = min(analyse for analyse, _ in runs)
    build_ms = min(build for _, build in runs)

    assert total_ms < 500.0, (
        f"best of {TIMING_RUNS}: analyse {analyse_ms:.1f} ms + build {build_ms:.1f} ms "
        f"= {total_ms:.1f} ms, bound 500 ms"
    )


def test_fr018_the_cost_grows_linearly_with_the_number_of_cells() -> None:
    """FR-018: linear in cells and names, asserted by doubling rather than by a constant.

    A wall-clock ceiling passes on a fast runner however the algorithm scales.
    This builds the graph at two sizes and requires the larger to cost less than
    a quadratic would: four times the cells must not cost sixteen times the time.
    The slack is generous because the measurement is a shared CI runner, and the
    point is to catch an accidental quadratic, not to bill for milliseconds.
    """

    def build_ms(count: int) -> float:
        facts = analyse_cells(generated_notebook(count))
        started = time.perf_counter()
        build_graph(facts)
        return (time.perf_counter() - started) * 1000

    small = max(build_ms(250), 0.5)
    large = build_ms(1000)
    assert large < small * 16, f"250 cells: {small:.1f} ms, 1000 cells: {large:.1f} ms"


def test_sc007_fingerprinting_a_whole_namespace_stays_inside_the_declared_bound() -> None:
    """SC-007: every name in the largest fixture's namespace, against ``max_seconds``.

    The namespace here is what a working session holds: a large frame, a large
    array, containers, scalars, and a handful of values the fingerprint cannot
    inspect at all.

    The bound is one ``max_seconds`` — 250 ms — for the *whole* namespace, not
    ``max_seconds`` per name. ``max_seconds`` is the ceiling for a single call, so
    ``max_seconds x len(namespace)`` is what the budget formally permits, but at
    nine names that is 2 250 ms against a measured 6 ms and the ADR-054 spec 2
    audit was right to call the result unfalsifiable: 476x headroom is a
    statement, not a measurement. The claim actually worth holding is stronger and
    is what the design rests on — nine ordinary session values together cost less
    than the budget allows for *one* of them.

    **Measured: 6.1 ms against 250 ms — 41x.** That is deliberately comfortable
    and stays a single sample: nothing here is close enough to the bound for
    scheduler noise to reach it, so it does not need the ``best_of`` treatment
    that ``dict_1m`` (5.4x) and the SC-010 test above (7.5x) do. The ``per name``
    bound is asserted alongside it so the formal criterion is still on the record.
    """
    namespace = {
        "frame": pd.DataFrame({f"c{i}": np.random.default_rng(i).random(50_000) for i in range(20)}),
        "array": np.zeros(8_000_000, dtype=np.float64),
        "series": pd.Series(np.arange(200_000)),
        "mapping": {f"k{i}": i for i in range(50_000)},
        "sequence": list(range(200_000)),
        "text": "x" * 2_000_000,
        "handle": object(),
        "module": pd,
        "scale": 1.0,
    }
    started = time.perf_counter()
    snapshot = {name: fingerprint(value) for name, value in namespace.items()}
    elapsed = time.perf_counter() - started

    formal = FINGERPRINT_BUDGET.max_seconds * len(namespace)
    assert elapsed < formal, f"{elapsed * 1000:.1f} ms for {len(namespace)} names, bound {formal * 1000:.0f} ms"
    assert elapsed < FINGERPRINT_BUDGET.max_seconds, (
        f"the whole namespace took {elapsed * 1000:.1f} ms, which is more than one call is allowed "
        f"({FINGERPRINT_BUDGET.max_seconds * 1000:.0f} ms)"
    )
    assert compare_namespaces(snapshot, snapshot, cell_id="c1", source_hash="h").changed_names == frozenset()
