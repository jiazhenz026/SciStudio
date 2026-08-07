"""ADR-053 FR-022 to FR-030 — ``POST /api/work-import/sessions``.

The endpoint's whole job is to hand a running agent a complete set of
instructions it can find. Everything pinned here follows from that:

* the brief is on disk, complete, before the agent that reads it exists
  (FR-024) — a session pointed at a missing or half-written file has no
  second source of instructions and cannot recover;
* two sessions never share a brief (FR-030);
* the brief lives where the user's version history will not pick it up
  (FR-027);
* the user sees one sentence, not the instruction set (FR-028);
* and delivery does not vary with the provider (FR-029), because four of
  the five registry agents have no per-session prompt channel at all.

The PTY spawn is faked with a tiny echo subprocess through the existing
``ai_pty._state._spawn`` seam, so no real agent CLI is launched. The fake
also *reads the brief at spawn time*: that is what makes the ordering
requirement a test result rather than a code-reading exercise.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.providers_registry import (
    SystemPromptStrategy,
    agent_descriptors,
)
from scistudio.ai.agent.terminal import PtyProcess
from scistudio.ai.work_import.brief import compose_brief
from scistudio.ai.work_import.context import ImportSessionContext
from scistudio.api.routes import ai_pty, work_import
from scistudio.api.routes.ai_pty import (
    _active_ptys,
    _engine_run_to_run_dir,
    _engine_tab_to_run,
    get_block_run_id_for_tab,
)
from scistudio.core.versioning.git_binary import GitBinary
from scistudio.core.versioning.gitignore_template import DEFAULT_GITIGNORE

# Real PtyProcess (echo child): isolate from xdist so a hang or leak cannot
# crash a parallel worker (#1896) — same policy as the other PTY suites.
pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


def _echo_argv() -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import sys\n"
            "sys.stdout.write('READY\\n')\n"
            "sys.stdout.flush()\n"
            "for line in iter(sys.stdin.readline, ''):\n"
            "    if not line:\n"
            "        break\n"
            "    sys.stdout.write(line)\n"
            "    sys.stdout.flush()\n"
        ),
    ]


def _brief_reference(prompt: str) -> str | None:
    """Return the ``.md`` path named in the opening message, if any.

    Deliberately reads the path out of the message rather than guessing
    it from the project layout: the point of FR-028 is that the message
    itself is what tells the agent where to look.
    """
    for token in prompt.split():
        if token.endswith(".md"):
            return token
    return None


class _SpawnRecorder:
    """``_spawn`` stand-in that snapshots the brief as the agent starts.

    Reading the file *inside* the spawn call is the ordering proof: if the
    endpoint spawned before writing (or before closing) the brief, the
    snapshot taken here would be missing or short, and no amount of
    after-the-fact inspection of the finished directory would show it.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        cols: int = 120,
        rows: int = 30,
        extra_env: dict[str, str] | None = None,
        prompt: str = "",
    ) -> PtyProcess:
        brief_rel = _brief_reference(prompt)
        brief_abs = project_dir / brief_rel if brief_rel else None
        exists = bool(brief_abs is not None and brief_abs.is_file())
        self.calls.append(
            {
                "provider": provider,
                "project_dir": project_dir,
                "dangerous": dangerous,
                "cols": cols,
                "rows": rows,
                "extra_env": extra_env,
                "prompt": prompt,
                "brief_rel": brief_rel,
                "brief_exists_at_spawn": exists,
                "brief_text_at_spawn": (brief_abs.read_text(encoding="utf-8") if exists and brief_abs else None),
            }
        )
        return PtyProcess(_echo_argv(), cwd=project_dir, cols=cols, rows=rows, extra_env=extra_env)


@pytest.fixture()
def spawn(monkeypatch: pytest.MonkeyPatch) -> Iterator[_SpawnRecorder]:
    """Install the recording spawn and reset the shared PTY registries."""
    recorder = _SpawnRecorder()
    monkeypatch.setattr(ai_pty._state, "_spawn", recorder)
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    _engine_run_to_run_dir.clear()
    yield recorder
    for pty in list(_active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    _engine_run_to_run_dir.clear()


def _payload(project_root: Path, **overrides: Any) -> dict[str, Any]:
    """A complete, valid request body — the shape contract C3 fixes."""
    body: dict[str, Any] = {
        "project_dir": str(project_root),
        "source_location": str(project_root / "legacy-scripts"),
        "has_no_codebase": False,
        "destination_tier": "project",
        "data_kinds": ["spectra", "images"],
        "data_kinds_other": "chromatograms from an old HPLC",
        "workflow_description": "I run a MATLAB script over every folder, then paste the numbers into Excel.",
        "interaction_wishes": "I want to change the baseline window and see the fit update.",
        "other_software": None,
        "skipped": ["other_software"],
        "provider": "claude-code",
        "permission_mode": "safe",
    }
    body.update(overrides)
    return body


def _expected_brief(body: dict[str, Any]) -> str:
    """Compose the brief the endpoint should have written, independently."""
    context = ImportSessionContext(
        source_location=body["source_location"],
        has_no_codebase=body["has_no_codebase"],
        destination_tier=body["destination_tier"],
        data_kinds=tuple(body["data_kinds"]),
        data_kinds_other=body["data_kinds_other"],
        workflow_description=body["workflow_description"],
        interaction_wishes=body["interaction_wishes"],
        other_software=body["other_software"],
        skipped=frozenset(body["skipped"]),
        provider=body["provider"],
        permission_mode=body["permission_mode"],
    )
    return compose_brief(context)


def _start(client: TestClient, project_dir: Path, **overrides: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """POST a session and return ``(request_body, response_json)``."""
    body = _payload(project_dir, **overrides)
    resp = client.post("/api/work-import/sessions", json=body)
    assert resp.status_code == 200, resp.text
    return body, resp.json()


# ---------------------------------------------------------------------------
# Contract C3 — the response the dialog consumes
# ---------------------------------------------------------------------------


def test_response_carries_exactly_the_contract_c3_fields(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The dialog is written against this shape; it must not drift."""
    body, data = _start(client, opened_project)

    assert set(data) == {"tab_id", "title", "brief_path", "provider", "permission_mode"}
    assert isinstance(data["tab_id"], str) and len(data["tab_id"]) == 12
    assert data["title"] == work_import.SESSION_TITLE == "Bring in my work"
    assert data["brief_path"].startswith(".scistudio/work-import/")
    assert data["brief_path"].endswith(".md")
    assert data["provider"] == body["provider"]
    assert data["permission_mode"] == body["permission_mode"]


def test_the_returned_tab_is_a_live_registered_pty(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-022: the session is spawned through the AI Block's own mechanism.

    A ``tab_id`` the frontend cannot connect to would make the endpoint a
    no-op that looks like a success.
    """
    _body, data = _start(client, opened_project)

    assert data["tab_id"] in _active_ptys
    assert len(spawn.calls) == 1
    assert spawn.calls[0]["provider"] == "claude-code"
    assert spawn.calls[0]["project_dir"] == opened_project


# ---------------------------------------------------------------------------
# FR-024 — the brief is complete on disk before the agent exists
# ---------------------------------------------------------------------------


def test_brief_is_complete_on_disk_before_the_agent_is_spawned(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-024, observed from inside the spawn rather than after it.

    The recorder reads the file named in the opening message at the exact
    moment the agent process would be created. A spawn that raced the
    write would see no file; a spawn that raced the *close* would see a
    prefix. Both fail here.
    """
    body, data = _start(client, opened_project)

    call = spawn.calls[0]
    assert call["brief_rel"] == data["brief_path"], "the opening message must name the brief that was written"
    assert call["brief_exists_at_spawn"], "the brief did not exist when the agent was spawned"
    assert call["brief_text_at_spawn"] == _expected_brief(body), "the agent was spawned against an incomplete brief"


def test_no_agent_is_spawned_when_the_brief_cannot_be_written(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of FR-024: never spawn against a brief that is not there.

    A session started after a failed write would open, greet the user, and
    then have nothing to do — a worse outcome than a visible error.
    """

    def boom(project_dir: Path, text: str) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(work_import, "_write_brief", boom)

    resp = client.post("/api/work-import/sessions", json=_payload(opened_project))

    assert resp.status_code == 500
    assert spawn.calls == [], "a failed brief write must not be followed by a spawn"


# ---------------------------------------------------------------------------
# FR-030 — one brief per session
# ---------------------------------------------------------------------------


def test_two_sessions_in_one_project_get_distinct_brief_files(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-030: concurrent sessions must not overwrite each other's instructions."""
    first_body, first = _start(client, opened_project, workflow_description="Session one's description.")
    second_body, second = _start(client, opened_project, workflow_description="Session two's description.")

    assert first["brief_path"] != second["brief_path"]
    assert first["tab_id"] != second["tab_id"]

    first_file = opened_project / first["brief_path"]
    second_file = opened_project / second["brief_path"]
    assert first_file.is_file() and second_file.is_file()
    assert first_file.read_text(encoding="utf-8") == _expected_brief(first_body)
    assert second_file.read_text(encoding="utf-8") == _expected_brief(second_body)
    # Each agent was pointed at its own brief, not at the other's.
    assert spawn.calls[0]["brief_rel"] == first["brief_path"]
    assert spawn.calls[1]["brief_rel"] == second["brief_path"]


def test_a_brief_outlives_its_session(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """FR-030's second reason: the record of what the agent was told persists.

    The PTY is torn down here the way a closed tab tears it down; the brief
    must still be readable afterwards, because that is how a user finds out
    what their agent was actually asked to do when a session went wrong.
    """
    _body, data = _start(client, opened_project)
    brief_file = opened_project / data["brief_path"]

    pty = _active_ptys.pop(data["tab_id"])
    pty.kill_tree()

    assert brief_file.is_file()
    assert brief_file.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# FR-027 — the brief is runtime state, not project content
# ---------------------------------------------------------------------------


def test_brief_lands_under_dot_scistudio(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """FR-027: the brief goes under the project's ``.scistudio/`` directory."""
    _body, data = _start(client, opened_project)

    parts = Path(data["brief_path"]).parts
    assert parts[0] == ".scistudio"
    assert (opened_project / ".scistudio" / "work-import").is_dir()
    assert (opened_project / data["brief_path"]).is_file()


def test_default_project_ignore_file_excludes_the_brief(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-027: session state must not enter the user's version history.

    Asserted against real ``git check-ignore`` in a real project rather
    than against the template text, so a future move of the brief to a
    path that merely *looks* ignored is caught.
    """
    assert ".scistudio/" in DEFAULT_GITIGNORE, "the default project template no longer ignores .scistudio/"
    assert (opened_project / ".gitignore").is_file(), "the opened project has no .gitignore to test against"

    _body, data = _start(client, opened_project)

    result = GitBinary.locate().run(
        ["check-ignore", "--quiet", "--", data["brief_path"]],
        cwd=opened_project,
        check=False,
    )
    assert result.returncode == 0, f"git does not ignore {data['brief_path']!r}: {result.stderr}"


# ---------------------------------------------------------------------------
# FR-028 — one visible line
# ---------------------------------------------------------------------------


def test_opening_message_is_a_single_line_naming_the_brief(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-028: the user watching the terminal sees a sentence, not a brief."""
    body, data = _start(client, opened_project)

    prompt = spawn.calls[0]["prompt"]
    assert "\n" not in prompt and "\r" not in prompt, f"the opening message is not a single line: {prompt!r}"
    assert data["brief_path"] in prompt
    # The brief's own text stays in the file. If the instruction set were
    # inlined here, the terminal would open with a wall of text and FR-028
    # would be defeated even though a path also appeared.
    assert _expected_brief(body) not in prompt
    assert len(prompt) < 200


def test_opening_message_wording_is_actionable() -> None:
    """The line has to read as an instruction, not as a filename."""
    message = work_import._opening_message(".scistudio/work-import/brief.md")

    assert message == "Read the file .scistudio/work-import/brief.md and follow the instructions in it."


# ---------------------------------------------------------------------------
# FR-029 — delivery does not depend on the provider
# ---------------------------------------------------------------------------


def test_registry_still_has_both_system_prompt_strategies() -> None:
    """Guards the parametrised test below from silently covering one strategy.

    FR-029 exists because the registry is mixed. If it ever stopped being
    mixed, the provider-independence test would still pass while proving
    nothing.
    """
    strategies = {descriptor.system_prompt.strategy for descriptor in agent_descriptors()}
    assert SystemPromptStrategy.FLAG_FILE in strategies
    assert SystemPromptStrategy.AMBIENT in strategies


@pytest.mark.parametrize("provider", [descriptor.key for descriptor in agent_descriptors()])
def test_delivery_is_identical_across_system_prompt_strategies(
    provider: str, client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-029: a ``FLAG_FILE`` and an ``AMBIENT`` provider are served the same way.

    Only ``claude-code`` can carry a hidden per-session prompt; the other
    four have no per-session channel at all. Routing through a file plus a
    pointer is what makes that difference invisible here.
    """
    body, data = _start(client, opened_project, provider=provider)

    call = spawn.calls[0]
    assert call["provider"] == provider
    assert call["brief_exists_at_spawn"]
    assert call["brief_text_at_spawn"] == _expected_brief(body)
    # Same message, modulo the per-session filename.
    assert call["prompt"].replace(data["brief_path"], "<BRIEF>") == (
        "Read the file <BRIEF> and follow the instructions in it."
    )
    # No provider-specific side channel is used to carry any of it.
    assert call["extra_env"] is None


# ---------------------------------------------------------------------------
# §7.4 — the permission-mode boundary trap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("permission_mode", "dangerous"), [("safe", False), ("bypass", True)])
def test_backend_permission_spelling_is_accepted_and_applied(
    permission_mode: str, dangerous: bool, client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The backend spelling is ``safe`` | ``bypass``, and it reaches the spawn."""
    _body, data = _start(client, opened_project, permission_mode=permission_mode)

    assert data["permission_mode"] == permission_mode
    assert spawn.calls[0]["dangerous"] is dangerous


def test_frontend_permission_spelling_is_rejected(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """``dangerous`` is the *frontend* union member; the dialog maps it.

    Accepting it here would let an unmapped request through and silently
    downgrade a bypass session to safe mode, or vice versa, depending on
    which side later changed.
    """
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, permission_mode="dangerous"))

    assert resp.status_code == 422
    assert spawn.calls == []


def test_unknown_permission_mode_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, permission_mode="yolo"))

    assert resp.status_code == 422
    assert spawn.calls == []


# ---------------------------------------------------------------------------
# Request validation — nothing is spawned or written on a bad request
# ---------------------------------------------------------------------------


def test_unknown_provider_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """ADR-034 FR-010: the provider is stated, never inferred or defaulted."""
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, provider="not-a-provider"))

    assert resp.status_code == 400
    assert spawn.calls == []
    assert not (opened_project / ".scistudio" / "work-import").exists()


def test_user_terminal_is_not_an_import_provider(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The shell pseudo-provider cannot read a brief; it must not be accepted."""
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, provider="user-terminal"))

    assert resp.status_code == 400
    assert spawn.calls == []


def test_relative_project_dir_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, project_dir="relative/path"))

    assert resp.status_code == 400
    assert spawn.calls == []


def test_missing_project_dir_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    resp = client.post(
        "/api/work-import/sessions",
        json=_payload(opened_project, project_dir=str(opened_project / "does-not-exist")),
    )

    assert resp.status_code == 400
    assert spawn.calls == []


def test_unknown_skipped_question_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """FR-021: a skip marker that no question owns would be dropped silently.

    The brief would then render an explicitly-skipped question as merely
    unanswered, which is the exact distinction the skip marker exists to
    preserve.
    """
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, skipped=["destination_tier"]))

    assert resp.status_code == 422
    assert spawn.calls == []


def test_no_codebase_session_is_a_first_class_path(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-009/FR-010: a user with spreadsheets and no code gets a real session."""
    body, data = _start(
        client,
        opened_project,
        source_location=None,
        has_no_codebase=True,
        workflow_description="Everything lives in one Excel workbook with a lot of manual copying.",
    )

    assert spawn.calls[0]["brief_text_at_spawn"] == _expected_brief(body)
    assert (opened_project / data["brief_path"]).is_file()


def test_pty_cap_reached_returns_503(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-034 §8: the shared terminal cap applies to import sessions too."""
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 0)

    resp = client.post("/api/work-import/sessions", json=_payload(opened_project))

    assert resp.status_code == 503
    assert spawn.calls == []


# ---------------------------------------------------------------------------
# Joining the pre-spawned session PTY, without AI Block semantics
# ---------------------------------------------------------------------------


def _ws_url(tab_id: str, project_dir: Path, *, provider: str = "claude-code", dangerous: bool = False) -> str:
    return (
        f"/api/ai/pty/{tab_id}"
        f"?project_dir={quote(str(project_dir))}"
        f"&provider={provider}"
        f"&dangerous={'true' if dangerous else 'false'}"
    )


def test_frontend_joins_the_pre_spawned_session_instead_of_starting_a_second_agent(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The tab the endpoint returned must attach to the agent it started.

    A second spawn here would orphan the agent that was given the brief and
    leave the user talking to one that was told nothing.
    """
    _body, data = _start(client, opened_project)
    tab_id = data["tab_id"]
    session_pty = _active_ptys[tab_id]
    assert len(spawn.calls) == 1

    with client.websocket_connect(_ws_url(tab_id, opened_project)) as ws:
        with contextlib.suppress(Exception):
            ws.receive_json(timeout=0.5)
        assert _active_ptys.get(tab_id) is session_pty

    assert len(spawn.calls) == 1, f"the join must not spawn a second agent; got {spawn.calls}"


def test_work_import_tab_carries_no_ai_block_semantics(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """An import session is an ordinary chat session (FR-025).

    Block cancel and mark-done frames are addressed by ``block_run_id``; a
    work-import tab that appeared in those maps would let an unrelated AI
    Block control frame reach into this session.
    """
    _body, data = _start(client, opened_project)
    tab_id = data["tab_id"]

    assert tab_id not in _engine_tab_to_run
    assert get_block_run_id_for_tab(tab_id) is None
    assert _engine_run_to_run_dir == {}
    assert not hasattr(_active_ptys[tab_id], "_engine_block_run_id")


# ---------------------------------------------------------------------------
# Regression pin — the ADR-034-frozen user-launched route is unchanged
#
# The join predicate in ``ai_pty/websocket.py`` was widened to recognise a
# provider-neutral pre-spawn marker. These tests pin the four things the
# freeze protects: the query-parameter contract, spawn semantics, error
# frames, and cap behaviour.
# ---------------------------------------------------------------------------


def test_user_launched_tab_still_spawns_with_its_query_parameters(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """A tab_id nobody pre-spawned still spawns from the WS query string."""
    url = f"{_ws_url('tab-user-launched', opened_project, provider='codex', dangerous=True)}&cols=101&rows=33"

    with client.websocket_connect(url) as ws:
        with contextlib.suppress(Exception):
            ws.receive_json(timeout=0.5)
        assert "tab-user-launched" in _active_ptys

    assert len(spawn.calls) == 1
    call = spawn.calls[0]
    assert call["provider"] == "codex"
    assert call["dangerous"] is True
    assert (call["cols"], call["rows"]) == (101, 33)
    assert call["prompt"] == "", "a user-launched tab carries no pre-seeded prompt"


def test_user_launched_tab_is_removed_from_the_registry_on_disconnect(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """Teardown semantics are part of the frozen contract."""
    with (
        client.websocket_connect(_ws_url("tab-teardown", opened_project)) as ws,
        contextlib.suppress(Exception),
    ):
        ws.receive_json(timeout=0.5)

    assert "tab-teardown" not in _active_ptys


def test_user_launched_invalid_provider_still_returns_the_enumerated_error_frame(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    with client.websocket_connect(_ws_url("tab-bad-provider", opened_project, provider="bogus")) as ws:
        frame = ws.receive_json()

    assert frame["type"] == "error"
    assert "Invalid provider" in frame["message"]
    assert "claude-code" in frame["message"]
    assert spawn.calls == []


def test_user_launched_missing_project_dir_still_returns_an_error_frame(
    client: TestClient, spawn: _SpawnRecorder
) -> None:
    with client.websocket_connect("/api/ai/pty/tab-no-dir?provider=claude-code") as ws:
        frame = ws.receive_json()

    assert frame["type"] == "error"
    assert "project_dir" in frame["message"]
    assert spawn.calls == []


def test_user_launched_cap_behaviour_is_unchanged(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap is still enforced before the spawn, with the same message."""
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 0)

    with client.websocket_connect(_ws_url("tab-capped", opened_project)) as ws:
        frame = ws.receive_json()

    assert frame["type"] == "error"
    assert "active terminals" in frame["message"]
    assert spawn.calls == []


def test_an_unmarked_registered_pty_is_never_joined(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The widened predicate must not turn every registry entry into a join target.

    Only a PTY that was deliberately pre-spawned server-side carries the
    marker. A leftover user-launched entry under the same tab_id must still
    take the spawn path, exactly as before.
    """
    stray = PtyProcess(_echo_argv(), cwd=opened_project, cols=80, rows=24)
    _active_ptys["tab-stray"] = stray
    try:
        with client.websocket_connect(_ws_url("tab-stray", opened_project)) as ws:
            with contextlib.suppress(Exception):
                ws.receive_json(timeout=0.5)
            assert _active_ptys.get("tab-stray") is not stray
    finally:
        with contextlib.suppress(Exception):
            stray.kill_tree()

    assert len(spawn.calls) == 1, "an unmarked PTY must not be joined"
