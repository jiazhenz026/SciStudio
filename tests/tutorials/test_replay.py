"""Replay — ADR-053 spec §4.4 "Replay" row, FR-061 … FR-061c.

Asserts: a replay naming a surface outside the declared set is rejected at
validation (FR-061a); a segment's bound actions complete before that segment's
bytes are delivered, and therefore before the next segment's (FR-061b); and the
delivery interface a replay drives reaches only the surface the action names
(FR-061) and never carries user input back into the scripted session.

Byte delivery itself is not implemented here — the PTY injection that feeds the
AI Chat terminal is a separate slice (checklist §6.1.7). What this module owns,
and what these tests cover, is the sequence and the interface that slice
drives.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scistudio.tutorials.actions import (
    AI_CHAT_TERMINAL_SURFACE,
    REPLAY_SURFACES,
    ActionContext,
    ActionExecutionError,
    ActionValidationError,
    ReplayAction,
    ReplaySegment,
    WriteAction,
    execute_action,
    execute_replay,
    parse_action,
)
from scistudio.tutorials.manifest import ManifestValidationError, TutorialSourceKind, load_manifest

from .conftest import MINIMAL_MANIFEST, write_tutorial


@dataclass
class RecordingDelivery:
    """A stand-in for the PTY-backed delivery the API layer supplies.

    It records what it was handed and when, which is how the ordering FR-061b
    requires becomes observable without a terminal.
    """

    surface: str = AI_CHAT_TERMINAL_SURFACE
    project_dir: Path | None = None
    log: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    closed: bool = False

    def deliver(self, segment: ReplaySegment, payload: bytes) -> None:
        landed: tuple[str, ...] = ()
        if self.project_dir is not None:
            landed = tuple(
                # as_posix(): the ordering assertions name these paths with "/",
                # and str() would use the OS separator on Windows (#2075).
                sorted(p.relative_to(self.project_dir).as_posix() for p in self.project_dir.rglob("*") if p.is_file())
            )
        self.log.append((segment.id, payload.decode("utf-8"), landed))

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def replay_context(tmp_path: Path) -> ActionContext:
    tutorial = tmp_path / "tutorial"
    (tutorial / "assets" / "replay").mkdir(parents=True)
    # Bytes, not text mode: the tests compare the delivered payloads
    # against these POSIX literals, and text mode would write CRLF on
    # Windows (#2075).
    (tutorial / "assets" / "replay" / "one.txt").write_bytes(b"I will write the block.\n")
    (tutorial / "assets" / "replay" / "two.txt").write_bytes(b"I have written the block.\n")
    (tutorial / "assets" / "code").mkdir(parents=True)
    (tutorial / "assets" / "code" / "cluster.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    return ActionContext(tutorial_dir=tutorial, project_dir=project)


# ---------------------------------------------------------------------------
# The closed surface set (FR-061a)
# ---------------------------------------------------------------------------


def test_the_surface_set_has_exactly_one_member() -> None:
    assert set(REPLAY_SURFACES) == {"ai_chat_terminal"}
    assert AI_CHAT_TERMINAL_SURFACE == "ai_chat_terminal"


def test_a_surface_outside_the_set_is_rejected_at_validation() -> None:
    with pytest.raises(ActionValidationError) as excinfo:
        parse_action(
            {"replay": {"surface": "canvas", "segments": [{"id": "one", "source": "assets/replay/one.txt"}]}},
            field_name="do[0]",
        )
    message = str(excinfo.value)
    assert "canvas" in message
    assert "ai_chat_terminal" in message


def test_a_manifest_naming_an_unknown_surface_is_rejected_while_being_listed(tmp_path: Path) -> None:
    data = copy.deepcopy(MINIMAL_MANIFEST)
    data["steps"][0]["do"] = [
        {"replay": {"surface": "git_tab", "segments": [{"id": "one", "source": "assets/replay/one.txt"}]}}
    ]
    directory = write_tutorial(tmp_path / "bad-surface", data, files={"assets/replay/one.txt": "hi\n"})
    with pytest.raises(ManifestValidationError) as excinfo:
        load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert "git_tab" in str(excinfo.value)


def test_a_replay_with_no_segments_is_rejected() -> None:
    with pytest.raises(ActionValidationError):
        parse_action({"replay": {"surface": AI_CHAT_TERMINAL_SURFACE, "segments": []}}, field_name="do[0]")


def test_duplicate_segment_ids_are_rejected() -> None:
    with pytest.raises(ActionValidationError) as excinfo:
        parse_action(
            {
                "replay": {
                    "surface": AI_CHAT_TERMINAL_SURFACE,
                    "segments": [
                        {"id": "one", "source": "assets/replay/one.txt"},
                        {"id": "one", "source": "assets/replay/two.txt"},
                    ],
                }
            },
            field_name="do[0]",
        )
    assert "duplicate segment id" in str(excinfo.value)


def test_a_segment_source_escaping_the_tutorial_is_rejected() -> None:
    with pytest.raises(ActionValidationError):
        parse_action(
            {
                "replay": {
                    "surface": AI_CHAT_TERMINAL_SURFACE,
                    "segments": [{"id": "one", "source": "../elsewhere.txt"}],
                }
            },
            field_name="do[0]",
        )


def test_a_replay_parses_into_an_ordered_segment_sequence() -> None:
    action = parse_action(
        {
            "replay": {
                "surface": AI_CHAT_TERMINAL_SURFACE,
                "segments": [
                    {
                        "id": "claim",
                        "source": "assets/replay/one.txt",
                        "do": [{"write": {"source": "assets/code/cluster.py", "destination": "blocks/cluster.py"}}],
                    },
                    {"id": "confirm", "source": "assets/replay/two.txt"},
                ],
            }
        },
        field_name="do[0]",
    )
    assert isinstance(action, ReplayAction)
    assert [segment.id for segment in action.segments] == ["claim", "confirm"]
    assert action.segments[0].do[0].destination == "blocks/cluster.py"
    assert action.segments[1].do == ()


# ---------------------------------------------------------------------------
# Segment ordering (FR-061b)
# ---------------------------------------------------------------------------


def test_a_segments_actions_land_before_its_own_bytes_and_before_the_next_segments(
    replay_context: ActionContext,
) -> None:
    """FR-061b: the claim must be matched by the block existing when it is readable."""
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(
            ReplaySegment(
                id="writes-the-block",
                source="assets/replay/one.txt",
                do=(WriteAction(source="assets/code/cluster.py", destination="blocks/cluster.py"),),
            ),
            ReplaySegment(
                id="writes-the-plot",
                source="assets/replay/two.txt",
                do=(WriteAction(source="assets/code/cluster.py", destination="plots/scatter.py"),),
            ),
        ),
    )
    delivery = RecordingDelivery(project_dir=replay_context.project_dir)
    execute_replay(action, context=replay_context, step_id="fake-agent", delivery=delivery)

    first, second = delivery.log
    assert first[0] == "writes-the-block"
    assert "blocks/cluster.py" in first[2], "the block was not on disk when its claim became readable"
    assert "plots/scatter.py" not in first[2], "a later segment's file landed too early"
    assert second[0] == "writes-the-plot"
    assert "plots/scatter.py" in second[2]


def test_the_bytes_delivered_are_the_segment_assets(replay_context: ActionContext) -> None:
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(
            ReplaySegment(id="one", source="assets/replay/one.txt"),
            ReplaySegment(id="two", source="assets/replay/two.txt"),
        ),
    )
    delivery = RecordingDelivery()
    execute_replay(action, context=replay_context, step_id="s1", delivery=delivery)
    assert [entry[1] for entry in delivery.log] == ["I will write the block.\n", "I have written the block.\n"]


def test_a_failing_segment_action_stops_the_replay_before_its_bytes(replay_context: ActionContext) -> None:
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(
            ReplaySegment(
                id="one",
                source="assets/replay/one.txt",
                do=(WriteAction(source="assets/code/absent.py", destination="blocks/absent.py"),),
            ),
        ),
    )
    delivery = RecordingDelivery()
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_replay(action, context=replay_context, step_id="fake-agent", delivery=delivery)
    assert excinfo.value.step_id == "fake-agent"
    assert delivery.log == []


def test_a_missing_segment_asset_names_the_segment(replay_context: ActionContext) -> None:
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(ReplaySegment(id="ghost", source="assets/replay/absent.txt"),),
    )
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_replay(action, context=replay_context, step_id="s1", delivery=RecordingDelivery())
    assert "ghost" in str(excinfo.value)


# ---------------------------------------------------------------------------
# A replay reaches only the surface it names (FR-061)
# ---------------------------------------------------------------------------


def test_a_delivery_bound_to_another_surface_is_refused(replay_context: ActionContext) -> None:
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(ReplaySegment(id="one", source="assets/replay/one.txt"),),
    )
    delivery = RecordingDelivery(surface="some_other_surface")
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_replay(action, context=replay_context, step_id="s1", delivery=delivery)
    assert "some_other_surface" in str(excinfo.value)
    assert delivery.log == []


def test_a_replay_without_a_delivery_fails_rather_than_being_skipped(replay_context: ActionContext) -> None:
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(ReplaySegment(id="one", source="assets/replay/one.txt"),),
    )
    with pytest.raises(ActionExecutionError) as excinfo:
        execute_action(action, context=replay_context, step_id="s1", delivery=None)
    assert "delivery" in str(excinfo.value)


def test_the_delivery_interface_carries_no_path_for_user_input() -> None:
    """FR-061a: a replay never accepts user input back into the scripted session."""
    from scistudio.tutorials.actions import ReplayDelivery

    members = {name for name in dir(ReplayDelivery) if not name.startswith("_")}
    assert members == {"surface", "deliver", "close"}


def test_ending_a_replay_can_close_the_scripted_session(replay_context: ActionContext) -> None:
    """FR-061c: the session layer terminates the scripted session through ``close``."""
    delivery = RecordingDelivery()
    action = ReplayAction(
        surface=AI_CHAT_TERMINAL_SURFACE,
        segments=(ReplaySegment(id="one", source="assets/replay/one.txt"),),
    )
    execute_replay(action, context=replay_context, step_id="s1", delivery=delivery)
    assert delivery.closed is False
    delivery.close()
    assert delivery.closed is True


# ---------------------------------------------------------------------------
# continue_tab (#2089, FR-061)
# ---------------------------------------------------------------------------


def test_continue_tab_parses_and_defaults_to_false() -> None:
    from scistudio.tutorials.actions import ReplayAction, parse_action

    plain = parse_action(
        {"replay": {"surface": "ai_chat_terminal", "segments": [{"id": "s1", "source": "assets/replay/s1.txt"}]}},
        field_name="steps[0].do[0]",
    )
    assert isinstance(plain, ReplayAction)
    assert plain.continue_tab is False

    appended = parse_action(
        {
            "replay": {
                "surface": "ai_chat_terminal",
                "continue_tab": True,
                "segments": [{"id": "s2", "source": "assets/replay/s2.txt"}],
            }
        },
        field_name="steps[0].do[0]",
    )
    assert isinstance(appended, ReplayAction)
    assert appended.continue_tab is True


def test_continue_tab_must_be_a_boolean() -> None:
    from scistudio.tutorials.actions import ActionValidationError, parse_action

    with pytest.raises(ActionValidationError, match="continue_tab"):
        parse_action(
            {
                "replay": {
                    "surface": "ai_chat_terminal",
                    "continue_tab": "yes",
                    "segments": [{"id": "s1", "source": "assets/replay/s1.txt"}],
                }
            },
            field_name="steps[0].do[0]",
        )
