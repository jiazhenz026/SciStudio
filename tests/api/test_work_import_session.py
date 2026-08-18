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

from scistudio.ai.agent import providers_registry
from scistudio.ai.agent import terminal as terminal_module
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
    engine,
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
        "anything_else": "Please ask before you touch anything under raw/.",
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
        anything_else=body["anything_else"],
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


#: Registry agents a SciStudio-started session can actually be delivered to.
#:
#: FR-029 removes the *system-prompt* difference between providers. It does not
#: remove the one requirement delivery still has: the pointer is a positional
#: command-line argument, and a CLI that parses its first positional as a
#: subcommand never receives it. The registry records exactly that with
#: ``prompt_argv_prefix is None``, so the split is read off the registry rather
#: than listed here — a sixth provider lands on the right side of it by itself.
_DELIVERABLE_PROVIDERS = [d.key for d in agent_descriptors() if d.prompt_argv_prefix is not None]
_UNDELIVERABLE_PROVIDERS = [d.key for d in agent_descriptors() if d.prompt_argv_prefix is None]


def test_the_registry_still_contains_a_provider_that_cannot_take_a_prompt() -> None:
    """Guards the split above from silently covering one side.

    If every registry agent gained a positional prompt, the refusal tests below
    would pass while exercising nothing, and the endpoint's guard could be
    deleted without a failure.
    """
    assert _DELIVERABLE_PROVIDERS
    assert _UNDELIVERABLE_PROVIDERS


@pytest.mark.parametrize("provider", _DELIVERABLE_PROVIDERS)
def test_delivery_is_identical_across_system_prompt_strategies(
    provider: str, client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-029: a ``FLAG_FILE`` and an ``AMBIENT`` provider are served the same way.

    Only ``claude-code`` can carry a hidden per-session prompt; the others
    have no per-session channel at all. Routing through a file plus a
    pointer is what makes that difference invisible here.

    This runs against a stubbed ``_spawn``, so what it proves is that the
    *endpoint* hands every provider the same message and the same complete
    brief. It does NOT prove the message can be delivered — the stub never
    reaches argv assembly. That was the gap the 2026-08-07 no-context audit
    found, and it is closed by
    ``test_the_opening_message_reaches_the_command_line_for_every_provider``
    below, which runs the real assembly.
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


@pytest.mark.parametrize("provider", _DELIVERABLE_PROVIDERS)
def test_the_opening_message_reaches_the_command_line_for_every_provider(
    provider: str, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The argv every offered provider is actually launched with carries the pointer.

    The test the audit asked for. The endpoint suite stubs ``_spawn``, which is
    right for everything it pins and wrong for this one claim: a test that named
    five providers and exercised the failing path for none of them read as
    coverage for FR-029 while the real ``spawn_agent`` raised ``ValueError`` for
    one of them, and the endpoint turned that into a 500.

    So this drives ``spawn_agent`` itself — real descriptor, real binary
    resolution, real ``_initial_prompt_argv`` — and stubs only ``PtyProcess``,
    the one step that would start a process.
    """
    recorded: list[list[str]] = []

    def record(argv: list[str], **_kwargs: Any) -> object:
        recorded.append(list(argv))
        return object()

    monkeypatch.setattr(terminal_module, "PtyProcess", record)
    message = work_import._opening_message(".scistudio/work-import/brief.md")

    terminal_module.spawn_agent(
        descriptor=providers_registry.get(provider),
        project_dir=opened_project,
        dangerous=False,
        prompt=message,
    )

    assert recorded, "spawn_agent did not build an argv"
    assert message in recorded[0], f"{provider} never receives the opening message"


@pytest.mark.parametrize("provider", _UNDELIVERABLE_PROVIDERS)
def test_a_provider_with_no_positional_prompt_is_refused_before_anything_is_written(
    provider: str, client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The P1 the 2026-08-07 no-context audit reproduced, from both ends.

    Observed before the fix: ``POST`` with ``provider: "kimi-code"`` returned
    ``{"detail": "Internal Server Error"}`` — the registry's own explanatory
    sentence lost inside an unhandled ``ValueError`` — and left an orphaned
    brief in the user's project for a session that never started. It was
    reachable: the provider grades ``ready`` on a live call, so the dialog
    offered it, and FR-043 auto-selected it when it was the only usable one.

    Three things are pinned. A 4xx, because this is a bad request rather than a
    server fault. The registry's sentence, because it is the only text that
    tells the user what to do. And an untouched project, because the brief is
    written before the spawn (FR-024) and a refusal that came later would leave
    one behind.
    """
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, provider=provider))

    assert 400 <= resp.status_code < 500, f"expected 4xx, got {resp.status_code}: {resp.text}"
    assert "Internal Server Error" not in resp.text
    reason = providers_registry.get(provider).prompt_unsupported_reason
    assert reason and reason in resp.json()["detail"]
    assert spawn.calls == []
    assert not (opened_project / ".scistudio" / "work-import").exists()


@pytest.mark.parametrize("provider", _UNDELIVERABLE_PROVIDERS)
def test_the_spawn_path_agrees_that_such_a_provider_cannot_be_launched(
    provider: str, opened_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal above matches what the spawn would really have done.

    Without this the endpoint guard could drift into refusing a provider that
    works, or stop refusing one that does not, and the endpoint test alone would
    not notice: it asserts the guard's own behaviour, not the reason for it.
    """
    monkeypatch.setattr(terminal_module, "PtyProcess", lambda argv, **_kwargs: object())

    with pytest.raises(ValueError, match="cannot receive an initial prompt"):
        terminal_module.spawn_agent(
            descriptor=providers_registry.get(provider),
            project_dir=opened_project,
            dangerous=False,
            prompt=work_import._opening_message(".scistudio/work-import/brief.md"),
        )


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


def test_unknown_destination_tier_is_rejected(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """The destination is a closed set; the wire shape rejects anything else."""
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, destination_tier="somewhere-else"))

    assert resp.status_code == 422
    assert spawn.calls == []


# ---------------------------------------------------------------------------
# Contract C2 answer-shape rules
#
# ``ImportSessionContext.__post_init__`` owns them and signals a violation with
# ``ValueError``. Each one describes a dialog state the user cannot actually
# produce, so it is a bad request: the endpoint must answer 4xx with the
# dataclass's own message, never 500. A 500 here would read as "SciStudio
# broke" for what is a caller bug, and would bury the message that says which
# rule was violated.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected_fragment"),
    [
        pytest.param({"skipped": ["destination_tier"]}, "skipped may only name", id="unskippable-question-skipped"),
        pytest.param({"has_no_codebase": True}, "source_location must be empty", id="source-and-no-codebase"),
        pytest.param(
            {"source_location": None, "has_no_codebase": False},
            "source location is required",
            id="neither-source-nor-no-codebase",
        ),
        pytest.param({"skipped": ["interaction_wishes"]}, "carries an answer", id="skipped-but-answered"),
        pytest.param({"provider": "   "}, "provider", id="blank-provider"),
    ],
)
def test_answer_shape_violations_are_4xx_with_a_usable_message(
    overrides: dict[str, Any],
    expected_fragment: str,
    client: TestClient,
    opened_project: Path,
    spawn: _SpawnRecorder,
) -> None:
    """Every contract-C2 ``ValueError`` reaches the caller as a 4xx, not a 500."""
    resp = client.post("/api/work-import/sessions", json=_payload(opened_project, **overrides))

    assert 400 <= resp.status_code < 500, f"expected 4xx, got {resp.status_code}: {resp.text}"
    assert expected_fragment in resp.text, f"response does not say what was wrong: {resp.text}"
    assert spawn.calls == []
    assert not (opened_project / ".scistudio" / "work-import").exists()


def test_a_blank_answer_is_a_valid_session_not_an_error(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-021: a blank optional answer renders as skipped rather than failing.

    The dialog lets a user tab past a question without pressing skip. That
    has to start a session, not return an error, and the brief has to say the
    user did not answer rather than pretend they said nothing applies.
    """
    body, data = _start(
        client,
        opened_project,
        interaction_wishes="   ",
        other_software=None,
        anything_else="   ",
        skipped=[],
    )

    assert spawn.calls[0]["brief_text_at_spawn"] == _expected_brief(body)
    assert (opened_project / data["brief_path"]).is_file()


def test_the_final_open_answer_reaches_the_brief_the_agent_reads(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-019a with FR-023: question 5 is an answer like any other, not a note.

    It is the one question the user was not told what to say to, so it is also
    the one most likely to carry the fact that changes how the session should go
    — asserted against the file on disk rather than the composed string, because
    the file is what the agent opens.
    """
    body, data = _start(client, opened_project, anything_else="Please ask before you touch anything under raw/.")

    written = (opened_project / data["brief_path"]).read_text(encoding="utf-8")
    assert body["anything_else"] in written
    assert written == _expected_brief(body)


def test_the_final_open_question_can_be_skipped(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """FR-019a: having nothing to add is an answer, and the brief says so."""
    body, data = _start(
        client,
        opened_project,
        anything_else=None,
        skipped=["other_software", "anything_else"],
    )

    written = (opened_project / data["brief_path"]).read_text(encoding="utf-8")
    assert written == _expected_brief(body)
    assert written.count("Skipped. They did not answer this.") == 2


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


def _age_prespawn(tab_id: str, seconds: float) -> None:
    """Backdate a pre-spawned tab's stamp so the reaper will consider it.

    Real time is not worth waiting out for a 120 s grace, and freezing the
    clock would hide whether the reaper reads the stamp at all.
    """
    pty = _active_ptys[tab_id]
    pty._engine_prespawned_at -= seconds  # type: ignore[attr-defined]


def _mark_joined(tab_id: str) -> None:
    """Stamp what ``pty_endpoint``'s join branch stamps on a completed handoff."""
    _active_ptys[tab_id]._engine_joined = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Orphan reclamation — a handoff that never completes must not hold a slot
# ---------------------------------------------------------------------------


def test_a_session_whose_websocket_never_arrives_is_reclaimed(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """A pre-spawned tab nobody joins is killed and deregistered.

    Only ``pty_endpoint``'s teardown pops ``_active_ptys``, so a handoff
    that never completes — the user dismisses the dialog, the tab
    navigates away, the WebSocket fails to open — would otherwise leave a
    live agent holding a cap slot for the lifetime of the server.
    """
    _body, data = _start(client, opened_project)
    tab_id = data["tab_id"]
    assert tab_id in _active_ptys

    # Nothing joined it, and it is older than the grace period.
    _age_prespawn(tab_id, engine.PRESPAWN_JOIN_GRACE_SECONDS + 1)

    assert engine.reclaim_orphaned_prespawned_tabs() == 1
    assert tab_id not in _active_ptys


def test_a_joined_session_is_never_reclaimed(client: TestClient, opened_project: Path, spawn: _SpawnRecorder) -> None:
    """A live tab is owned by its WebSocket, however long it has been open.

    Reaping on age alone would kill the sessions this feature exists to
    produce: a Bring In My Work session is long — the user talks to it
    while the agent reads a codebase and writes blocks.
    """
    _body, data = _start(client, opened_project)
    tab_id = data["tab_id"]

    # The join branch of ``pty_endpoint`` stamps this.
    _mark_joined(tab_id)
    _age_prespawn(tab_id, engine.PRESPAWN_JOIN_GRACE_SECONDS * 100)

    assert engine.reclaim_orphaned_prespawned_tabs() == 0
    assert tab_id in _active_ptys


def test_a_recent_unjoined_session_is_left_alone(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder
) -> None:
    """The window between the POST returning and the WebSocket connecting.

    Reclaiming inside it would kill the session the caller is in the
    middle of handing over, which is worse than the leak it prevents.
    """
    _body, data = _start(client, opened_project)
    assert engine.reclaim_orphaned_prespawned_tabs() == 0
    assert data["tab_id"] in _active_ptys


def test_orphans_do_not_permanently_consume_the_cap(
    client: TestClient, opened_project: Path, spawn: _SpawnRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure mode this reclamation exists for.

    Repeated failed handoffs used to fill ``MAX_ACTIVE_PTYS`` and refuse
    every agent chat until a restart. A later session must succeed.
    """
    monkeypatch.setattr(ai_pty._state, "MAX_ACTIVE_PTYS", 2)

    first = _start(client, opened_project)[1]["tab_id"]
    second = _start(client, opened_project)[1]["tab_id"]
    assert len(_active_ptys) == 2

    # Both handoffs failed: nobody ever connected, and the grace has passed.
    for tab_id in (first, second):
        _age_prespawn(tab_id, engine.PRESPAWN_JOIN_GRACE_SECONDS + 1)

    # Before the fix this raised the cap error instead of starting.
    third = _start(client, opened_project)[1]["tab_id"]
    assert third in _active_ptys
    assert first not in _active_ptys
    assert second not in _active_ptys


def test_reclaiming_an_ai_block_orphan_clears_its_run_maps(opened_project: Path, spawn: _SpawnRecorder) -> None:
    """An AI Block orphan must not leave a stale block_run_id pointer.

    ``pty_endpoint``'s teardown clears both maps; the reaper is the other
    path that removes a tab, so it owes the same cleanup.
    """
    tab_id = engine.open_engine_initiated_tab(
        title="AI Block",
        provider="claude-code",
        cwd=str(opened_project),
        initial_stdin="do the thing",
        block_run_id="run-42",
        permission_mode="safe",
        run_dir_path=str(opened_project),
    )
    assert _engine_tab_to_run[tab_id] == "run-42"

    _age_prespawn(tab_id, engine.PRESPAWN_JOIN_GRACE_SECONDS + 1)
    assert engine.reclaim_orphaned_prespawned_tabs() == 1

    assert tab_id not in _active_ptys
    assert tab_id not in _engine_tab_to_run
    assert "run-42" not in _engine_run_to_run_dir
