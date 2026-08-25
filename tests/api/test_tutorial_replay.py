"""Scripted replay, delivered through the product's real terminal path.

``docs/specs/adr-053-learning-center.md`` FR-061 … FR-061c, checklist §6.1.7.

``tests/tutorials/test_replay.py`` owns the sequence: it drives
``execute_replay`` against a recording double and pins that a segment's actions
run before its bytes and that a delivery bound to another surface is refused.
None of that needs an API. What needs one is the half FR-061a actually
specifies — that a replay is delivered *as a scripted session through the
existing PTY path*, "so the tab strip, the terminal component, and the tab
lifecycle stay the product's real ones and only the byte source changes".

So these tests are about the injection point. They assert that the byte source
is registered where ``pty_endpoint`` looks for a pre-spawned tab, that the real
WebSocket route joins it and streams the scripted bytes without knowing it is
not an agent, that typing into it goes nowhere, and that ending the session
leaves nothing behind — on the same path a real PTY uses.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from scistudio.api.routes.ai_pty import _state
from scistudio.api.routes.ai_pty.replay import (
    PtyReplayHandle,
    ScriptedReplaySession,
    UnknownReplaySurfaceError,
    open_replay_tab,
)
from scistudio.api.runtime import ApiRuntime
from scistudio.tutorials import discovery
from scistudio.tutorials.actions import (
    AI_CHAT_TERMINAL_SURFACE,
    ActionContext,
    ActionExecutionError,
    ReplayAction,
    ReplaySegment,
    WriteAction,
    execute_replay,
)
from scistudio.tutorials.manifest import TUTORIAL_MANIFEST_FILENAME

SEGMENT_ONE = b"> write the block for me\r\nWritten blocks/written_by_segment.py.\r\n"
SEGMENT_TWO = b"> confirm\r\nIt is there.\r\n"


@pytest.fixture(autouse=True)
def _clean_pty_registry() -> Iterator[None]:
    """Leave the shared PTY registry as it was found.

    ``_active_ptys`` is module state, so a replay tab a test forgets would
    change the next test's cap arithmetic and its "nothing left behind"
    assertions.
    """
    _state._active_ptys.clear()
    yield
    _state._active_ptys.clear()


# ---------------------------------------------------------------------------
# The closed surface set (FR-061a)
# ---------------------------------------------------------------------------


def test_a_surface_outside_the_closed_set_gets_no_byte_source() -> None:
    """FR-061: a replay must not reach any surface but the one it names.

    The manifest parser already rejects an unknown surface while the tutorial is
    being listed. This is the second guard, on the one function that turns a
    surface name into a live tab, because that is where the failure would
    actually cost something.
    """
    with pytest.raises(UnknownReplaySurfaceError) as raised:
        open_replay_tab("terminal")

    assert AI_CHAT_TERMINAL_SURFACE in str(raised.value)
    assert not _state._active_ptys


def test_opening_a_replay_registers_a_tab_the_websocket_route_will_join() -> None:
    """The injection point: a pre-spawned tab, marked as ``pty_endpoint`` expects.

    The marker is the whole mechanism. Without it the route would spawn a real
    agent over the top of the replay when the frontend connected.
    """
    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)

    assert handle.surface == AI_CHAT_TERMINAL_SURFACE
    registered = _state._active_ptys[handle.tab_id]
    assert registered is handle.session
    assert getattr(registered, "_engine_prespawned", False) is True
    assert getattr(registered, "_engine_prespawned_at", None) is not None


def test_only_the_named_surface_gets_a_tab() -> None:
    """One replay opens one tab, and it is the one the action named."""
    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)

    assert list(_state._active_ptys) == [handle.tab_id]
    assert handle.surface == AI_CHAT_TERMINAL_SURFACE


def test_a_delivery_cannot_be_pointed_at_another_surface(tmp_path: Path) -> None:
    """A handle bound to one surface refuses an action naming another."""
    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)
    action = ReplayAction(surface="somewhere_else", segments=(ReplaySegment(id="one", source="assets/replay/a.txt"),))

    with pytest.raises(ActionExecutionError):
        execute_replay(
            action,
            context=ActionContext(tutorial_dir=tmp_path, project_dir=tmp_path),
            step_id="step",
            delivery=handle,
        )


# ---------------------------------------------------------------------------
# The byte source itself
# ---------------------------------------------------------------------------


def test_typing_into_a_replay_goes_nowhere() -> None:
    """FR-061a: a replay must not accept user input back into the session.

    ``write`` is exactly where the route's WS→PTY pump delivers keystrokes, so
    dropping them here is what makes the transcript unalterable. The session
    stays alive, because a tab that died on a keypress would be worse than one
    that ignores it.
    """
    session = ScriptedReplaySession()
    session.feed(SEGMENT_ONE)

    session.write(b"rm -rf /\r")

    assert session.read(0.01) == SEGMENT_ONE
    assert session.read(0.01) == b""
    assert session.is_alive() is True


def test_a_replay_stays_open_after_its_last_segment() -> None:
    """The transcript is still there to be read when the bytes run out.

    The tutorial session decides when a replay is over. Ending at the last byte
    would tear the tab down at the moment the user starts reading it.
    """
    session = ScriptedReplaySession()
    session.feed(SEGMENT_ONE)
    session.read(0.01)

    assert session.is_alive() is True


def test_a_segments_files_land_before_that_segments_bytes_can_be_read(tmp_path: Path) -> None:
    """FR-061b, through the real byte source.

    A scripted agent that claims to have written a block has to be matched by
    the block existing at the moment the claim becomes readable. This watches
    both sides at once: what was on disk when each segment was delivered, and
    what became readable immediately afterwards.
    """
    tutorial = tmp_path / "tutorial"
    (tutorial / "assets" / "replay").mkdir(parents=True)
    (tutorial / "assets" / "code").mkdir(parents=True)
    (tutorial / "assets" / "replay" / "one.txt").write_bytes(SEGMENT_ONE)
    (tutorial / "assets" / "replay" / "two.txt").write_bytes(SEGMENT_TWO)
    (tutorial / "assets" / "code" / "block.py").write_text("# a block\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    written = project / "blocks" / "written_by_segment.py"

    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)
    observed: list[tuple[str, bool, bytes]] = []

    class _Watching:
        """The real handle, with a note taken as each segment is delivered."""

        surface = handle.surface
        tab_id = handle.tab_id

        def deliver(self, segment: ReplaySegment, payload: bytes) -> None:
            existed = written.is_file()
            handle.deliver(segment, payload)
            observed.append((segment.id, existed, handle.session.read(0.05)))

        def close(self) -> None:
            handle.close()

    execute_replay(
        ReplayAction(
            surface=AI_CHAT_TERMINAL_SURFACE,
            segments=(
                ReplaySegment(
                    id="claims-to-write",
                    source="assets/replay/one.txt",
                    do=(WriteAction(source="assets/code/block.py", destination="blocks/written_by_segment.py"),),
                ),
                ReplaySegment(id="confirms-it-wrote", source="assets/replay/two.txt"),
            ),
        ),
        context=ActionContext(tutorial_dir=tutorial, project_dir=project),
        step_id="replay-step",
        delivery=_Watching(),  # type: ignore[arg-type]
    )

    assert observed == [
        ("claims-to-write", True, SEGMENT_ONE),
        ("confirms-it-wrote", True, SEGMENT_TWO),
    ]


def test_closing_a_replay_leaves_no_session_object_behind() -> None:
    """FR-061c: terminate, and drop the registry entry the real teardown drops."""
    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)
    handle.deliver(ReplaySegment(id="one", source="assets/replay/one.txt"), SEGMENT_ONE)

    handle.close()

    assert handle.tab_id not in _state._active_ptys
    assert not _state._active_ptys
    assert handle.session.is_alive() is False


def test_closing_a_replay_twice_is_harmless() -> None:
    """The WebSocket teardown and the session can both close the same replay."""
    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)

    handle.close()
    handle.close()

    assert not _state._active_ptys


# ---------------------------------------------------------------------------
# Through the routes
# ---------------------------------------------------------------------------


REPLAY_TUTORIAL_ID = "replays-a-session"


@pytest.fixture
def replay_tutorial(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Mount a core-tier tutorial whose first step replays a scripted session.

    Core tier, not user or project: FR-020a rejects a replay declared by either
    of those, because they are the two tiers a user can write without review.
    """
    core = tmp_path / "core-tutorials"
    directory = core / REPLAY_TUTORIAL_ID
    (directory / "assets" / "replay").mkdir(parents=True)
    (directory / "assets" / "code").mkdir(parents=True)
    (directory / "assets" / "replay" / "one.txt").write_bytes(SEGMENT_ONE)
    (directory / "assets" / "replay" / "two.txt").write_bytes(SEGMENT_TWO)
    (directory / "assets" / "code" / "block.py").write_text("# a block\n", encoding="utf-8")
    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "id": REPLAY_TUTORIAL_ID,
        "title": "Replays A Session",
        "summary": "A tutorial that plays a scripted agent session.",
        "bootstrap": {"project_name": "Replay Fixture"},
        "steps": [
            {
                "id": "watch-it",
                "say": "Watch.",
                "route_to": "ai_chat",
                "do": [
                    {
                        "replay": {
                            "surface": AI_CHAT_TERMINAL_SURFACE,
                            "segments": [
                                {
                                    "id": "claims-to-write",
                                    "source": "assets/replay/one.txt",
                                    "do": [
                                        {
                                            "write": {
                                                "source": "assets/code/block.py",
                                                "destination": "blocks/written_by_segment.py",
                                            }
                                        }
                                    ],
                                },
                                {"id": "confirms-it-wrote", "source": "assets/replay/two.txt"},
                            ],
                        }
                    }
                ],
            },
            {"id": "afterwards", "say": "Done."},
        ],
    }
    (directory / TUTORIAL_MANIFEST_FILENAME).write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: core)
    return directory


def _start_replay(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/tutorials/sessions",
        json={"source_kind": "core", "source_id": "", "tutorial_id": REPLAY_TUTORIAL_ID, "restart": False},
    )
    assert response.status_code == 200, response.text
    payload: dict[str, Any] = response.json()
    return payload


def test_a_step_that_replays_reports_the_tab_to_attach_to(client: TestClient, replay_tutorial: Path) -> None:
    """The session response names the surface and the tab (checklist §6.1.6).

    ``replay.tab_id`` is the only thing that connects the backend's scripted
    session to the tab the frontend opens, so a session that plays a replay and
    does not report one is a transcript nobody can see.
    """
    payload = _start_replay(client)

    assert payload["replay"]["surface"] == AI_CHAT_TERMINAL_SURFACE
    tab_id = payload["replay"]["tab_id"]
    assert tab_id in _state._active_ptys
    assert getattr(_state._active_ptys[tab_id], "_engine_prespawned", False) is True
    assert (Path(payload["project_path"]) / "blocks" / "written_by_segment.py").is_file()


def test_ending_a_session_mid_replay_leaves_no_session_object(client: TestClient, replay_tutorial: Path) -> None:
    """FR-061c through the route the user actually takes.

    Leaving preserves the tutorial's position, but a live terminal session
    cannot be preserved, so it is terminated on the way out.
    """
    payload = _start_replay(client)
    tab_id = payload["replay"]["tab_id"]

    assert client.post("/api/tutorials/sessions/active/leave").status_code == 204

    assert tab_id not in _state._active_ptys
    assert not _state._active_ptys


def test_clearing_tutorial_data_ends_a_running_replay(client: TestClient, replay_tutorial: Path) -> None:
    _start_replay(client)

    assert client.post("/api/tutorials/data/clear", json={"confirm": True}).status_code == 200

    assert not _state._active_ptys


@pytest.mark.serial
def test_the_real_terminal_route_joins_the_replay_and_streams_it(
    client: TestClient, runtime: ApiRuntime, replay_tutorial: Path
) -> None:
    """The frontend's own WebSocket joins the scripted session and reads it.

    This is the requirement FR-061a states as a mechanism rather than as a
    behaviour: the terminal, the tab lifecycle and the wire protocol are the
    product's real ones, and only the byte source changed. Nothing in the route
    is replay-aware — it takes the join branch it already had for a pre-spawned
    tab — so if the scripted source did not present the same small interface a
    ``PtyProcess`` does, this connection would fail rather than stream.
    """
    payload = _start_replay(client)
    tab_id = payload["replay"]["tab_id"]
    project_dir = payload["project_path"]

    received = b""
    with client.websocket_connect(
        f"/api/ai/pty/{tab_id}?provider=claude-code&project_dir={project_dir}&cols=100&rows=40"
    ) as socket:
        # Typing must not reach a scripted session, and must not break it.
        socket.send_json({"type": "stdin", "data": "rm -rf /\r"})
        while SEGMENT_TWO.decode() not in received.decode("utf-8", "replace"):
            frame = socket.receive_json()
            assert frame["type"] == "stdout", frame
            received += frame["data"].encode("utf-8")

    transcript = received.decode("utf-8")
    assert SEGMENT_ONE.decode() in transcript
    assert SEGMENT_TWO.decode() in transcript
    assert "rm -rf /" not in transcript
    # The route's own teardown reclaims the tab, exactly as it does for a PTY.
    assert tab_id not in _state._active_ptys


def test_a_replay_handle_satisfies_the_runtimes_port() -> None:
    """``PtyReplayHandle`` is what the tutorial runtime is allowed to hold."""
    from scistudio.tutorials.session import ReplayHandle

    handle = open_replay_tab(AI_CHAT_TERMINAL_SURFACE)

    assert isinstance(handle, ReplayHandle)
    assert isinstance(handle, PtyReplayHandle)


# ---------------------------------------------------------------------------
# is_open — what a continue_tab replay checks before appending (#2089)
# ---------------------------------------------------------------------------


def test_a_live_registered_tab_is_open_and_a_closed_one_is_not() -> None:
    from scistudio.api.routes.ai_pty import _state as _pkg
    from scistudio.api.routes.ai_pty.replay import open_replay_tab

    handle = open_replay_tab("ai_chat_terminal")
    try:
        assert handle.is_open is True
        handle.close()
        assert handle.is_open is False
        assert handle.tab_id not in _pkg._active_ptys
    finally:
        handle.close()


def test_a_tab_torn_down_by_the_websocket_route_reads_as_closed() -> None:
    """The WS teardown pops the registry and kills; either half must read closed."""
    from scistudio.api.routes.ai_pty import _state as _pkg
    from scistudio.api.routes.ai_pty.replay import open_replay_tab

    handle = open_replay_tab("ai_chat_terminal")
    try:
        # The route's teardown order: pop first, then kill.
        _pkg._active_ptys.pop(handle.tab_id, None)
        assert handle.is_open is False
    finally:
        handle.close()
