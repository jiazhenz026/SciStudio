"""The completion vocabulary and its evaluator — ADR-053 spec §4.4 "Conditions".

Asserts: each of the sixteen vocabulary terms true *and* false against a
constructed state; ``all`` / ``any``; evaluation leaves no side effects
(FR-055). Plus the parts of FR-048 through FR-054 that live in this module: no
negation, unknown terms rejected at parse time, a condition already true on
entry satisfied immediately, and the FR-050 event map keyed by constants rather
than literals.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    GIT_HEAD_CHANGED,
    INTERACTIVE_COMPLETE,
    WORKFLOW_CHANGED,
    WORKFLOW_COMPLETED,
)
from scistudio.tutorials.conditions import (
    BLOCKS_RELOADED_TERMS,
    COMBINATORS,
    EVENT_TERM_MAP,
    FILE_CHANGED_TERMS,
    TERM_SPECS,
    UI_EVENT_NAMES,
    VOCABULARY,
    Condition,
    ConditionValidationError,
    ExternalEventNames,
    RunSummary,
    build_event_term_map,
    evaluate,
    event_types_for_condition,
    parse_condition,
    terms_for_event,
)
from scistudio.workflow.definition import WorkflowDefinition

from .conftest import StubProductState, snapshot_tree

EXTERNAL = ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed")


# ---------------------------------------------------------------------------
# The vocabulary itself (FR-045, FR-047, FR-048)
# ---------------------------------------------------------------------------


def test_the_vocabulary_is_exactly_the_sixteen_terms_of_fr_047() -> None:
    assert set(VOCABULARY) == {
        "node_exists",
        "edge_exists",
        "config_equals",
        "run_succeeded",
        "port_has_output",
        "block_registered",
        "type_registered",
        "previewer_registered",
        "plot_exists",
        "file_exists",
        "git_branch_exists",
        "git_current_branch",
        "library_contains",
        "interaction_completed",
        "page_reached",
        "ui_event",
    }
    assert len(VOCABULARY) == 16
    assert set(TERM_SPECS) == VOCABULARY


def test_the_combinators_are_all_and_any_and_negation_is_absent() -> None:
    """FR-048: a step advancing on absence advances by the user doing nothing."""
    assert set(COMBINATORS) == {"all", "any"}
    for forbidden in ("not", "none", "never", "absent"):
        assert forbidden not in VOCABULARY | COMBINATORS


# ---------------------------------------------------------------------------
# Parsing (FR-049)
# ---------------------------------------------------------------------------


def test_unknown_term_is_rejected_and_the_message_lists_the_vocabulary() -> None:
    with pytest.raises(ConditionValidationError) as excinfo:
        parse_condition({"blocks_are_pretty": {}})
    assert "blocks_are_pretty" in str(excinfo.value)
    assert "node_exists" in str(excinfo.value)


def test_negation_is_rejected_like_any_other_unknown_term() -> None:
    with pytest.raises(ConditionValidationError):
        parse_condition({"not": [{"node_exists": {"block_type": "LoadCSV"}}]})


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"node_exists": {"block_type": "A"}, "file_exists": {"path": "x"}},
        [{"node_exists": {"block_type": "A"}}],
        "node_exists",
    ],
)
def test_a_condition_is_a_single_key_mapping(raw: object) -> None:
    with pytest.raises(ConditionValidationError):
        parse_condition(raw)


def test_unknown_term_argument_is_rejected() -> None:
    with pytest.raises(ConditionValidationError) as excinfo:
        parse_condition({"file_exists": {"path": "x", "colour": "blue"}})
    assert "colour" in str(excinfo.value)


def test_edge_exists_requires_a_source_and_a_target() -> None:
    with pytest.raises(ConditionValidationError):
        parse_condition({"edge_exists": {"source_block_type": "LoadCSV"}})
    parsed = parse_condition({"edge_exists": {"source_block_type": "LoadCSV", "target_block_type": "SaveCSV"}})
    assert parsed.term == "edge_exists"


def test_library_contains_rejects_an_unknown_kind() -> None:
    with pytest.raises(ConditionValidationError) as excinfo:
        parse_condition({"library_contains": {"kind": "workflow", "name": "x"}})
    assert "block" in str(excinfo.value)


def test_the_ui_event_name_set_is_the_declared_one() -> None:
    assert set(UI_EVENT_NAMES) == {"preview_expanded", "block_source_viewed"}


@pytest.mark.parametrize("name", sorted(UI_EVENT_NAMES))
def test_every_ui_event_name_is_accepted(name: str) -> None:
    assert parse_condition({"ui_event": {"name": name}}).args["name"] == name


@pytest.mark.parametrize("bad", ["preview_enlarged", "tab_opened", "clicked", "Preview_Expanded"])
def test_a_ui_event_name_outside_the_set_is_rejected_naming_the_field_and_the_values(bad: str) -> None:
    """FR-052 names real product actions; an unlisted one is a step that never advances."""
    with pytest.raises(ConditionValidationError) as excinfo:
        parse_condition({"ui_event": {"name": bad}})
    message = str(excinfo.value)
    assert "ui_event" in message
    assert "name" in message
    assert bad in message
    for accepted in UI_EVENT_NAMES:
        assert accepted in message


def test_an_empty_combinator_is_rejected() -> None:
    with pytest.raises(ConditionValidationError):
        parse_condition({"all": []})


def test_terms_walks_the_whole_tree() -> None:
    condition = parse_condition(
        {
            "all": [
                {"node_exists": {"block_type": "LoadCSV"}},
                {"any": [{"file_exists": {"path": "x"}}, {"ui_event": {"name": "preview_expanded"}}]},
            ]
        }
    )
    assert condition.terms() == {"node_exists", "file_exists", "ui_event"}
    assert condition.is_combinator is True


# ---------------------------------------------------------------------------
# Every term, true and false
# ---------------------------------------------------------------------------


def _state(tmp_path: Path, loaded_workflow: WorkflowDefinition) -> StubProductState:
    return StubProductState(
        project_dir=tmp_path,
        tutorial_library_dir=tmp_path / ".library",
        workflow_definition=loaded_workflow,
        block_types=frozenset({"LoadCSV", "SaveCSV"}),
        data_types=frozenset({"DataFrame"}),
        previewer_types=frozenset({"DataFrame"}),
        plots=(("plot-1", "save-1", "table"),),
        runs=(RunSummary(run_id="r1", workflow_id="wf-1", succeeded=True, succeeded_node_ids=frozenset({"load-1"})),),
        ports_with_output=frozenset({("load-1", "table")}),
        branches=frozenset({"main", "imaging"}),
        current_branch="imaging",
        library=frozenset({("type", "CellTable")}),
        interactions=frozenset({"router-1"}),
        pages=frozenset({"what-is-a-block"}),
        events=frozenset({"preview_expanded"}),
    )


TRUE_CASES: list[tuple[str, dict[str, object]]] = [
    ("node_exists", {"node_exists": {"block_type": "LoadCSV"}}),
    ("edge_exists", {"edge_exists": {"source_block_type": "LoadCSV", "target_block_type": "SaveCSV"}}),
    ("config_equals", {"config_equals": {"node_id": "load-1", "key": "path", "value": "data/raw/cells.csv"}}),
    ("run_succeeded", {"run_succeeded": {}}),
    ("port_has_output", {"port_has_output": {"node_id": "load-1", "port": "table"}}),
    ("block_registered", {"block_registered": {"block_type": "LoadCSV"}}),
    ("type_registered", {"type_registered": {"type_name": "DataFrame"}}),
    ("previewer_registered", {"previewer_registered": {"type_name": "DataFrame"}}),
    ("plot_exists", {"plot_exists": {"node_id": "save-1", "port": "table"}}),
    ("file_exists", {"file_exists": {"path": "data/raw/cells.csv"}}),
    ("git_branch_exists", {"git_branch_exists": {"branch": "imaging"}}),
    ("git_current_branch", {"git_current_branch": {"branch": "imaging"}}),
    ("library_contains", {"library_contains": {"kind": "type", "name": "CellTable"}}),
    ("interaction_completed", {"interaction_completed": {"node_id": "router-1"}}),
    ("page_reached", {"page_reached": {"page": "what-is-a-block"}}),
    ("ui_event", {"ui_event": {"name": "preview_expanded"}}),
]

FALSE_CASES: list[tuple[str, dict[str, object]]] = [
    ("node_exists", {"node_exists": {"block_type": "Cluster"}}),
    ("edge_exists", {"edge_exists": {"source_block_type": "SaveCSV", "target_block_type": "LoadCSV"}}),
    ("config_equals", {"config_equals": {"node_id": "load-1", "key": "path", "value": "elsewhere.csv"}}),
    ("run_succeeded", {"run_succeeded": {"node_id": "save-1"}}),
    ("port_has_output", {"port_has_output": {"node_id": "save-1", "port": "table"}}),
    ("block_registered", {"block_registered": {"block_type": "Cluster"}}),
    ("type_registered", {"type_registered": {"type_name": "Image"}}),
    ("previewer_registered", {"previewer_registered": {"type_name": "Image"}}),
    ("plot_exists", {"plot_exists": {"node_id": "load-1"}}),
    ("file_exists", {"file_exists": {"path": "data/raw/absent.csv"}}),
    ("git_branch_exists", {"git_branch_exists": {"branch": "release"}}),
    ("git_current_branch", {"git_current_branch": {"branch": "main"}}),
    ("library_contains", {"library_contains": {"kind": "block", "name": "CellTable"}}),
    ("interaction_completed", {"interaction_completed": {"node_id": "router-2"}}),
    ("page_reached", {"page_reached": {"page": "what-is-a-plot"}}),
    ("ui_event", {"ui_event": {"name": "block_source_viewed"}}),
]


@pytest.fixture
def populated_project(tmp_path: Path) -> Path:
    target = tmp_path / "data" / "raw"
    target.mkdir(parents=True)
    (target / "cells.csv").write_text("well,mean\nA1,0.42\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(("term", "raw"), TRUE_CASES, ids=[case[0] for case in TRUE_CASES])
def test_every_term_can_be_true(
    term: str, raw: dict[str, object], populated_project: Path, loaded_workflow: WorkflowDefinition
) -> None:
    state = _state(populated_project, loaded_workflow)
    assert evaluate(parse_condition(raw), state) is True


@pytest.mark.parametrize(("term", "raw"), FALSE_CASES, ids=[case[0] for case in FALSE_CASES])
def test_every_term_can_be_false(
    term: str, raw: dict[str, object], populated_project: Path, loaded_workflow: WorkflowDefinition
) -> None:
    state = _state(populated_project, loaded_workflow)
    assert evaluate(parse_condition(raw), state) is False


def test_the_true_and_false_cases_cover_the_whole_vocabulary() -> None:
    assert {case[0] for case in TRUE_CASES} == VOCABULARY
    assert {case[0] for case in FALSE_CASES} == VOCABULARY


def test_terms_reading_the_workflow_are_false_when_no_workflow_is_open(tmp_path: Path) -> None:
    state = StubProductState(project_dir=tmp_path, workflow_definition=None)
    for raw in (
        {"node_exists": {"block_type": "LoadCSV"}},
        {"edge_exists": {"source_node_id": "a", "target_node_id": "b"}},
        {"config_equals": {"node_id": "a", "key": "k", "value": 1}},
    ):
        assert evaluate(parse_condition(raw), state) is False


def test_file_exists_is_false_without_a_project() -> None:
    state = StubProductState(project_dir=None)
    assert evaluate(parse_condition({"file_exists": {"path": "x"}}), state) is False


def test_run_succeeded_can_be_scoped_to_a_workflow(
    populated_project: Path, loaded_workflow: WorkflowDefinition
) -> None:
    state = _state(populated_project, loaded_workflow)
    assert evaluate(parse_condition({"run_succeeded": {"workflow_id": "wf-1"}}), state) is True
    assert evaluate(parse_condition({"run_succeeded": {"workflow_id": "wf-2"}}), state) is False


def test_node_exists_can_be_narrowed_to_a_node_id(populated_project: Path, loaded_workflow: WorkflowDefinition) -> None:
    state = _state(populated_project, loaded_workflow)
    assert evaluate(parse_condition({"node_exists": {"block_type": "LoadCSV", "node_id": "load-1"}}), state) is True
    assert evaluate(parse_condition({"node_exists": {"block_type": "LoadCSV", "node_id": "load-9"}}), state) is False


# ---------------------------------------------------------------------------
# Combinators (FR-048)
# ---------------------------------------------------------------------------


def test_all_and_any(populated_project: Path, loaded_workflow: WorkflowDefinition) -> None:
    state = _state(populated_project, loaded_workflow)
    truthy = {"node_exists": {"block_type": "LoadCSV"}}
    falsy = {"node_exists": {"block_type": "Cluster"}}

    assert evaluate(parse_condition({"all": [truthy, truthy]}), state) is True
    assert evaluate(parse_condition({"all": [truthy, falsy]}), state) is False
    assert evaluate(parse_condition({"any": [truthy, falsy]}), state) is True
    assert evaluate(parse_condition({"any": [falsy, falsy]}), state) is False
    assert evaluate(parse_condition({"all": [{"any": [falsy, truthy]}, truthy]}), state) is True


# ---------------------------------------------------------------------------
# FR-054 and FR-055
# ---------------------------------------------------------------------------


def test_a_condition_already_true_on_entry_is_satisfied_immediately(
    populated_project: Path, loaded_workflow: WorkflowDefinition
) -> None:
    """FR-054: conditions are statements about state, not about the user just acting."""
    state = _state(populated_project, loaded_workflow)
    condition = parse_condition({"node_exists": {"block_type": "LoadCSV"}})
    assert evaluate(condition, state) is True
    assert evaluate(condition, state) is True


def test_evaluation_is_side_effect_free(populated_project: Path, loaded_workflow: WorkflowDefinition) -> None:
    """FR-055: no file created, no registry mutated, no run triggered."""
    state = _state(populated_project, loaded_workflow)
    before = snapshot_tree(populated_project)
    frozen = (
        state.block_types,
        state.data_types,
        state.previewer_types,
        state.plots,
        state.runs,
        state.library,
        state.branches,
    )

    for _, raw in TRUE_CASES + FALSE_CASES:
        evaluate(parse_condition(raw), state)

    assert snapshot_tree(populated_project) == before
    assert (
        state.block_types,
        state.data_types,
        state.previewer_types,
        state.plots,
        state.runs,
        state.library,
        state.branches,
    ) == frozen
    assert state.reads, "evaluation should have read product state"


def test_a_missing_file_exists_target_is_not_created(tmp_path: Path) -> None:
    state = StubProductState(project_dir=tmp_path)
    assert evaluate(parse_condition({"file_exists": {"path": "nested/thing.tif"}}), state) is False
    assert not (tmp_path / "nested").exists()


# ---------------------------------------------------------------------------
# The event map (FR-050, FR-051, FR-053)
# ---------------------------------------------------------------------------


def test_the_engine_half_of_the_map_is_keyed_by_the_imported_constants() -> None:
    assert set(EVENT_TERM_MAP) == {
        WORKFLOW_CHANGED,
        WORKFLOW_COMPLETED,
        BLOCK_DONE,
        BLOCK_ERROR,
        GIT_HEAD_CHANGED,
        INTERACTIVE_COMPLETE,
    }
    assert EVENT_TERM_MAP[WORKFLOW_CHANGED] == {"node_exists", "edge_exists", "config_equals"}
    assert EVENT_TERM_MAP[WORKFLOW_COMPLETED] == {"run_succeeded", "port_has_output"}
    assert EVENT_TERM_MAP[GIT_HEAD_CHANGED] == {"git_branch_exists", "git_current_branch"}
    assert EVENT_TERM_MAP[INTERACTIVE_COMPLETE] == {"interaction_completed"}


def test_the_two_api_layer_events_are_supplied_rather_than_written_down() -> None:
    """FR-050 + checklist §6.1.2: the tutorials package may not import ``scistudio.api``."""
    complete = build_event_term_map(EXTERNAL)
    assert complete["blocks.reloaded"] == BLOCKS_RELOADED_TERMS
    assert complete["file.changed"] == FILE_CHANGED_TERMS
    assert set(BLOCKS_RELOADED_TERMS) == {
        "block_registered",
        "type_registered",
        "previewer_registered",
        "library_contains",
    }
    assert set(FILE_CHANGED_TERMS) == {"file_exists"}
    # Renaming the events on the API side moves the map with them.
    renamed = build_event_term_map(ExternalEventNames(blocks_reloaded="x.reloaded", file_changed="x.changed"))
    assert renamed["x.reloaded"] == BLOCKS_RELOADED_TERMS


def test_no_module_in_the_tutorials_package_writes_the_two_api_event_names() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials"
    for module in package.rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        for name in ("blocks.reloaded", "file.changed"):
            for quoted in (f'"{name}"', f"'{name}'"):
                assert quoted not in source, f"{module} writes the event name {name!r} as a literal"


def test_the_three_leaf_modules_import_neither_the_api_nor_the_runtime() -> None:
    """Checklist §6.1.2 for the modules this slice owns.

    ``manifest``, ``conditions`` and ``actions`` may not reach ``scistudio.api``
    (the route layer injects what they need, keeping ``api -> tutorials``
    one-way) nor ``discovery`` / ``driver`` / ``session``. If one of them looks
    as though it needs one, the boundary is wrong.
    """
    package = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials"
    forbidden = (
        "scistudio.api",
        "scistudio.tutorials.discovery",
        "scistudio.tutorials.driver",
        "scistudio.tutorials.session",
    )
    for filename in ("manifest.py", "conditions.py", "actions.py"):
        module = package / filename
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            for target in imported:
                assert not any(target.startswith(bad) for bad in forbidden), f"{module} imports {target}"


def test_terms_for_event_and_event_types_for_condition() -> None:
    assert terms_for_event(WORKFLOW_CHANGED) == {"node_exists", "edge_exists", "config_equals"}
    assert terms_for_event("nothing.at.all") == frozenset()
    assert terms_for_event("blocks.reloaded", EXTERNAL) == BLOCKS_RELOADED_TERMS

    condition = parse_condition({"all": [{"node_exists": {"block_type": "A"}}, {"file_exists": {"path": "x.tif"}}]})
    reached = event_types_for_condition(condition, EXTERNAL)
    assert WORKFLOW_CHANGED in reached
    assert "file.changed" in reached


def test_a_condition_no_event_reaches_is_visible_as_such() -> None:
    """FR-053 exists for exactly this: some truth changes reach no mapped event."""
    condition = parse_condition({"page_reached": {"page": "intro"}})
    assert event_types_for_condition(condition, EXTERNAL) == frozenset()


def test_the_module_creates_no_timer_or_polling_loop() -> None:
    """FR-051: every re-evaluation comes from an event, a request, or step entry."""
    source = (Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "conditions.py").read_text(
        encoding="utf-8"
    )
    for banned in ("time.sleep", "threading.Timer", "asyncio.sleep", "call_later", "while True"):
        assert banned not in source


def test_condition_args_are_read_only() -> None:
    condition: Condition = parse_condition({"file_exists": {"path": "x"}})
    with pytest.raises(TypeError):
        condition.args["path"] = "y"  # type: ignore[index]
