"""Step actions — ADR-053 spec §4.4 "Actions" row.

Asserts: write and copy land before the step text is exposed (FR-059); a path
escaping the project is rejected; a failed action ends the step with an error
naming the step and the action (FR-060). Plus FR-058 (write at any step) and
the overwrite decision the Edge Cases list records.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.tutorials.actions import (
    ActionContext,
    ActionExecutionError,
    ActionValidationError,
    CopyAction,
    WriteAction,
    describe_action,
    destination_head,
    execute_actions,
    parse_action,
    parse_actions,
    parse_file_actions,
    perform_step_entry,
    resolve_contained_path,
    validate_relative_path,
)


@pytest.fixture
def context(tmp_path: Path) -> ActionContext:
    tutorial = tmp_path / "tutorial"
    (tutorial / "assets" / "code").mkdir(parents=True)
    (tutorial / "assets" / "code" / "cluster.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (tutorial / "assets" / "data").mkdir(parents=True)
    (tutorial / "assets" / "data" / "cells.csv").write_text("well,mean\n", encoding="utf-8")
    (tutorial / "assets" / "data" / "nested").mkdir()
    (tutorial / "assets" / "data" / "nested" / "more.csv").write_text("a,b\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    return ActionContext(tutorial_dir=tutorial, project_dir=project)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_write_and_copy_parse() -> None:
    write = parse_action(
        {"write": {"source": "assets/code/cluster.py", "destination": "blocks/cluster.py"}}, field_name="do[0]"
    )
    assert isinstance(write, WriteAction)
    assert write.kind == "write"
    copy = parse_action({"copy": {"source": "assets/data", "destination": "data/raw"}}, field_name="do[0]")
    assert isinstance(copy, CopyAction)
    assert copy.kind == "copy"


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"write": {}, "copy": {}},
        {"teleport": {"source": "a", "destination": "b"}},
        {"write": {"source": "a"}},
        {"write": {"source": "a", "destination": "b", "mode": "append"}},
        "write",
    ],
)
def test_a_malformed_action_is_rejected(raw: object) -> None:
    with pytest.raises(ActionValidationError):
        parse_action(raw, field_name="do[0]")


def test_parse_actions_preserves_declaration_order() -> None:
    parsed = parse_actions(
        [
            {"write": {"source": "a", "destination": "one.txt"}},
            {"write": {"source": "b", "destination": "two.txt"}},
        ],
        field_name="do",
    )
    assert [action.destination for action in parsed] == ["one.txt", "two.txt"]
    assert parse_actions(None, field_name="do") == ()


def test_a_replay_segment_may_only_bind_file_actions() -> None:
    with pytest.raises(ActionValidationError):
        parse_file_actions([{"replay": {"surface": "ai_chat_terminal", "segments": []}}], field_name="do")


def test_describe_action_names_the_paths() -> None:
    action = WriteAction(source="assets/x.py", destination="blocks/x.py")
    assert "assets/x.py" in describe_action(action)
    assert "blocks/x.py" in describe_action(action)


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "..", "../x", "a/../../x", "/abs/x", "C:/x", "a\\b"])
def test_a_path_that_could_escape_is_rejected(bad: str) -> None:
    with pytest.raises(ActionValidationError):
        validate_relative_path(bad, field_name="destination")


def test_a_good_path_is_accepted() -> None:
    assert str(validate_relative_path("data/raw/cells.csv", field_name="source")) == "data/raw/cells.csv"


def test_resolve_contained_path_returns_a_path_under_the_base(tmp_path: Path) -> None:
    resolved = resolve_contained_path(tmp_path, "a/b.txt", field_name="destination")
    assert resolved == tmp_path / "a" / "b.txt"


def test_destination_head_names_the_first_segment() -> None:
    assert destination_head("blocks/cluster.py") == "blocks"
    assert destination_head("notes.md") == "notes.md"
    assert destination_head("") == ""


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_write_lands_the_file(context: ActionContext) -> None:
    action = WriteAction(source="assets/code/cluster.py", destination="blocks/cluster.py")
    execute_actions([action], context=context, step_id="s1")
    assert context.project_dir is not None
    assert (context.project_dir / "blocks" / "cluster.py").read_text(encoding="utf-8").startswith("def run()")


def test_copy_lands_the_directory(context: ActionContext) -> None:
    action = CopyAction(source="assets/data", destination="data/raw")
    execute_actions([action], context=context, step_id="s1")
    assert context.project_dir is not None
    assert (context.project_dir / "data" / "raw" / "cells.csv").is_file()
    assert (context.project_dir / "data" / "raw" / "nested" / "more.csv").is_file()


def test_a_write_overwrites_a_file_the_user_edited(context: ActionContext) -> None:
    """Edge Cases: tutorial projects are disposable and the tutorial controls their contents."""
    assert context.project_dir is not None
    target = context.project_dir / "blocks" / "cluster.py"
    target.parent.mkdir(parents=True)
    target.write_text("# the user typed this\n", encoding="utf-8")
    execute_actions(
        [WriteAction(source="assets/code/cluster.py", destination="blocks/cluster.py")],
        context=context,
        step_id="s1",
    )
    assert "the user typed this" not in target.read_text(encoding="utf-8")


def test_a_write_is_available_at_any_step_not_only_bootstrap(context: ActionContext) -> None:
    """FR-058: two designed scenarios depend on mid-tutorial writes."""
    for index, step in enumerate(["bootstrap", "step-3", "step-7"]):
        execute_actions(
            [WriteAction(source="assets/data/cells.csv", destination=f"data/raw/round-{index}.csv")],
            context=context,
            step_id=step,
        )
    assert context.project_dir is not None
    assert sorted(p.name for p in (context.project_dir / "data" / "raw").iterdir()) == [
        "round-0.csv",
        "round-1.csv",
        "round-2.csv",
    ]


def test_a_destination_escaping_the_project_is_rejected_at_execution_too(context: ActionContext) -> None:
    action = WriteAction(source="assets/data/cells.csv", destination="../escaped.csv")
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_actions([action], context=context, step_id="s1")
    assert "escaped.csv" in str(excinfo.value)
    assert context.project_dir is not None
    assert not (context.project_dir.parent / "escaped.csv").exists()


def test_a_failed_action_names_the_step_and_the_action(context: ActionContext) -> None:
    """FR-060: the session ends with an error naming both, and never advances silently."""
    action = WriteAction(source="assets/code/absent.py", destination="blocks/absent.py")
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_actions([action], context=context, step_id="write-the-block")
    assert excinfo.value.step_id == "write-the-block"
    assert excinfo.value.action is action
    assert "write-the-block" in str(excinfo.value)
    assert "assets/code/absent.py" in str(excinfo.value)


def test_a_copy_of_something_that_is_not_a_directory_fails(context: ActionContext) -> None:
    with pytest.raises(ActionExecutionError):
        execute_actions(
            [CopyAction(source="assets/data/cells.csv", destination="data/raw")],
            context=context,
            step_id="s1",
        )


def test_a_write_without_a_project_fails_rather_than_guessing(tmp_path: Path) -> None:
    context = ActionContext(tutorial_dir=tmp_path, project_dir=None)
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_actions([WriteAction(source="a", destination="b")], context=context, step_id="s1")
    assert "bootstrap" in str(excinfo.value)


# ---------------------------------------------------------------------------
# FR-059: the ordering is a property of the API
# ---------------------------------------------------------------------------


def test_the_step_text_is_only_reachable_after_the_actions_have_landed(context: ActionContext) -> None:
    """FR-059: 'we have written this block for you' must not be readable first."""
    assert context.project_dir is not None
    written = context.project_dir / "blocks" / "cluster.py"

    def reveal() -> str:
        assert written.is_file(), "the step text was produced before the block existed"
        return "We have written this block for you."

    said = perform_step_entry(
        [WriteAction(source="assets/code/cluster.py", destination="blocks/cluster.py")],
        context=context,
        step_id="s1",
        reveal=reveal,
    )
    assert said == "We have written this block for you."


def test_a_failed_action_means_the_step_text_is_never_produced(context: ActionContext) -> None:
    revealed: list[str] = []

    def reveal() -> str:
        revealed.append("shown")
        return "shown"

    with pytest.raises(ActionExecutionError):
        perform_step_entry(
            [WriteAction(source="assets/code/absent.py", destination="blocks/absent.py")],
            context=context,
            step_id="s1",
            reveal=reveal,
        )
    assert revealed == []


def test_actions_run_in_declaration_order(context: ActionContext) -> None:
    assert context.project_dir is not None
    execute_actions(
        [
            WriteAction(source="assets/data/cells.csv", destination="notes.csv"),
            WriteAction(source="assets/code/cluster.py", destination="notes.csv"),
        ],
        context=context,
        step_id="s1",
    )
    assert (context.project_dir / "notes.csv").read_text(encoding="utf-8").startswith("def run()")
