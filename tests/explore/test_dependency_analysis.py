"""Unit coverage for the ADR-054 notebook dependency analysis (spec 2, T-001 to T-006).

The coverage is organised by rule rather than by function, because the static
estimate is a *list of forms* and a form with no test is one that silently stops
matching when the ``ast`` or ``symtable`` shape changes across Python versions.
SC-001 makes that explicit: every assignment form named in FR-005 has a test
that fails if the form stops being recognised, and
:func:`test_every_fr_005_form_has_its_own_test` checks that the list of forms and
the list of tests have not drifted apart.

Where a test asserts a rule the spec states, its docstring names the requirement.
Where a test pins a behaviour the spec leaves to the implementation, the
docstring says which way it was resolved and why.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence

import pytest

from scistudio import explore as explore_package
from scistudio.explore import dependency_analysis
from scistudio.explore.dependency_analysis import (
    ANALYSIS_VERSION,
    BUILTIN_NAMES,
    CELL_RECORD_KEY,
    AnalysisFlag,
    BlockCall,
    CellFacts,
    DependencyGraph,
    EdgeOrigin,
    OutputDeclaration,
    VersionNode,
    analyse_cell,
    analyse_cells,
    build_graph,
    decode_cell_record,
    encode_cell_record,
    encode_notebook_record,
    notebook_record_version,
    observation_flags,
    source_hash,
)
from scistudio.explore.fingerprint import ObservedChange
from scistudio.stability import get_stability

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def facts_for(source: str, cell_id: str = "c") -> CellFacts:
    """Analyse one cell of *source*."""
    return analyse_cell(cell_id, source)


def assigned(source: str) -> frozenset[str]:
    """The static estimate of what a one-cell notebook of *source* changes."""
    return facts_for(source).assigned


def read(source: str) -> frozenset[str]:
    """The names a one-cell notebook of *source* reads at module scope."""
    return facts_for(source).read


def graph_of(*cells: tuple[str, str], **kwargs: object) -> DependencyGraph:
    """Analyse ``(cell_id, source)`` pairs and build the graph over them."""
    return build_graph(analyse_cells(cells), **kwargs)  # type: ignore[arg-type]


def edge_tuples(graph: DependencyGraph) -> set[tuple[str, str, str]]:
    """``(reader, definer, name)`` for every edge, for order-free comparison."""
    return {(edge.reader, edge.definer, edge.name) for edge in graph.edges}


def unresolved_tuples(graph: DependencyGraph) -> set[tuple[str, str]]:
    return {(read.cell_id, read.name) for read in graph.unresolved_reads}


# ---------------------------------------------------------------------------
# FR-005 — the assignment forms, one test each (SC-001)
# ---------------------------------------------------------------------------


def test_assigned_plain_assignment() -> None:
    """FR-005: a plain assignment target."""
    assert "df" in assigned("df = load()")


def test_assigned_tuple_target() -> None:
    """FR-005: a tuple target binds every name in it.

    The spec's edge case: ``a, b = f()`` changes both, and each is a separate
    version node for the same cell.
    """
    result = assigned("a, b = f()")
    assert {"a", "b"} <= result


def test_assigned_nested_tuple_target() -> None:
    """FR-005: nesting inside a tuple target does not hide a binding."""
    assert {"a", "b", "c"} <= assigned("a, (b, c) = f()")


def test_assigned_star_target() -> None:
    """FR-005: a starred target binds the starred name as well as the rest."""
    result = assigned("head, *tail = f()")
    assert {"head", "tail"} <= result


def test_assigned_annotated_assignment() -> None:
    """FR-005: an annotated assignment binds its target."""
    assert "count" in assigned("count: int = 0")


def test_assigned_bare_annotation() -> None:
    """FR-005: a bare annotation is counted as a binding.

    ``x: int`` binds nothing at runtime — it only records the annotation — so
    this names an assignment execution would not perform. FR-002 permits exactly
    that and forbids the reverse, so the extra name is kept rather than special
    cased.
    """
    assert "x" in assigned("x: int")


def test_assigned_walrus_target() -> None:
    """FR-005: a walrus target at module scope."""
    assert "value" in assigned("if (value := compute()):\n    pass")


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("list", "vals = [y := i for i in range(3)]"),
        ("set", "vals = {y := i for i in range(3)}"),
        ("dict", "vals = {i: (y := i) for i in range(3)}"),
        ("nested", "vals = [[y := j for j in range(2)] for i in range(2)]"),
        ("generator", "vals = list(y := i for i in range(3))"),
    ],
)
def test_assigned_walrus_target_inside_a_comprehension(label: str, source: str) -> None:
    """FR-005: PEP 572 gives a comprehension's ``:=`` to the scope around it.

    The statement-level form above is the one the FR-005 ratchet used to stand
    on, and it hid this: PEP 709 inlines list, set, and dict comprehensions from
    CPython 3.12, and for an inlined one :mod:`symtable` reports the walrus target
    at module scope as neither assigned nor local nor referenced. ``y`` was
    therefore recorded nowhere, while ``exec`` binds it — the missing assignment
    FR-002 forbids. A generator expression is still a real child scope and always
    worked, which is included here as the control that made the asymmetry
    visible.

    The consequences are asserted in
    ``test_a_comprehension_walrus_definer_reaches_the_cell_that_reads_it``; this
    row is the isolated fact, one per comprehension kind, so a repair aimed at
    only one of them cannot pass.
    """
    namespace: dict[str, object] = {}
    # The interpreter is the oracle here: what it binds is what FR-002 says must not be omitted.
    exec(source, namespace)
    bound = {name for name in namespace if not name.startswith("__")}
    assert bound == {"vals", "y"}, f"{label}: the fixture must bind y at module scope"
    assert bound <= assigned(source), f"{label}: FR-002 forbids omitting an assignment the code shows"


def test_a_walrus_bound_only_inside_a_nested_scope_is_not_the_cell_s_binding() -> None:
    """FR-005: the exclusion still holds for ``:=``, which is what bounds the repair.

    A walrus inside a ``def`` or a ``lambda`` binds in that scope, not at module
    scope, so collecting every ``:=`` in the tree would over-report exactly where
    FR-005's nested-scope exclusion says not to. The collector stops at both.
    """
    in_function = assigned("def f():\n    return [w := i for i in range(2)]\n")
    assert "f" in in_function
    assert "w" not in in_function

    in_lambda = assigned("f = lambda: [w := i for i in range(2)]")
    assert "f" in in_lambda
    assert "w" not in in_lambda


def test_a_comprehension_walrus_definer_reaches_the_cell_that_reads_it() -> None:
    """FR-002, FR-015, FR-020, FR-021: what the missing binding cost downstream.

    Every consequence of the omission in one place, because each is a different
    promise: the reader was never marked stale (§6.1, the defect ADR-054 exists
    to remove), the name was reported unresolved so packaging would refuse a
    notebook that runs, and the slice dropped the definer so it would have raised
    ``NameError``.
    """
    graph = graph_of(("c1", "vals = [y := i for i in range(3)]"), ("c2", "out = y + 1"))

    assert graph.downstream("c1") == ("c2",)
    assert graph.definer_for("c2", "y") == "c1"
    assert [(read.cell_id, read.name) for read in graph.unresolved_reads] == []
    assert graph.backward_slice(["c2"]).cells == ("c1", "c2")


def test_assigned_augmented_assignment() -> None:
    """FR-005: an augmented assignment target."""
    assert "total" in assigned("total += 1")


def test_assigned_for_target() -> None:
    """FR-005: a ``for`` target."""
    assert "row" in assigned("for row in rows:\n    pass")


def test_assigned_with_as_target() -> None:
    """FR-005: a ``with ... as`` target."""
    assert "handle" in assigned("with opener() as handle:\n    pass")


def test_assigned_except_as_target() -> None:
    """FR-005: an ``except ... as`` target."""
    source = "try:\n    risky()\nexcept ValueError as err:\n    pass\n"
    assert "err" in assigned(source)


def test_assigned_import() -> None:
    """FR-005: ``import numpy`` binds ``numpy``.

    ``symtable`` reports an import as *imported* and not as *assigned*, so the
    analysis unions the two. This test is the one that fails if that union is
    ever dropped.
    """
    assert "numpy" in assigned("import numpy")


def test_assigned_dotted_import_binds_the_root_package() -> None:
    """FR-005: ``import os.path`` binds ``os``, not ``os.path``."""
    result = assigned("import os.path")
    assert "os" in result
    assert "os.path" not in result


def test_assigned_import_as() -> None:
    """FR-005: ``import numpy as np`` binds ``np`` and not ``numpy``."""
    result = assigned("import numpy as np")
    assert "np" in result
    assert "numpy" not in result


def test_assigned_from_import() -> None:
    """FR-005: ``from ... import`` binds the imported name."""
    assert "find_peaks" in assigned("from scipy.signal import find_peaks")


def test_assigned_from_import_as() -> None:
    """FR-005: ``from ... import ... as`` binds the alias."""
    result = assigned("from scipy.signal import find_peaks as fp")
    assert "fp" in result
    assert "find_peaks" not in result


def test_assigned_function_definition() -> None:
    """FR-005: a ``def`` binds its name."""
    assert "clean" in assigned("def clean(frame):\n    return frame\n")


def test_assigned_async_function_definition() -> None:
    """FR-005: an ``async def`` binds its name the same way."""
    assert "fetch" in assigned("async def fetch(url):\n    return url\n")


def test_assigned_class_definition() -> None:
    """FR-005: a ``class`` binds its name."""
    assert "Model" in assigned("class Model:\n    pass\n")


def test_assigned_del_target() -> None:
    """FR-005: a ``del`` target.

    The spec's edge case: ``del df`` removes the name from the namespace, so
    readers below depend on the deleting cell and running them fails loudly.
    """
    assert "df" in assigned("del df")


def test_assigned_match_capture() -> None:
    """FR-005: a ``match`` capture pattern binds its name."""
    source = "match command:\n    case [action, target]:\n        pass\n"
    assert {"action", "target"} <= assigned(source)


def test_name_bound_only_inside_a_nested_scope_is_not_assigned() -> None:
    """FR-005: a name bound only inside a nested scope is not the cell's binding."""
    source = "def clean(frame):\n    scratch = frame.copy()\n    return scratch\n"
    result = assigned(source)
    assert "clean" in result
    assert "scratch" not in result


def test_comprehension_target_is_not_assigned() -> None:
    """FR-005: a comprehension target binds a scope of its own, not the module.

    PEP 709 inlines list, set, and dict comprehensions from CPython 3.12, which
    makes ``symtable`` report their targets at module scope on 3.12+ and not on
    3.11. The analysis removes them so the facts are a function of the source
    rather than of the interpreter (FR-017).
    """
    result = assigned("squares = [item * 2 for item in values]")
    assert "squares" in result
    assert "item" not in result


def test_comprehension_target_that_is_also_bound_outside_stays_assigned() -> None:
    """A name that is both a comprehension target and a real binding is kept.

    Dropping it would remove a definer, which is the one direction FR-002
    forbids.
    """
    source = "item = seed\nsquares = [item * 2 for item in values]\n"
    assert "item" in assigned(source)


def test_generator_expression_target_is_not_assigned() -> None:
    """A generator expression's target is scope-local on every supported version."""
    result = assigned("stream = (item for item in values)")
    assert "stream" in result
    assert "item" not in result


def test_global_declaration_in_a_nested_scope_is_assigned() -> None:
    """A ``global`` declaration binds module scope, so the code shows the assignment.

    FR-005 excludes a name bound *only* inside a nested scope; ``global`` takes
    the binding out of that scope by declaration, and FR-002 resolves the
    remaining uncertainty (the function may never be called) toward the edge.
    """
    source = "def install():\n    global registry\n    registry = {}\n"
    assert "registry" in assigned(source)


#: FR-005 names these forms. Each maps to the test that fails if the form stops
#: being recognised — the machine-checked half of SC-001.
FR_005_FORMS: dict[str, str] = {
    "assignment target": "test_assigned_plain_assignment",
    "tuple target": "test_assigned_tuple_target",
    "star target": "test_assigned_star_target",
    "annotated target": "test_assigned_annotated_assignment",
    "walrus target at module scope": "test_assigned_walrus_target",
    "walrus target inside a comprehension": "test_assigned_walrus_target_inside_a_comprehension",
    "augmented assignment": "test_assigned_augmented_assignment",
    "for target": "test_assigned_for_target",
    "with ... as target": "test_assigned_with_as_target",
    "except ... as target": "test_assigned_except_as_target",
    "import": "test_assigned_import",
    "from ... import": "test_assigned_from_import",
    "function definition": "test_assigned_function_definition",
    "class definition": "test_assigned_class_definition",
    "del target": "test_assigned_del_target",
    "nested scope exclusion": "test_name_bound_only_inside_a_nested_scope_is_not_assigned",
}


def test_every_fr_005_form_has_its_own_test() -> None:
    """SC-001, measured by the presence of the test per form.

    The ratchet checks that each *form* has a test, not that the test covers the
    form's variants, and the ADR-054 spec 2 audits showed what that costs: a
    walrus inside a comprehension was recorded nowhere while
    ``test_assigned_walrus_target`` — the statement-level form — stayed green, so
    this meta-test stayed green with it. A variant whose binding rule differs is
    a row of its own here, which is why the two walrus forms are listed
    separately.
    """
    missing = [name for name, test in FR_005_FORMS.items() if test not in globals()]
    assert not missing, f"FR-005 forms with no test: {missing}"


# ---------------------------------------------------------------------------
# FR-006 — the read set
# ---------------------------------------------------------------------------


def test_read_at_module_scope() -> None:
    """FR-006: a name referenced at module scope is a read."""
    assert "df" in read("peaks = find(df)")


def test_a_name_the_cell_also_assigns_is_still_read() -> None:
    """FR-006: the analysis does not model whether the read precedes the assignment."""
    facts = facts_for("df = df.dropna()")
    assert "df" in facts.assigned
    assert "df" in facts.read


def test_read_written_after_the_binding_is_still_recorded() -> None:
    """The spec's edge case: ``df = load(); df.head()`` is recorded as reading ``df``.

    Dropping the read would be correct here and wrong for ``if flag: df = load()``
    followed by ``df.head()``, and the analysis cannot tell the two apart without
    modelling control flow.
    """
    assert "df" in read("df = load()\ndf.head()\n")


def test_read_inside_a_nested_scope_resolving_to_module_scope() -> None:
    """FR-006: a nested scope's read of a module-scope name is the cell's read."""
    source = "def report():\n    return summary_frame\n"
    assert "summary_frame" in read(source)


def test_read_inside_a_class_body_resolving_to_module_scope() -> None:
    """FR-006: a class body is a nested scope whose global reads are the cell's."""
    source = "class Model:\n    default = base_config\n"
    assert "base_config" in read(source)


def test_free_variable_of_an_inner_function_is_not_a_module_read() -> None:
    """A free variable resolves to the enclosing function, not to the module."""
    source = "def outer():\n    local_value = 1\n    def inner():\n        return local_value\n    return inner\n"
    assert "local_value" not in read(source)


def test_comprehension_iterable_is_read() -> None:
    """The iterable of a comprehension is evaluated at module scope."""
    assert "values" in read("squares = [item * 2 for item in values]")


def test_comprehension_target_is_not_read() -> None:
    """A comprehension target is removed from the read set as well as the assigned set.

    CPython 3.12+ reports an inlined comprehension's target as referenced at
    module scope and 3.11 does not. Leaving it in would make the unresolved-read
    list — and so what packaging refuses — depend on the interpreter the analysis
    happens to run under (FR-017).
    """
    assert "item" not in read("squares = [item * 2 for item in values]")


def test_a_comprehension_target_bound_outside_stays_read() -> None:
    """The removal never reaches a name the cell binds for real."""
    assert "item" in read("item = seed\nsquares = [item * 2 for item in values]\nuse(item)\n")


def test_augmented_assignment_target_is_read() -> None:
    """``x += 1`` needs ``x`` to exist, so it is a read as well as a binding.

    ``symtable`` reports the target as a binding only. Without the read, a
    backward slice containing this cell would omit the cell that defines the name
    and fail with a ``NameError`` when the slice runs (FR-006, FR-021).
    """
    assert "total" in read("total += 1")


def test_del_target_is_read() -> None:
    """``del x`` needs ``x`` to exist, so it is a read as well as a binding."""
    assert "df" in read("del df")


def test_augmented_assignment_on_a_nested_scope_local_is_not_a_module_read() -> None:
    """A function's own local is its own, however it is written.

    ``running`` is bound and then augmented inside ``tally``; nothing resolves it
    to the module scope, so FR-006 does not reach it. This is the boundary of the
    rule the test below states, and the two belong together: the extra read
    follows the *scope a name resolves to*, not the depth the statement sits at.
    """
    source = "def tally():\n    running = 0\n    running += 1\n    return running\n"
    assert "running" not in read(source)


def test_augmented_assignment_on_a_global_inside_a_function_is_a_module_read() -> None:
    """FR-006: a nested-scope read that resolves to the module scope is a module read.

    ``counter += 1`` under ``global counter`` reads ``counter``. :mod:`symtable`
    reports the symbol as assigned and global but not as referenced, so without
    this the cell would be a definer of ``counter`` that reads nothing, and a
    backward slice through it would drop the cell that gave ``counter`` its
    initial value and fail with a ``NameError`` (FR-021, SC-003).
    """
    source = "def bump():\n    global counter\n\n    counter += 1\n"
    assert "counter" in read(source)
    assert "counter" in facts_for(source).assigned


def test_del_of_a_global_inside_a_function_is_a_module_read() -> None:
    """``del counter`` under ``global`` needs ``counter`` to exist, exactly as ``+=`` does."""
    assert "counter" in read("def drop():\n    global counter\n\n    del counter\n")


def test_a_global_declaration_does_not_reach_a_function_defined_inside_the_one_that_made_it() -> None:
    """The declaration governs its own scope, and the extra read follows it exactly.

    ``inner`` never declares ``counter`` global, so ``counter += 1`` there is a
    read of ``inner``'s own local — a ``NameError`` at run time and not a
    module-scope read the graph should draw an edge for.
    """
    source = "def outer():\n    global counter\n\n    def inner():\n        counter += 1\n\n    return inner\n"
    assert "counter" not in read(source)


def test_an_augmented_assignment_on_a_global_inside_a_class_body_is_a_module_read() -> None:
    """A class body is a scope too, and ``global`` means the same thing in it."""
    assert "tally" in read("class Counter:\n    global tally\n\n    tally += 1\n")


def test_augmented_assignment_inside_a_module_level_loop_is_a_read() -> None:
    """A module-level ``for`` body still executes at module scope."""
    source = "for row in rows:\n    total += row\n"
    assert "total" in read(source)


def test_attribute_and_subscript_targets_read_the_base_name() -> None:
    """``d['k'] = 1`` reads ``d``; it does not bind it (FR-007)."""
    facts = facts_for("frame['x'] = frame.a * 2")
    assert "frame" in facts.read
    assert "frame" not in facts.assigned


# ---------------------------------------------------------------------------
# FR-007 — static facts are assignments only
# ---------------------------------------------------------------------------


def test_in_place_method_call_assigns_nothing() -> None:
    """FR-007: no list of mutating methods. ``df.dropna(inplace=True)`` binds nothing.

    What the cell changes is established by the observation when it runs.
    """
    facts = facts_for("df.dropna(inplace=True)")
    assert facts.assigned == frozenset()
    assert "df" in facts.read


def test_call_that_mutates_its_argument_assigns_nothing() -> None:
    """FR-007: no analysis of a called function's body."""
    facts = facts_for("normalise(df)")
    assert facts.assigned == frozenset()
    assert {"normalise", "df"} <= facts.read


def test_alias_of_a_frame_is_not_tracked() -> None:
    """FR-007: no alias tracking. ``df2 = df`` binds ``df2`` and nothing else."""
    facts = facts_for("df2 = df\ndf2.dropna(inplace=True)\n")
    assert facts.assigned == frozenset({"df2"})


# ---------------------------------------------------------------------------
# FR-008, FR-009, FR-010 — declarations and block calls
# ---------------------------------------------------------------------------


def test_output_declaration_records_keyword_and_argument_names() -> None:
    """FR-008: the keyword names and the argument names of each ``scistudio.output`` call."""
    facts = facts_for("scistudio.output(peaks=peaks, table=df_clean)")
    assert facts.outputs == (OutputDeclaration(keywords=("peaks", "table"), arguments=("peaks", "df_clean")),)
    assert facts.is_output_cell


def test_output_declaration_records_positional_arguments() -> None:
    """FR-008: a positional argument's name is recorded ahead of the keyword values."""
    facts = facts_for("scistudio.output(peaks, table=df)")
    assert facts.outputs[0].arguments == ("peaks", "df")
    assert facts.outputs[0].keywords == ("table",)


def test_two_output_calls_are_recorded_separately() -> None:
    """FR-008: *each* such call, not the first."""
    facts = facts_for("scistudio.output(a=a)\nscistudio.output(b=b)\n")
    assert [decl.keywords for decl in facts.outputs] == [("a",), ("b",)]


def test_a_cell_without_an_output_call_is_not_an_output_cell() -> None:
    """FR-008: a cell with such a call is an output cell; this one is not."""
    facts = facts_for("peaks = find(df)")
    assert facts.outputs == ()
    assert not facts.is_output_cell


def test_a_bare_output_call_is_not_an_output_declaration() -> None:
    """The declaration is ``scistudio.output``; a local function named ``output`` is not it.

    The recognised form is the dotted path, so a notebook that happens to define
    its own ``output`` helper does not accidentally declare a block port.
    """
    facts = facts_for("output(peaks=peaks)")
    assert facts.outputs == ()


def test_input_declaration_records_the_string_literal() -> None:
    """FR-009: each string literal passed as the first argument to ``scistudio.input``."""
    facts = facts_for('df = scistudio.load(scistudio.input("data")).to_pandas()')
    assert facts.inputs == ("data",)


def test_two_input_declarations_are_recorded_in_written_order() -> None:
    """FR-009: *each* string literal."""
    facts = facts_for('a = scistudio.input("first")\nb = scistudio.input("second")\n')
    assert facts.inputs == ("first", "second")


def test_input_declaration_with_a_non_literal_argument_is_not_recorded() -> None:
    """FR-009 records string literals; a computed port name is not one."""
    facts = facts_for("a = scistudio.input(port_name)")
    assert facts.inputs == ()


def test_block_call_records_the_literal_identifier() -> None:
    """FR-010: the block identifier passed as a string literal."""
    facts = facts_for('peaks = blocks.run("imaging.find_peaks", img=img, sigma=2.0)')
    assert facts.block_calls == (BlockCall(block_id="imaging.find_peaks", lineno=1),)
    assert not facts.has_flag(AnalysisFlag.UNKNOWN_BLOCK_CALL)


def test_fully_qualified_block_call_is_recognised() -> None:
    """FR-010: the dotted path is matched by suffix, so the qualified spelling matches."""
    facts = facts_for('peaks = scistudio.blocks.run("imaging.find_peaks")')
    assert facts.block_calls == (BlockCall(block_id="imaging.find_peaks", lineno=1),)


def test_block_call_with_a_non_literal_identifier_is_flagged() -> None:
    """FR-010: a block call whose identifier is not a literal is an unknown block call."""
    facts = facts_for("peaks = blocks.run(block_id, img=img)")
    assert facts.block_calls == (BlockCall(block_id=None, lineno=1),)
    assert facts.has_flag(AnalysisFlag.UNKNOWN_BLOCK_CALL)


def test_block_call_flag_carries_its_line() -> None:
    """The diagnostic points at the call rather than at the cell."""
    facts = facts_for("x = 1\ny = 2\npeaks = blocks.run(block_id)\n")
    flag = next(entry for entry in facts.flags if entry.flag is AnalysisFlag.UNKNOWN_BLOCK_CALL)
    assert flag.lineno == 3


# ---------------------------------------------------------------------------
# FR-011, FR-012, FR-013 — magics, syntax errors, unknown bindings (SC-005)
# ---------------------------------------------------------------------------


def test_line_magic_is_stripped_and_the_assignment_below_it_survives() -> None:
    """US5 scenario 1 / FR-011: ``%pip install x`` then ``df = ...``."""
    facts = facts_for("%pip install scikit-image\ndf = load()\n")
    assert "df" in facts.assigned
    assert facts.flags == ()


def test_shell_line_is_stripped() -> None:
    """FR-011: a line whose first non-blank character is ``!`` is removed."""
    facts = facts_for("!ls -la\ndf = load()\n")
    assert "df" in facts.assigned
    assert facts.flags == ()


def test_an_indented_magic_line_is_stripped() -> None:
    """FR-011: the first token of a logical line, not the first token in column zero.

    The indent token says nothing about where the logical line begins, so a magic
    inside a block is still the first token of its own.
    """
    facts = facts_for("if True:\n    %time\n    df = load()\n")
    assert "df" in facts.assigned
    assert facts.flags == ()


def test_a_modulo_expression_is_not_a_magic_line() -> None:
    """FR-011: ``%`` after another token on the same logical line is the operator."""
    facts = facts_for("remainder = total % 3")
    assert "remainder" in facts.assigned
    assert facts.flags == ()


def test_a_wrapped_modulo_is_the_operator_and_its_right_hand_name_is_read() -> None:
    """FR-011 / FR-006: what ``black`` and ``ruff format`` emit is not a magic.

    The continuation line's first non-blank character is ``%``, and a textual
    rule removes it: the cell still parses, as ``ratio = (total)``, no flag is
    raised, and ``count`` vanishes from the read set — a silently smaller
    backward slice that raises ``NameError`` when it runs. The tokeniser puts
    that ``%`` inside an open bracket, where it is the operator.
    """
    facts = facts_for("ratio = (\n    total\n    % count\n)\n")
    assert facts.read >= {"total", "count"}
    assert facts.assigned == frozenset({"ratio"})
    assert facts.flags == ()


def test_a_wrapped_inequality_is_the_operator_and_its_right_hand_name_is_read() -> None:
    """The ``!`` half of the same shape: ``!=`` opening a continuation line."""
    facts = facts_for("ok = (\n    a\n    != b\n)\n")
    assert facts.read >= {"a", "b"}
    assert facts.flags == ()


def test_a_modulo_after_a_backslash_continuation_is_not_a_magic() -> None:
    """FR-011: a backslash joins two physical lines into one logical line."""
    facts = facts_for("ratio = total \\\n    % count\n")
    assert facts.read >= {"total", "count"}
    assert facts.flags == ()


def test_a_magic_after_a_comment_only_line_is_still_a_magic() -> None:
    """FR-011: a comment-only line does not end a logical line, and none was open.

    The tokeniser's ``NL`` after the comment is not a logical newline, so the
    rule cannot lean on it — the magic is the first token of the logical line
    because nothing has opened one yet, which is the case that distinguishes this
    from the wrapped operator above.
    """
    facts = facts_for("# set the backend\n%matplotlib inline\ndf = load()\n")
    assert "df" in facts.assigned
    assert facts.flags == ()


def test_a_magic_after_a_blank_line_is_still_a_magic() -> None:
    """The other ``NL``-emitting shape, for the same reason."""
    facts = facts_for("df = load()\n\n%matplotlib inline\npeaks = find(df)\n")
    assert facts.assigned >= {"df", "peaks"}
    assert facts.flags == ()


def test_a_magic_inside_a_string_literal_is_left_in_place() -> None:
    """FR-011: a ``%`` inside a literal is part of that token, not the start of a line."""
    facts = facts_for('notes = """\n%matplotlib"""\ndf = load()\n')
    assert facts.assigned == frozenset({"notes", "df"})
    assert facts.flags == ()


def test_a_shell_line_the_tokeniser_cannot_read_is_still_stripped() -> None:
    """FR-011's error-recovery clause: the older textual test from the stop onward.

    ``!cat it's-a-file`` stops the tokeniser on the apostrophe, which opens a
    string literal that never closes. Every physical line from there on is
    classified textually, so the shell line still goes and the cell below it
    still parses.

    The first case is not enough on its own, and the ADR-054 spec 2 audit proved
    it: ``!`` is the first token of its own logical line, so the *lexical* pass
    marks line 2 before the tokeniser ever reaches the apostrophe, and the case
    passes whether the fallback exists or not. The second case is the one that
    needs it. Two magic lines, the first of which stops the tokeniser: only the
    textual pass can reach the ``%pip`` line below the stop, and without it the
    cell does not parse and comes back with a syntax-error flag and nothing
    assigned. Delete the fallback and this test dies on that assertion.
    """
    facts = facts_for("df = load()\n!cat it's-a-file\npeaks = find(df)\n")
    assert facts.assigned >= {"df", "peaks"}
    assert facts.flags == ()

    below_the_stop = facts_for("df = 1\n!cat it's-a-file\n%pip install x\n")
    assert below_the_stop.flags == (), "the magic below the tokeniser stop is only reachable textually"
    assert below_the_stop.assigned == frozenset({"df"})


def test_a_magic_whose_logical_line_spans_two_physical_lines_is_removed_whole() -> None:
    """FR-011: *every* physical line the magic's logical line spans is removed.

    Removing only the first would leave the continuation behind as a fragment
    that does not parse, which is the syntax-error flag FR-011 forbids the strip
    to produce on its own.
    """
    facts = facts_for("%time load(\n    'a.csv'\n)\ndf = 1\n")
    assert facts.assigned == frozenset({"df"})
    assert facts.flags == ()


def test_magic_stripping_preserves_line_numbers() -> None:
    """A stripped line is replaced by a blank one so a later position is still true."""
    facts = facts_for("%pip install x\ndef broken(:\n    pass\n")
    flag = next(entry for entry in facts.flags if entry.flag is AnalysisFlag.SYNTAX_ERROR)
    assert flag.lineno == 2


def test_cell_magic_makes_the_cell_opaque() -> None:
    """US5 scenario 2 / FR-011: ``%%time`` leaves an empty estimate and one flag."""
    facts = facts_for("%%time\ndf = load()\n")
    assert facts.assigned == frozenset()
    assert facts.read == frozenset()
    assert facts.flag_kinds == {AnalysisFlag.OPAQUE_CELL_MAGIC}


def test_cell_magic_after_a_blank_line_still_makes_the_cell_opaque() -> None:
    """FR-011 keys on the first non-blank line."""
    facts = facts_for("\n\n%%bash\necho hi\n")
    assert facts.has_flag(AnalysisFlag.OPAQUE_CELL_MAGIC)


def test_opaque_cell_flag_names_the_magic() -> None:
    """The message is what the person reads, so it says which magic made the cell opaque."""
    facts = facts_for("%%capture\ndf = load()\n")
    flag = facts.flags[0]
    assert "%%capture" in flag.message


def test_syntax_error_is_flagged_with_the_parser_message_and_position() -> None:
    """US5 scenario 3 / FR-012."""
    facts = facts_for("df = [1, 2\n")
    flag = next(entry for entry in facts.flags if entry.flag is AnalysisFlag.SYNTAX_ERROR)
    assert facts.assigned == frozenset()
    assert facts.read == frozenset()
    assert flag.message.strip()
    assert flag.lineno is not None


def test_a_cell_that_does_not_parse_does_not_stop_the_others() -> None:
    """FR-012: every other cell is analysed as if the broken one were absent."""
    graph = graph_of(
        ("c1", "df = load()"),
        ("c2", "def broken(:\n    pass\n"),
        ("c3", "peaks = find(df)"),
    )
    assert ("c3", "c1", "df") in edge_tuples(graph)


def test_a_source_with_a_null_byte_is_flagged_rather_than_raised() -> None:
    """``ast.parse`` raises ``ValueError`` rather than ``SyntaxError`` for a null byte."""
    facts = facts_for("df = 1\x00\n")
    assert facts.has_flag(AnalysisFlag.SYNTAX_ERROR)


@pytest.mark.parametrize(
    "source",
    [
        "",
        "\n\n\n",
        "   ",
        "%",
        "!",
        "%%",
        "%%%",
        "df = (",
        "def f(:",
        "class C(:",
        "return 1",
        "await x",
        "yield 1",
        "x = 1\x00",
        "﻿df = 1",
        "if True:\nbad_indent = 1",
        "  leading = 1",
        "x = " + "(" * 60 + "1" + ")" * 60,
        "x = " + "[" * 200,
        "df = 'unterminated",
        "\t\tx = 1",
        "l = lambda: (yield)",
    ],
    ids=[
        "empty",
        "blank-lines",
        "spaces",
        "bare-percent",
        "bare-bang",
        "bare-double-percent",
        "triple-percent",
        "unclosed-paren",
        "broken-def",
        "broken-class",
        "return-outside-function",
        "await-outside-async",
        "yield-outside-function",
        "null-byte",
        "bom",
        "bad-indent",
        "leading-indent",
        "deep-nesting",
        "unbalanced-brackets",
        "unterminated-string",
        "tab-indent",
        "yield-in-lambda",
    ],
)
def test_no_cell_ever_raises(source: str) -> None:
    """FR-012: the analysis of a half-written cell must not make the notebook unusable."""
    facts = analyse_cell("c", source)
    assert facts.cell_id == "c"
    assert facts.source_hash == source_hash(source)


def test_star_import_binds_an_unknown_set_of_names() -> None:
    """FR-013: a star import changes an unknown set of names."""
    facts = facts_for("from numpy import *")
    assert facts.has_flag(AnalysisFlag.UNKNOWN_BINDINGS)
    assert facts.binds_unknown_names


def test_run_magic_binds_an_unknown_set_of_names() -> None:
    """FR-013: a ``%run`` line changes an unknown set of names.

    The line is stripped before parsing like every other magic, so the flag has
    to be raised while stripping or it is lost.
    """
    facts = facts_for("%run setup.py\ndf = load()\n")
    assert facts.binds_unknown_names
    assert "df" in facts.assigned


def test_an_ordinary_magic_does_not_bind_unknown_names() -> None:
    """FR-011: a stripped magic line does not by itself produce a flag."""
    assert not facts_for("%matplotlib inline\ndf = load()\n").binds_unknown_names


def test_a_run_that_is_not_the_first_token_of_a_logical_line_binds_nothing_unknown() -> None:
    """FR-011's definition of a magic line governs FR-013's ``%run`` as well.

    Inside an open bracket ``%run`` is a modulo by a name called ``run``. Reading
    it as a ``%run`` magic would mark the cell as binding an unknown set, which
    resolves every otherwise-unresolved read below it to this cell and hides the
    ones packaging exists to refuse.
    """
    facts = facts_for("total = (\n    seconds\n    %run\n)\n")
    assert not facts.binds_unknown_names
    assert facts.read >= {"seconds", "run"}


def test_a_plain_from_import_does_not_bind_unknown_names() -> None:
    """Only the star form is unknown."""
    assert not facts_for("from numpy import array").binds_unknown_names


# ---------------------------------------------------------------------------
# FR-014 to FR-019 — the graph
# ---------------------------------------------------------------------------


def test_a_read_resolves_to_the_nearest_definer_above() -> None:
    """US1 scenario 2 / FR-015: the nearer of two definers, and no other."""
    graph = graph_of(
        ("c1", "df = load()"),
        ("c2", "df = df.dropna()"),
        ("c3", "peaks = find(df)"),
    )
    assert ("c3", "c2", "df") in edge_tuples(graph)
    assert ("c3", "c1", "df") not in edge_tuples(graph)


def test_a_cell_never_depends_on_itself() -> None:
    """US1 scenario 3 / FR-015: ``df = df.dropna()`` resolves to the cell above."""
    graph = graph_of(("c1", "df = load()"), ("c2", "df = df.dropna()"))
    assert ("c2", "c1", "df") in edge_tuples(graph)
    assert not [edge for edge in graph.edges if edge.reader == edge.definer]


def test_a_read_with_no_definer_above_is_unresolved() -> None:
    """FR-015: the unresolved list is what packaging refuses a notebook on."""
    graph = graph_of(("c1", "peaks = find_peaks(df)"))
    assert ("c1", "df") in unresolved_tuples(graph)
    assert ("c1", "find_peaks") in unresolved_tuples(graph)


def test_a_builtin_read_draws_no_edge_and_is_not_unresolved() -> None:
    """FR-015: the list stays about names a run would fail on."""
    graph = graph_of(("c1", "count = len(rows)\nprint(count)\n"))
    assert "len" in BUILTIN_NAMES
    assert ("c1", "len") not in unresolved_tuples(graph)
    assert ("c1", "print") not in unresolved_tuples(graph)
    assert not [edge for edge in graph.edges if edge.name in {"len", "print"}]


def test_a_name_the_reading_cell_binds_itself_is_not_unresolved() -> None:
    """A read the cell's own binding satisfies is not a name error.

    FR-015 draws no edge here because a cell must not depend on itself, and US2
    scenario 5 scopes the unresolved list to "a name that no enabled cell
    changes" — which this is not. Without the exception every
    ``import pandas as pd`` cell would report ``pd`` unresolved and packaging
    would refuse every notebook.
    """
    graph = graph_of(("c1", "import pandas as pd\ndf = pd.read_csv('f')\n"))
    assert ("c1", "pd") not in unresolved_tuples(graph)
    assert graph.unresolved_reads == ()


def test_a_star_import_resolves_an_otherwise_unresolved_read() -> None:
    """US5 scenario 4 / FR-013."""
    graph = graph_of(("c1", "from numpy import *"), ("c2", "values = array([1, 2])"))
    edge = next(edge for edge in graph.edges if edge.name == "array")
    assert edge.definer == "c1"
    assert edge.origin is EdgeOrigin.UNKNOWN_BINDING
    assert ("c2", "array") not in unresolved_tuples(graph)


def test_a_real_definer_beats_a_star_import_cell() -> None:
    """FR-013: the unknown-binding fallback applies only when no definer resolves the read."""
    graph = graph_of(
        ("c1", "df = load()"),
        ("c2", "from numpy import *"),
        ("c3", "peaks = find(df)"),
    )
    edge = next(edge for edge in graph.edges if edge.name == "df")
    assert edge.definer == "c1"
    assert edge.origin is EdgeOrigin.STATIC_ASSIGNMENT


def test_a_star_import_below_the_reader_does_not_resolve_it() -> None:
    """Written order is the authority: only a cell *above* can resolve a read."""
    graph = graph_of(("c1", "values = array([1])"), ("c2", "from numpy import *"))
    assert ("c1", "array") in unresolved_tuples(graph)


def test_edge_origin_is_recorded_for_a_static_assignment() -> None:
    """FR-019: the origin is what lets the view say why an edge exists."""
    graph = graph_of(("c1", "df = load()"), ("c2", "peaks = find(df)"))
    assert graph.edges[0].origin is EdgeOrigin.STATIC_ASSIGNMENT


def test_edge_origin_is_recorded_for_an_observed_change() -> None:
    """FR-019: an edge that exists only because of an observation says so."""
    graph = build_graph(
        analyse_cells([("c1", "df.dropna(inplace=True)"), ("c2", "peaks = find(df)")]),
        observations={"c1": {"df"}},
    )
    edge = next(edge for edge in graph.edges if edge.reader == "c2")
    assert edge.definer == "c1"
    assert edge.origin is EdgeOrigin.OBSERVED_CHANGE


def test_version_nodes_are_one_per_changed_name_per_cell() -> None:
    """US1 scenario 5 / FR-016."""
    graph = graph_of(("c1", "a, b = f()"), ("c2", "c = a + b"))
    assert set(graph.version_nodes) == {
        VersionNode("c1", "a"),
        VersionNode("c1", "b"),
        VersionNode("c2", "c"),
    }


def test_version_nodes_exclude_a_disabled_cell() -> None:
    """FR-016 is over the *enabled* cells' changed sets."""
    graph = graph_of(("c1", "a = 1"), ("c2", "b = 2"), enabled={"c2": False})
    assert set(graph.version_nodes) == {VersionNode("c1", "a")}


def test_version_edges_agree_with_the_cell_edges() -> None:
    """US1 scenario 5 / FR-016: the version graph is derived from the same facts."""
    graph = graph_of(
        ("c1", "df = load()"),
        ("c2", "a, b = split(df)"),
        ("c3", "df.head()"),
    )
    projected = {(edge.target_cell, edge.source.cell_id, edge.source.name, edge.origin) for edge in graph.version_edges}
    assert projected == {(edge.reader, edge.definer, edge.name, edge.origin) for edge in graph.edges}


def test_a_version_edge_into_a_sink_cell_has_no_target_version() -> None:
    """A display cell changes nothing, so it has no version node — but must still appear."""
    graph = graph_of(("c1", "df = load()"), ("c2", "df.head()"))
    edge = next(edge for edge in graph.version_edges if edge.target_cell == "c2")
    assert edge.source == VersionNode("c1", "df")
    assert edge.target is None


def test_a_version_edge_into_a_producing_cell_names_each_version_it_produces() -> None:
    """A cell that changes two names carries the read into both versions."""
    graph = graph_of(("c1", "df = load()"), ("c2", "a, b = split(df)"))
    targets = {edge.target for edge in graph.version_edges if edge.target_cell == "c2"}
    assert targets == {VersionNode("c2", "a"), VersionNode("c2", "b")}


def test_the_graph_is_a_deterministic_function_of_its_inputs() -> None:
    """FR-017."""
    cells = [
        ("c1", "import pandas as pd\ndf = pd.read_csv('f')"),
        ("c2", "df = df[df.x > 1]"),
        ("c3", "peaks, meta = find(df)"),
        ("c4", "scistudio.output(peaks=peaks)"),
    ]
    first = build_graph(analyse_cells(cells), observations={"c2": ["df", "extra"]})
    second = build_graph(analyse_cells(cells), observations={"c2": ["extra", "df"]})
    assert first == second


def test_duplicate_cell_ids_are_rejected() -> None:
    """Two cells with one id would make every query ambiguous."""
    facts = analyse_cells([("c1", "a = 1"), ("c1", "b = 2")])
    with pytest.raises(ValueError, match="duplicate cell id"):
        build_graph(facts)


def test_build_graph_does_not_write_the_enabled_flag() -> None:
    """FR-014: the enabled flag is the notebook's; the analysis only reads it."""
    enabled = {"c1": True, "c2": False}
    graph_of(("c1", "a = 1"), ("c2", "b = a"), enabled=enabled)
    assert enabled == {"c1": True, "c2": False}


def test_a_cell_missing_from_the_enabled_map_defaults_to_enabled() -> None:
    """A notebook that has never toggled a cell has no flag to read."""
    graph = graph_of(("c1", "a = 1"), ("c2", "b = a"), enabled={})
    assert graph.cells == ("c1", "c2")


# ---------------------------------------------------------------------------
# FR-014 / US4 — enabling and disabling (SC-004)
# ---------------------------------------------------------------------------


ALTERNATIVES = (
    ("c1", "raw = load()"),
    ("c2", "df = raw[raw.a > 1]"),
    ("c3", "df = raw[raw.b > 2]"),
    ("c4", "peaks = find(df)"),
)


def test_disabling_the_later_definer_moves_the_edge_to_the_earlier_one() -> None:
    """US4 scenario 1 / SC-004."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c3": False})
    edge = next(edge for edge in graph.edges if edge.reader == "c4" and edge.name == "df")
    assert edge.definer == "c2"


def test_disabling_the_earlier_definer_moves_the_edge_to_the_later_one() -> None:
    """US4 scenario 2 / SC-004."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c2": False})
    edge = next(edge for edge in graph.edges if edge.reader == "c4" and edge.name == "df")
    assert edge.definer == "c3"


def test_a_disabled_cell_is_absent_from_the_graph_and_nothing_depends_on_it() -> None:
    """US4 scenario 3 / FR-014: a disabled cell neither defines nor reads."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c3": False})
    assert "c3" not in graph.cells
    assert not [edge for edge in graph.edges if "c3" in (edge.reader, edge.definer)]
    assert "c3" not in graph.downstream("c1")


def test_disabling_the_only_definer_leaves_the_read_unresolved() -> None:
    """US4 scenario 4 / SC-004."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c2": False, "c3": False})
    assert ("c4", "df") in unresolved_tuples(graph)


def test_downstream_excludes_a_disabled_reader() -> None:
    """US4 scenario 3: nothing depends on a disabled cell, and it depends on nothing."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c4": False})
    assert "c4" not in graph.downstream("c1")


def test_a_read_routes_past_a_disabled_definer_to_the_one_above_it() -> None:
    """FR-014 with three definers: disabling the nearest exposes the next one up."""
    cells = [("c1", "df = load()"), ("c2", "df = df.dropna()"), ("c3", "df = df.head()"), ("c4", "use(df)")]
    graph = build_graph(analyse_cells(cells), enabled={"c3": False, "c2": False})
    assert next(edge for edge in graph.edges if edge.reader == "c4").definer == "c1"


def test_a_disabled_star_import_does_not_resolve_a_read() -> None:
    """FR-014 applies to the unknown-binding fallback as much as to a definer."""
    graph = graph_of(
        ("c1", "from numpy import *"),
        ("c2", "values = array([1])"),
        enabled={"c1": False},
    )
    assert ("c2", "array") in unresolved_tuples(graph)


# ---------------------------------------------------------------------------
# FR-020 to FR-023 — the four queries
# ---------------------------------------------------------------------------


STALE_NOTEBOOK = (
    ("c1", "raw = load()"),
    ("c2", "df = raw[raw.intensity > 100]"),
    ("c3", "peaks = find(df)"),
    ("c4", "report = summarise(peaks)"),
    ("c5", "lookup = load_lookup()"),
    ("c6", "table = df.describe()"),
)


def test_downstream_contains_every_transitive_reader_in_written_order() -> None:
    """US1 scenario 1 / FR-020: cells 3, 4, and 6 are stale; cell 5 is untouched."""
    graph = graph_of(*STALE_NOTEBOOK)
    assert graph.downstream("c2") == ("c3", "c4", "c6")


def test_downstream_does_not_contain_the_cell_itself() -> None:
    """FR-020: the re-run cell is not downstream of itself."""
    graph = graph_of(*STALE_NOTEBOOK)
    assert "c2" not in graph.downstream("c2")


def test_downstream_of_a_leaf_is_empty() -> None:
    """Nothing reads the last cell's bindings."""
    graph = graph_of(*STALE_NOTEBOOK)
    assert graph.downstream("c6") == ()


def test_downstream_rejects_a_cell_that_is_not_in_the_graph() -> None:
    """A disabled cell has no downstream set; asking is a caller error, not an empty answer."""
    graph = graph_of(*STALE_NOTEBOOK, enabled={"c5": False})
    with pytest.raises(KeyError):
        graph.downstream("c5")
    with pytest.raises(KeyError):
        graph.downstream("nope")


#: The six-cell notebook of User Story 2: a load, a filter, an in-place drop, a
#: peak finder, a ``head()`` the person left in, and an output declaration.
STORY_TWO = (
    ("c1", "import pandas as pd\nfrom scipy.signal import find_peaks\ndf = pd.read_csv('f')\n"),
    ("c2", "df = df[df.intensity > 100]"),
    ("c3", "df.dropna(inplace=True)"),
    ("c4", "peaks = find_peaks(df)"),
    ("c5", "df.head()"),
    ("c6", "scistudio.output(peaks=peaks, table=df)"),
)

#: Cell 3 mutates in place, so its static estimate is empty and only the
#: observation makes it a definer of ``df``. The three variants of SC-002
#: replace the in-place call with a subscript assignment, a mutating library
#: function, and a helper that mutates its parameter; all four are invisible to
#: the static estimate and all four are seen the same way once observed.
STORY_TWO_VARIANTS = {
    "in-place-method": "df.dropna(inplace=True)",
    "subscript-assignment": "df['x'] = df.a * 2",
    "library-function": "numpy.nan_to_num(df, copy=False)",
    "helper-mutating-its-argument": "clean(df)",
}


@pytest.mark.parametrize("body", list(STORY_TWO_VARIANTS.values()), ids=list(STORY_TWO_VARIANTS))
def test_backward_slice_of_the_story_two_notebook(body: str) -> None:
    """US2 scenario 1 / SC-002: the slice is cells 1, 2, 3, 4, and 6, never cell 5."""
    cells = [(cell_id, body if cell_id == "c3" else source) for cell_id, source in STORY_TWO]
    graph = build_graph(analyse_cells(cells), observations={"c3": {"df"}})
    result = graph.backward_slice(["c6"])
    assert result.cells == ("c1", "c2", "c3", "c4", "c6")


@pytest.mark.parametrize("body", list(STORY_TWO_VARIANTS.values()), ids=list(STORY_TWO_VARIANTS))
def test_the_mutating_cell_is_a_definer_once_it_has_been_observed(body: str) -> None:
    """US2 scenarios 2 to 4 / US3 scenario 3: the observation makes the cell a definer."""
    cells = [(cell_id, body if cell_id == "c3" else source) for cell_id, source in STORY_TWO]
    graph = build_graph(analyse_cells(cells), observations={"c3": {"df"}})
    assert "df" in graph.changed_set("c3")
    assert graph.definer_for("c4", "df") == "c3"


def test_without_the_observation_the_in_place_cell_is_not_a_definer() -> None:
    """FR-007: the static facts carry no list of mutating methods.

    This is the test that fails if someone reintroduces one.
    """
    graph = build_graph(analyse_cells(list(STORY_TWO)))
    assert graph.changed_set("c3") == frozenset()
    assert graph.definer_for("c4", "df") == "c2"


def test_the_backward_slice_lists_the_unresolved_reads_inside_it() -> None:
    """US2 scenario 5 / FR-021: packaging refuses a notebook that would fail with a name error."""
    graph = graph_of(
        ("c1", "df = load(raw_path)"),
        ("c2", "peaks = find(df)"),
        ("c3", "unrelated = other_missing_name"),
    )
    result = graph.backward_slice(["c2"])
    assert result.cells == ("c1", "c2")
    assert ("c1", "raw_path") in {(read.cell_id, read.name) for read in result.unresolved_reads}
    assert "other_missing_name" not in {read.name for read in result.unresolved_reads}


def test_the_backward_slice_of_several_seeds_is_their_union_in_written_order() -> None:
    """FR-021: those cells and every enabled cell they transitively depend on."""
    graph = graph_of(*STALE_NOTEBOOK)
    assert graph.backward_slice(["c4", "c6"]).cells == ("c1", "c2", "c3", "c4", "c6")


def test_the_backward_slice_of_a_cell_with_no_dependencies_is_itself() -> None:
    graph = graph_of(*STALE_NOTEBOOK)
    assert graph.backward_slice(["c1"]).cells == ("c1",)


def test_the_backward_slice_excludes_a_disabled_dependency() -> None:
    """FR-014: the slice is over enabled cells, so a disabled definer is routed around."""
    graph = build_graph(analyse_cells(ALTERNATIVES), enabled={"c2": False})
    assert graph.backward_slice(["c4"]).cells == ("c1", "c3", "c4")


def test_the_changed_set_is_the_union_of_the_estimate_and_the_observation() -> None:
    """FR-022 / US3 scenario 6: an observation only adds."""
    graph = build_graph(
        analyse_cells([("c1", "df = load()\nlookup = build()\n")]),
        observations={"c1": {"cache"}},
    )
    assert graph.changed_set("c1") == frozenset({"df", "lookup", "cache"})


def test_an_observation_never_removes_a_static_edge() -> None:
    """FR-030 / SC-008 / US3 scenario 6.

    The conditional-assignment case: the static estimate says the cell changes
    ``df``, the observation says it did not, and the edge stays because the
    changed set is the union.
    """
    cells = [("c1", "if flag:\n    df = load()\n"), ("c2", "peaks = find(df)")]
    without = build_graph(analyse_cells(cells))
    with_observation = build_graph(analyse_cells(cells), observations={"c1": set()})
    assert edge_tuples(without) == edge_tuples(with_observation)
    assert ("c2", "c1", "df") in edge_tuples(with_observation)


def test_an_observation_may_be_an_object_exposing_changed_names() -> None:
    """The seam the runtime observation record uses, so this module need not import it."""

    class _Observation:
        cell_id = "c1"
        changed_names = frozenset({"df"})

    graph = build_graph(
        analyse_cells([("c1", "normalise(df)"), ("c2", "peaks = find(df)")]),
        observations={"c1": _Observation()},
    )
    assert graph.definer_for("c2", "df") == "c1"


def test_an_observation_of_the_wrong_shape_is_rejected() -> None:
    """A silent no-op here would drop a definer, which is the direction FR-002 forbids."""
    with pytest.raises(TypeError):
        build_graph(analyse_cells([("c1", "a = 1")]), observations={"c1": 42})
    with pytest.raises(TypeError):
        build_graph(analyse_cells([("c1", "a = 1")]), observations={"c1": "df"})


def test_the_changed_set_answers_for_a_disabled_cell() -> None:
    """FR-022 asks about a cell, not about the graph's shape."""
    graph = graph_of(("c1", "a = 1"), ("c2", "b = 2"), enabled={"c2": False})
    assert graph.changed_set("c2") == frozenset({"b"})


def test_the_changed_set_rejects_an_unknown_cell() -> None:
    graph = graph_of(("c1", "a = 1"))
    with pytest.raises(KeyError):
        graph.changed_set("nope")


#: US1 scenario 4 / SC-013: cells A, B, and C each change ``df`` in written order.
ABC_NOTEBOOK = (
    ("a", "df = load()"),
    ("b", "df = df.dropna()"),
    ("c", "df = df.head()"),
)


def test_the_definer_query_answers_with_the_written_order_definer() -> None:
    """US1 scenario 4 / FR-023 / SC-013.

    The session compares this with the cell that last bound the name in the
    kernel, and marks the re-run out of order when they differ.
    """
    graph = graph_of(*ABC_NOTEBOOK)
    assert graph.definer_for("b", "df") == "a"
    assert graph.definer_for("c", "df") == "b"


def test_the_definer_query_returns_none_when_no_cell_above_defines_the_name() -> None:
    """FR-023: "or that none does"."""
    graph = graph_of(*ABC_NOTEBOOK)
    assert graph.definer_for("a", "df") is None
    assert graph.definer_for("c", "never_bound") is None


def test_the_definer_query_skips_a_disabled_cell() -> None:
    """FR-014 again: a disabled cell does not define."""
    graph = build_graph(analyse_cells(list(ABC_NOTEBOOK)), enabled={"b": False})
    assert graph.definer_for("c", "df") == "a"


def test_the_definer_query_matches_the_edge_the_graph_drew() -> None:
    """The two must not be able to disagree: the session acts on the definer query."""
    graph = graph_of(
        ("c1", "from numpy import *"),
        ("c2", "df = load()"),
        ("c3", "peaks = find(df)\nvalues = array(peaks)\n"),
    )
    for edge in graph.edges:
        assert graph.definer_for(edge.reader, edge.name) == edge.definer


def test_the_definer_query_rejects_a_cell_that_is_not_in_the_graph() -> None:
    graph = graph_of(*ABC_NOTEBOOK)
    with pytest.raises(KeyError):
        graph.definer_for("nope", "df")


# ---------------------------------------------------------------------------
# FR-036 — the closed flag enumeration
# ---------------------------------------------------------------------------


def test_the_flag_enumeration_holds_exactly_the_seven_spec_flags() -> None:
    """FR-036: exactly the flags the spec names, no more and no fewer."""
    assert {flag.value for flag in AnalysisFlag} == {
        "syntax_error",
        "opaque_cell_magic",
        "unknown_bindings",
        "unknown_block_call",
        "unpredicted_change",
        "unobservable_name",
        "unresolved_read",
    }


@pytest.mark.parametrize("flag", list(AnalysisFlag), ids=[flag.value for flag in AnalysisFlag])
def test_every_flag_has_a_human_readable_message(flag: AnalysisFlag) -> None:
    """FR-036: one enumeration, each member with a human-readable message."""
    assert flag.message_template.strip()
    assert "{cell_id}" in flag.message_template


def test_a_flag_message_renders_its_fields() -> None:
    rendered = AnalysisFlag.UNPREDICTED_CHANGE.message(cell_id="c4", name="df")
    assert rendered == "Cell c4 changed df without an assignment showing it."


def test_an_unresolved_read_renders_as_a_flag() -> None:
    """The unresolved read is a member of the same enumeration (FR-036)."""
    graph = graph_of(("c1", "peaks = find(df)"))
    flag = graph.unresolved_reads[0].as_flag()
    assert flag.flag is AnalysisFlag.UNRESOLVED_READ
    assert "df" in flag.message


def test_the_flag_values_are_plain_strings() -> None:
    """The record the codec writes must use JSON-serialisable primitives (FR-033)."""
    assert AnalysisFlag.SYNTAX_ERROR == "syntax_error"
    assert EdgeOrigin.STATIC_ASSIGNMENT == "static_assignment"


# ---------------------------------------------------------------------------
# Source hashing and the analysis version
# ---------------------------------------------------------------------------


def test_the_source_hash_changes_with_the_source() -> None:
    """FR-027: an observation is discarded when the cell's source hash changes."""
    assert source_hash("df = load()") == source_hash("df = load()")
    assert source_hash("df = load()") != source_hash("df = load2()")


def test_the_facts_carry_the_hash_of_the_source_they_were_computed_from() -> None:
    """FR-031: the record is keyed to the source hash."""
    assert facts_for("df = load()").source_hash == source_hash("df = load()")


def test_the_analysis_version_is_an_integer() -> None:
    """FR-031: the notebook-level record holds the analysis version."""
    assert isinstance(ANALYSIS_VERSION, int)


# ---------------------------------------------------------------------------
# FR-018 / SC-010 — cost
# ---------------------------------------------------------------------------


def test_building_the_graph_of_a_five_hundred_cell_notebook_is_fast() -> None:
    """SC-010: under five hundred milliseconds on the CI runner, one linear pass.

    The generated notebook chains its cells so every one of them draws an edge,
    which is the shape that would expose a quadratic definer lookup.

    The clock covers ``analyse_cells`` as well as ``build_graph``, which is the
    whole of what SC-010 names — "**analysing** a generated notebook of five
    hundred cells … **builds the graph** in under five hundred milliseconds". It
    used to cover only the build, and the ADR-054 spec 2 audit measured why that
    mattered: the build is ~11 ms and the analysis ~62 ms, so the spec's number
    was guarding the cheap sixth of the work with forty-two-fold headroom while
    the expensive part was unbounded. Together they are ~73 ms against 500 ms,
    which is roughly seven times over — enough for a loaded shared runner and
    tight enough that a regression of the analysis has somewhere to fail.
    """
    cells = [("c0", "seed = load()")]
    cells += [(f"c{index}", f"v{index} = f(v{index - 1}, seed)\n") for index in range(1, 500)]
    cells[1] = ("c1", "v1 = f(seed, seed)\n")

    start = time.perf_counter()
    facts = analyse_cells(cells)
    analysed = time.perf_counter()
    graph = build_graph(facts)
    elapsed = time.perf_counter() - start

    assert len(graph.cells) == 500
    assert elapsed < 0.5, (
        f"analyse {(analysed - start) * 1000:.1f} ms + build {(elapsed - (analysed - start)) * 1000:.1f} ms"
    )


# ---------------------------------------------------------------------------
# FR-027 / FR-030 (T-008): joining an observation to the graph.
#
# The union of FR-030 is the invariant the whole design rests on: an
# observation may add a definer and may never remove one. The two directions
# that could break it are a *smaller* observation, which must not shrink the
# changed set, and a *stale* observation, which must not contribute at all.
# ---------------------------------------------------------------------------

OBSERVED_SOURCE = "if flag:\n    df = load()\nlookup = build()\n"


def observation_for(
    source: str,
    changed: set[str],
    *,
    cell_id: str = "c1",
    unobservable: set[str] | None = None,
    source_text: str | None = None,
) -> ObservedChange:
    """An observation of *changed* keyed to the hash of *source_text* (default *source*)."""
    return ObservedChange(
        cell_id=cell_id,
        changed_names=frozenset(changed),
        unobservable_names=frozenset(unobservable or set()),
        source_hash=source_hash(source_text if source_text is not None else source),
    )


def test_fr030_an_observation_smaller_than_the_estimate_leaves_the_union_standing() -> None:
    """FR-030 / SC-008: the observation reports *less* and the changed set does not shrink.

    The cell assigns ``df`` on an untaken branch and ``lookup`` unconditionally.
    The run observed only ``lookup``. If the observation replaced the estimate,
    ``df``'s edge would vanish and cell 2 would keep showing a number computed
    from a value nothing marked stale — the exact failure ADR-054 §6.1 was
    written to remove. The union means the observed set being a strict subset of
    the static one changes nothing at all.
    """
    cells = [("c1", OBSERVED_SOURCE), ("c2", "peaks = find(df)")]
    observed = observation_for(OBSERVED_SOURCE, {"lookup"})
    assert observed.changed_names < analyse_cell("c1", OBSERVED_SOURCE).assigned, "the test needs a strict subset"

    without = build_graph(analyse_cells(cells))
    with_observation = build_graph(analyse_cells(cells), observations={"c1": observed})

    assert with_observation.changed_set("c1") == frozenset({"df", "lookup"})
    assert edge_tuples(with_observation) == edge_tuples(without)
    assert ("c2", "c1", "df") in edge_tuples(with_observation)
    assert with_observation.definer_for("c2", "df") == "c1"


def test_fr030_an_empty_observation_removes_nothing() -> None:
    """The degenerate subset: the cell was observed to change nothing at all."""
    cells = [("c1", OBSERVED_SOURCE), ("c2", "peaks = find(df)")]
    graph = build_graph(analyse_cells(cells), observations={"c1": observation_for(OBSERVED_SOURCE, set())})

    assert graph.changed_set("c1") == frozenset({"df", "lookup"})
    assert ("c2", "c1", "df") in edge_tuples(graph)


def test_fr030_an_observation_of_a_name_the_estimate_lacks_adds_a_definer() -> None:
    """FR-028 / US3 scenario 3: the in-place mutation the source does not show."""
    cells = [("c1", "normalise(df)"), ("c2", "peaks = find(df)")]
    graph = build_graph(
        analyse_cells(cells),
        observations={"c1": observation_for("normalise(df)", {"df"})},
    )

    assert graph.changed_set("c1") == frozenset({"df"})
    assert graph.definer_for("c2", "df") == "c1"
    assert ("c2", "c1", "df") in edge_tuples(graph)


def test_fr019_an_observed_definer_carries_the_observed_change_origin() -> None:
    """FR-019: the edge says why it exists, so the view can explain it."""
    graph = build_graph(
        analyse_cells([("c1", "normalise(df)"), ("c2", "peaks = find(df)")]),
        observations={"c1": observation_for("normalise(df)", {"df"})},
    )
    origins = {(edge.reader, edge.name): edge.origin for edge in graph.edges}

    assert origins[("c2", "df")] is EdgeOrigin.OBSERVED_CHANGE


def test_fr027_an_observation_for_other_source_is_discarded() -> None:
    """FR-027 / US3 scenario 4 / SC-008: the cell was edited, so the observation goes.

    The observation says cell 1 changed ``df`` in place. The person then edits
    the cell. The statement is now about code that no longer exists, so it must
    not keep drawing an edge, and the static estimate alone governs until the
    cell runs again.
    """
    cells = [("c1", "normalise(df)"), ("c2", "peaks = find(df)")]
    stale = observation_for("normalise(df)", {"df"}, source_text="denoise(df)")

    graph = build_graph(analyse_cells(cells), observations={"c1": stale})

    assert graph.changed_set("c1") == frozenset()
    assert graph.definer_for("c2", "df") is None
    assert ("c2", "df") in unresolved_tuples(graph)


def test_fr027_a_current_observation_survives_the_same_check() -> None:
    """The other direction: the hash matches, so the observation counts."""
    cells = [("c1", "normalise(df)"), ("c2", "peaks = find(df)")]
    graph = build_graph(
        analyse_cells(cells),
        observations={"c1": observation_for("normalise(df)", {"df"})},
    )

    assert graph.definer_for("c2", "df") == "c1"


def test_an_observation_without_a_source_hash_is_taken_at_face_value() -> None:
    """The seam stays open for a caller that hands over a bare set of names.

    ``build_graph`` reads ``source_hash`` when it is there and trusts the caller
    when it is not, so the plain-set form the graph agent's tests use keeps
    working and the keyed form gains the FR-027 check.
    """
    cells = [("c1", "normalise(df)"), ("c2", "peaks = find(df)")]
    graph = build_graph(analyse_cells(cells), observations={"c1": {"df"}})

    assert graph.definer_for("c2", "df") == "c1"


def test_an_observation_of_none_is_read_as_no_observation() -> None:
    """``LoadedCell.observation`` is ``None`` for a cell that has not run.

    Handing the mapping straight from a load to ``build_graph`` must not have to
    filter the ``None`` entries out first.
    """
    graph = build_graph(analyse_cells([("c1", "df = load()")]), observations={"c1": None})

    assert graph.changed_set("c1") == frozenset({"df"})


# ---------------------------------------------------------------------------
# FR-028 / FR-029 (T-008): the two flags only the observation can raise.
# ---------------------------------------------------------------------------


def test_fr028_an_unpredicted_change_names_the_cell_and_the_name() -> None:
    """FR-028 / US2 scenario 4: ``clean(df)`` changed ``df`` without an assignment showing it."""
    facts = analyse_cell("c4", "clean(df)")
    flags = observation_flags(facts, observation_for("clean(df)", {"df"}, cell_id="c4"))

    assert [flag.flag for flag in flags] == [AnalysisFlag.UNPREDICTED_CHANGE]
    assert flags[0].name == "df"
    assert flags[0].message == "Cell c4 changed df without an assignment showing it."


def test_fr028_a_change_the_estimate_predicted_raises_nothing() -> None:
    """The diagnostic is about the *gap* between the source and the run."""
    facts = analyse_cell("c1", "df = load()")

    assert observation_flags(facts, observation_for("df = load()", {"df"})) == ()


def test_fr028_one_flag_per_unpredicted_name_in_sorted_order() -> None:
    """Two names changed without an assignment produce two flags, deterministically."""
    facts = analyse_cell("c1", "clean(df, lookup)")
    flags = observation_flags(facts, observation_for("clean(df, lookup)", {"lookup", "df"}))

    assert [flag.name for flag in flags] == ["df", "lookup"]


def test_fr029_an_unobservable_name_is_reported_once_for_the_run() -> None:
    """FR-029 / US3 scenario 5: once per cell run, naming the cell and the name."""
    facts = analyse_cell("c5", "df = load()")
    flags = observation_flags(facts, observation_for("df = load()", {"df"}, cell_id="c5", unobservable={"handle"}))

    assert [flag.flag for flag in flags] == [AnalysisFlag.UNOBSERVABLE_NAME]
    assert flags[0].name == "handle"
    assert "handle" in flags[0].message and "c5" in flags[0].message


def test_the_observation_flags_of_a_cell_that_has_not_run_are_empty() -> None:
    """No observation, no diagnostic."""
    assert observation_flags(analyse_cell("c1", "clean(df)"), None) == ()


def test_a_stale_observation_raises_no_diagnostic() -> None:
    """FR-027: a message about code the person has since edited is noise."""
    facts = analyse_cell("c1", "clean(df)")
    stale = observation_for("clean(df)", {"df"}, unobservable={"handle"}, source_text="scrub(df)")

    assert observation_flags(facts, stale) == ()


def test_an_observation_for_another_cell_is_refused() -> None:
    """Silently renaming the cell would put the wrong id in front of the person."""
    facts = analyse_cell("c1", "clean(df)")

    with pytest.raises(ValueError, match="c9"):
        observation_flags(facts, observation_for("clean(df)", {"df"}, cell_id="c9"))


def test_fr036_the_two_observation_flags_are_members_of_the_one_enumeration() -> None:
    """FR-036: seven flags, and the two raised here are among them, not beside them."""
    assert AnalysisFlag.UNPREDICTED_CHANGE in set(AnalysisFlag)
    assert AnalysisFlag.UNOBSERVABLE_NAME in set(AnalysisFlag)
    assert len(set(AnalysisFlag)) == 7


# ---------------------------------------------------------------------------
# FR-031 to FR-034 (T-009): the metadata codec.
# ---------------------------------------------------------------------------

CODEC_NOTEBOOK: list[tuple[str, str]] = [
    ("c1", "import pandas as pd\ndf = pd.read_csv(path)\n"),
    ("c2", "%time df = df.dropna()\n"),
    ("c3", "lookup = build()\n"),
    ("c4", "clean(df)\n"),
    ("c5", "df.head()\n"),
    ("c6", "peaks = find(df, lookup)\nscistudio.output(peaks=peaks)\n"),
    ("c7", "scistudio.input('threshold')\nblocks.run('smooth')\nblocks.run(chosen)\n"),
    ("c8", "from numpy import *\n"),
    ("c9", "%%time\ndf = broken(\n"),
    ("c10", "df = broken(\n"),
]


def stored_notebook(
    cells: Sequence[tuple[str, str]],
    observations: Mapping[str, ObservedChange] | None = None,
) -> dict[str, dict[str, object]]:
    """Analyse *cells*, write each record, and return them keyed by cell id."""
    return {
        facts.cell_id: encode_cell_record(facts, (observations or {}).get(facts.cell_id))
        for facts in analyse_cells(cells)
    }


def reload_notebook(
    cells: Sequence[tuple[str, str]],
    records: Mapping[str, Mapping[str, object]],
    notebook_record: Mapping[str, object] | None = None,
) -> tuple[list[CellFacts], dict[str, ObservedChange]]:
    """Decode every cell the way a notebook load would (FR-032)."""
    version = notebook_record_version(notebook_record if notebook_record is not None else encode_notebook_record())
    loaded = [
        decode_cell_record(cell_id, source, records.get(cell_id), analysis_version=version) for cell_id, source in cells
    ]
    facts = [entry.facts for entry in loaded]
    observations = {entry.facts.cell_id: entry.observation for entry in loaded if entry.observation is not None}
    return facts, observations


def test_sc009_a_round_trip_through_cell_metadata_yields_an_identical_graph() -> None:
    """SC-009 / FR-032 / US5 scenario 5: the rebuilt graph equals the one built from source.

    Every flag-raising shape in the notebook is present — a magic line, an
    opaque cell magic, a star import, a non-literal block call, a syntax error,
    an output declaration, an input declaration — so the round trip is over the
    whole record and not just its easy half.
    """
    observations = {"c4": observation_for("clean(df)\n", {"df"}, cell_id="c4", unobservable={"handle"})}
    source_facts = analyse_cells(CODEC_NOTEBOOK)
    source_graph = build_graph(source_facts, observations=observations)

    records = stored_notebook(CODEC_NOTEBOOK, observations)
    loaded_facts, loaded_observations = reload_notebook(CODEC_NOTEBOOK, records)

    assert loaded_facts == list(source_facts)
    assert loaded_observations == observations
    assert build_graph(loaded_facts, observations=loaded_observations) == source_graph


def test_sc009_the_round_trip_survives_json_itself() -> None:
    """FR-033 / FR-034: the record is JSON, so a real serialise/parse changes nothing.

    Asserting on a dict alone would pass for a record holding tuples, sets, or a
    ``CellFlag``; only a trip through :mod:`json` proves the primitives claim.
    """
    observations = {"c4": observation_for("clean(df)\n", {"df"}, cell_id="c4")}
    records = stored_notebook(CODEC_NOTEBOOK, observations)

    reparsed = json.loads(json.dumps(records))
    loaded_facts, loaded_observations = reload_notebook(CODEC_NOTEBOOK, reparsed)

    assert build_graph(loaded_facts, observations=loaded_observations) == build_graph(
        analyse_cells(CODEC_NOTEBOOK), observations=observations
    )


def test_fr033_the_record_holds_only_json_primitives() -> None:
    """FR-033: object, array, string, integer, or null — nothing else, at any depth."""
    records = stored_notebook(CODEC_NOTEBOOK, {"c4": observation_for("clean(df)\n", {"df"}, cell_id="c4")})

    def walk(value: object, path: str) -> None:
        assert type(value) in (dict, list, str, int, bool, type(None)), f"{path}: {type(value).__name__}"
        if isinstance(value, dict):
            for key, item in value.items():
                assert type(key) is str, f"{path}: non-string key {key!r}"
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(records, "records")


def test_fr032_edges_are_not_stored() -> None:
    """FR-032: a second copy of the graph could only ever disagree with the first."""
    record = encode_cell_record(analyse_cell("c1", "df = load()"))

    assert "edges" not in record
    assert "version_edges" not in record
    assert not any("edge" in key for key in json.loads(json.dumps(record)))


def test_fr032_a_record_whose_source_hash_does_not_match_is_discarded() -> None:
    """FR-032 / SC-008: the cell is re-analysed, and from its current source."""
    stored = encode_cell_record(analyse_cell("c1", "df = load()"))

    loaded = decode_cell_record("c1", "peaks = find(df)", stored)

    assert loaded.reanalysed is True
    assert loaded.facts == analyse_cell("c1", "peaks = find(df)")
    assert loaded.facts.assigned == frozenset({"peaks"})
    assert loaded.facts.source_hash == source_hash("peaks = find(df)")


def test_fr032_a_matching_record_is_reused_rather_than_recomputed() -> None:
    """The other direction, so the discard test above is not vacuously true."""
    stored = encode_cell_record(analyse_cell("c1", "df = load()"))

    loaded = decode_cell_record("c1", "df = load()", stored)

    assert loaded.reanalysed is False
    assert loaded.facts == analyse_cell("c1", "df = load()")


def test_fr032_a_cell_with_no_record_is_analysed_from_source() -> None:
    """A notebook written by Jupyter alone carries no record, and must still load."""
    loaded = decode_cell_record("c1", "df = load()", None)

    assert loaded.reanalysed is True
    assert loaded.facts == analyse_cell("c1", "df = load()")
    assert loaded.observation is None


def test_fr027_a_stored_observation_for_other_source_is_discarded_on_load() -> None:
    """FR-027: the codec discards it too, so a stale one never reaches the graph."""
    facts = analyse_cell("c1", "clean(df)")
    stored = encode_cell_record(facts, observation_for("clean(df)", {"df"}))

    loaded = decode_cell_record("c1", "scrub(df)", stored)

    assert loaded.reanalysed is True
    assert loaded.observation is None


def test_a_stored_observation_for_the_current_source_survives_a_reanalysis() -> None:
    """The two hashes are resolved independently, as the record stores them.

    A record whose facts were written by an older pass but whose observation is
    keyed to the source now on screen keeps the observation: it is a true
    statement about the code as it stands.
    """
    facts = analyse_cell("c1", "clean(df)")
    stored = encode_cell_record(facts, observation_for("clean(df)", {"df"}))
    stored["source_hash"] = source_hash("something else entirely")

    loaded = decode_cell_record("c1", "clean(df)", stored)

    assert loaded.reanalysed is True
    assert loaded.observation is not None
    assert loaded.observation.changed_names == frozenset({"df"})


def test_fr033_a_key_the_analysis_does_not_recognise_survives_a_rewrite() -> None:
    """FR-033: another tool's metadata under the same key is not this analysis's to drop."""
    existing = {
        "another_tool": {"cursor": 4, "notes": ["keep", "me"]},
        "source_hash": "an old value this analysis owns and replaces",
    }
    facts = analyse_cell("c1", "df = load()")

    record = encode_cell_record(facts, existing=existing)

    assert record["another_tool"] == {"cursor": 4, "notes": ["keep", "me"]}
    assert record["source_hash"] == facts.source_hash
    # And the unknown key is still there after the record has been read back.
    loaded = decode_cell_record("c1", "df = load()", record)
    assert loaded.facts == facts
    assert encode_cell_record(loaded.facts, existing=record)["another_tool"] == existing["another_tool"]


def test_fr033_an_unknown_key_survives_beside_a_record_the_codec_writes() -> None:
    """The dispatch's shape: a record written *beside* an unheard-of key, both read back."""
    existing = {"jupyterlab_extension": {"pinned": True}}
    facts = analyse_cell("c1", "df = load()")
    observation = observation_for("df = load()", {"df"})

    record = encode_cell_record(facts, observation, existing=existing)
    reparsed = json.loads(json.dumps(record))
    loaded = decode_cell_record("c1", "df = load()", reparsed)

    assert reparsed["jupyterlab_extension"] == {"pinned": True}
    assert loaded.facts == facts
    assert loaded.observation == observation


def test_an_observation_that_no_longer_applies_is_dropped_from_the_rewritten_record() -> None:
    """The recognised keys are rewritten wholesale, so a stale one cannot linger."""
    facts = analyse_cell("c1", "clean(df)")
    with_observation = encode_cell_record(facts, observation_for("clean(df)", {"df"}))

    rewritten = encode_cell_record(facts, None, existing=with_observation)

    assert "observation" not in rewritten


def test_the_record_does_not_store_the_cell_id() -> None:
    """The id belongs to the notebook cell; a second copy is one more thing to disagree."""
    record = encode_cell_record(analyse_cell("c1", "df = load()"))

    assert "cell_id" not in record
    assert decode_cell_record("renamed", "df = load()", record).facts.cell_id == "renamed"


def test_encoding_an_observation_for_another_cell_is_refused() -> None:
    """A record is written onto one cell; an observation of another does not belong on it."""
    facts = analyse_cell("c1", "clean(df)")

    with pytest.raises(ValueError, match="c9"):
        encode_cell_record(facts, observation_for("clean(df)", {"df"}, cell_id="c9"))


def test_the_flags_of_a_cell_round_trip_with_their_positions() -> None:
    """FR-031: the record holds the flags, message and position included."""
    facts = analyse_cell("c1", "df = broken(\n")
    assert facts.has_flag(AnalysisFlag.SYNTAX_ERROR)

    loaded = decode_cell_record("c1", "df = broken(\n", json.loads(json.dumps(encode_cell_record(facts))))

    assert loaded.reanalysed is False
    assert loaded.facts.flags == facts.flags
    assert loaded.facts.flags[0].lineno == facts.flags[0].lineno


def test_the_declarations_and_block_calls_round_trip() -> None:
    """FR-008 to FR-010 survive the record, including the non-literal block id."""
    source = "scistudio.input('threshold')\nblocks.run('smooth')\nblocks.run(chosen)\nscistudio.output(peaks=peaks)\n"
    facts = analyse_cell("c1", source)

    loaded = decode_cell_record("c1", source, json.loads(json.dumps(encode_cell_record(facts))))

    assert loaded.facts.outputs == facts.outputs
    assert loaded.facts.inputs == facts.inputs
    assert loaded.facts.block_calls == facts.block_calls
    assert loaded.facts.block_calls[1].block_id is None


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        ({"source_hash": source_hash("df = load()"), "assigned": "df"}, "a string where an array belongs"),
        ({"source_hash": source_hash("df = load()"), "assigned": [1]}, "a non-string name"),
        (
            {"source_hash": source_hash("df = load()"), "flags": [{"flag": "not_a_flag", "message": "x"}]},
            "an unknown flag",
        ),
        ({"source_hash": source_hash("df = load()"), "flags": [{"message": "x"}]}, "a flag with no kind"),
        ({"source_hash": source_hash("df = load()"), "outputs": [{"keywords": ["a"]}]}, "an output with no arguments"),
        ({"source_hash": source_hash("df = load()"), "block_calls": [{"block_id": "b"}]}, "a block call with no line"),
        (
            {"source_hash": source_hash("df = load()"), "block_calls": [{"lineno": "3"}]},
            "a line number that is a string",
        ),
        (
            {"source_hash": source_hash("df = load()"), "flags": [{"flag": "syntax_error", "message": 3}]},
            "a flag message that is not a string",
        ),
        (
            {
                "source_hash": source_hash("df = load()"),
                "flags": [{"flag": "syntax_error", "message": "x", "name": 3}],
            },
            "a flag name that is neither a string nor null",
        ),
        ({"source_hash": source_hash("df = load()"), "flags": "syntax_error"}, "flags that are not an array"),
        ({"source_hash": source_hash("df = load()"), "outputs": 3}, "outputs that are not an array"),
        ({"source_hash": source_hash("df = load()"), "observation": []}, "an observation that is not an object"),
        (
            {"source_hash": source_hash("df = load()"), "observation": {"source_hash": 3}},
            "an observation source hash that is not a string",
        ),
        (
            {"source_hash": source_hash("df = load()"), "observation": {"changed_names": ["df"]}},
            "an observation with no source hash",
        ),
        ("not an object at all", "a record that is not an object"),
        (42, "a record that is a number"),
    ],
)
def test_a_malformed_record_costs_a_reanalysis_and_never_an_exception(record: object, reason: str) -> None:
    """FR-032: a record lives in a file a person can edit, so it must fail soft.

    A notebook that raised on load because one cell's metadata was hand-edited
    would be a notebook the person cannot open — the failure mode US5 exists to
    rule out.
    """
    loaded = decode_cell_record("c1", "df = load()", record)  # type: ignore[arg-type]

    assert loaded.reanalysed is True, reason
    assert loaded.facts == analyse_cell("c1", "df = load()")
    assert loaded.observation is None


def test_fr031_the_notebook_record_holds_the_analysis_version() -> None:
    """FR-031: one notebook-level record under the same key, holding the version."""
    record = encode_notebook_record()

    assert record == {"analysis_version": ANALYSIS_VERSION}
    assert notebook_record_version(record) == ANALYSIS_VERSION


def test_fr033_the_notebook_record_preserves_unknown_keys() -> None:
    """FR-033 applies at the notebook level too."""
    record = encode_notebook_record({"analysis_version": 0, "another_tool": {"seen": True}})

    assert record["analysis_version"] == ANALYSIS_VERSION
    assert record["another_tool"] == {"seen": True}


@pytest.mark.parametrize("record", [None, {}, {"analysis_version": "1"}, {"analysis_version": True}, []])
def test_a_notebook_with_no_readable_version_reports_none(record: object) -> None:
    """``None`` means the same thing for every unreadable shape: re-analyse."""
    assert notebook_record_version(record) is None  # type: ignore[arg-type]


def test_a_record_from_another_analysis_version_is_discarded() -> None:
    """FR-031: a record this release cannot vouch for is re-analysed, not trusted."""
    stored = encode_cell_record(analyse_cell("c1", "df = load()"))

    loaded = decode_cell_record("c1", "df = load()", stored, analysis_version=ANALYSIS_VERSION + 1)

    assert loaded.reanalysed is True
    assert loaded.observation is None


def test_a_notebook_with_no_version_record_re_analyses_every_cell() -> None:
    """A notebook Jupyter wrote carries no version, so nothing stored is trusted."""
    records = stored_notebook(CODEC_NOTEBOOK)
    loaded = [
        decode_cell_record(cell_id, source, records[cell_id], analysis_version=notebook_record_version(None))
        for cell_id, source in CODEC_NOTEBOOK
    ]

    assert all(entry.reanalysed for entry in loaded)
    # Re-analysed, but not wrong: the facts are the ones the source produces.
    assert [entry.facts for entry in loaded] == list(analyse_cells(CODEC_NOTEBOOK))


def test_encoding_the_same_facts_twice_produces_the_same_record() -> None:
    """A re-save must not churn the notebook in git: sets are written sorted."""
    facts = analyse_cell("c1", "a, b, c = f(x, y, z)")
    observation = observation_for("a, b, c = f(x, y, z)", {"c", "a", "b"})

    first = json.dumps(encode_cell_record(facts, observation), sort_keys=False)
    second = json.dumps(encode_cell_record(analyse_cell("c1", "a, b, c = f(x, y, z)"), observation))

    assert first == second


def test_the_codec_does_not_mutate_the_record_it_was_given() -> None:
    """FR-004: the codec is pure over the mapping it reads."""
    facts = analyse_cell("c1", "df = load()")
    existing = {"another_tool": {"cursor": 4}}
    snapshot = json.dumps(existing)

    encode_cell_record(facts, existing=existing)
    decode_cell_record("c1", "df = load()", encode_cell_record(facts, existing=existing))

    assert json.dumps(existing) == snapshot


def test_the_metadata_key_is_the_one_the_spec_names() -> None:
    """FR-031: the record lives under the ``scistudio`` key of cell metadata."""
    assert CELL_RECORD_KEY == "scistudio"


# ---------------------------------------------------------------------------
# T-011 — stability markers (ADR-052 §5, spec A-009).
# ---------------------------------------------------------------------------

#: Public names that cannot carry a runtime marker (ADR-052 §15): a ``str``, an
#: ``int``, a ``frozenset``, and two tuples. ``get_stability`` returns ``None``
#: for each by design, which the stability module's own docstring calls the
#: honest result.
NON_MARKABLE: frozenset[str] = frozenset(
    {"ANALYSIS_VERSION", "BLOCK_CALL_PATHS", "BUILTIN_NAMES", "CELL_RECORD_KEY", "INPUT_CALL_PATH", "OUTPUT_CALL_PATH"}
)


def test_t011_every_markable_public_symbol_carries_a_tier_and_a_since() -> None:
    """ADR-052 §5: tier and Since on every public symbol of the module."""
    undecorated: list[str] = []
    for name in dependency_analysis.__all__:
        if name in NON_MARKABLE:
            continue
        info = get_stability(getattr(dependency_analysis, name))
        if info is None or info.tier != "provisional" or info.since != "0.3.4":
            undecorated.append(f"{name}: {info}")

    assert not undecorated, "missing or wrong stability markers:\n  " + "\n  ".join(undecorated)


def test_t011_the_non_markable_list_has_not_drifted() -> None:
    """A symbol that gains a markable type must gain a marker, not stay on the list."""
    assert set(dependency_analysis.__all__) >= NON_MARKABLE
    for name in NON_MARKABLE:
        value = getattr(dependency_analysis, name)
        assert isinstance(value, (str, int, frozenset, tuple)), name
        assert get_stability(value) is None, f"{name} can carry a marker now; take it off the list"


def test_t011_the_package_facade_exports_what_the_module_does() -> None:
    """The façade must not become a second, smaller surface that drifts from the module."""
    assert set(explore_package.__all__) == set(dependency_analysis.__all__)
    for name in explore_package.__all__:
        assert getattr(explore_package, name) is getattr(dependency_analysis, name), name


def test_t011_the_package_attribute_named_fingerprint_is_still_the_module() -> None:
    """The façade deliberately does not re-export the ``fingerprint`` function.

    Re-exporting it would rebind ``scistudio.explore.fingerprint`` from the
    module to the function, and ``import scistudio.explore.fingerprint as m``
    would then bind the function — a trap for every later caller, including the
    tests in ``test_fingerprint.py``.
    """
    from types import ModuleType

    assert isinstance(explore_package.fingerprint, ModuleType)
    assert explore_package.fingerprint.__name__ == "scistudio.explore.fingerprint"


def test_a009_the_explore_package_is_not_a_canonical_public_root() -> None:
    """A-009: the frozen surface inventory is unchanged because this is not a root.

    Confirmed against the two lists that define the frozen surface rather than
    assumed, so a later promotion to a root is a listing change caught here and
    not a silent one.
    """
    from tests.api.test_public_surface import CANONICAL_ROOTS as SURFACE_ROOTS
    from tests.api.test_stability_decorators import CANONICAL_ROOTS as DECORATOR_ROOTS

    assert not [root for root in SURFACE_ROOTS if root.startswith("scistudio.explore")]
    assert not [root for root in DECORATOR_ROOTS if root.startswith("scistudio.explore")]
