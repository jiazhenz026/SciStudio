"""Regressions for the five defects the owner found hand-testing ADR-034 (#1994).

Every test here was written against an observation made on a real machine with
``claude``, ``codex``, ``kimi`` and ``qoderclicn`` installed, not against a
mock. Where a test asserts a CLI fact — a flag name, an accepted value, the
presence or absence of a positional prompt — that fact was verified by running
the installed binary on 2026-08-06, and the surrounding comment records how.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scistudio.ai.agent import terminal
from scistudio.ai.agent.providers_registry import REGISTRY, ProviderDescriptor, get


@pytest.fixture
def spawned_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture the argv ``spawn_agent`` hands to :class:`PtyProcess`."""
    captured: list[list[str]] = []

    class _FakePty:
        def __init__(self, argv: list[str], cwd: Path, **_: object) -> None:
            captured.append(list(argv))

    monkeypatch.setattr(terminal, "PtyProcess", _FakePty)
    return captured


@pytest.fixture
def stable_binary(monkeypatch: pytest.MonkeyPatch):
    """Pin binary resolution so argv assertions do not depend on the host."""

    def _pin(name: str):
        monkeypatch.setattr(terminal, "_resolve_agent_binary", lambda _descriptor: name)

    return _pin


# ---------------------------------------------------------------------------
# Finding 2 — Manual Approve must be stated, not implied.
# ---------------------------------------------------------------------------


def _agents() -> tuple[ProviderDescriptor, ...]:
    return REGISTRY.agents()


@pytest.mark.parametrize("descriptor", _agents(), ids=lambda d: d.key)
def test_every_agent_declares_a_manual_mode_or_says_why_not(descriptor: ProviderDescriptor) -> None:
    """Manual mode is never left as an unexplained blank row.

    An empty ``manual_argv`` is a claim about a CLI's surface — that it has no
    flag asserting interactive approval — and a claim has to be written down.
    Without this invariant a provider added later inherits the silent default
    and reintroduces exactly the defect: a Manual Approve selection that passes
    no flag and lets the CLI resume its persisted auto-accept mode.
    """
    has_flag = bool(descriptor.manual_argv)
    has_reason = bool(descriptor.manual_argv_absent_reason)
    assert has_flag != has_reason, (
        f"{descriptor.key}: declare manual_argv, or explain its absence in "
        f"manual_argv_absent_reason — exactly one, never neither and never both."
    )


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        # `claude --permission-mode manual --help` exits 0; a bogus value exits 1.
        ("claude-code", ["--permission-mode", "manual"]),
        # `codex --ask-for-approval untrusted --help` exits 0; bogus exits 2.
        ("codex", ["--ask-for-approval", "untrusted"]),
        # `qoderclicn --permission-mode default --list-sessions` exits 0; a bogus
        # value exits 1 and prints the choice list.
        ("qoder", ["--permission-mode", "default"]),
        ("qoder-cn", ["--permission-mode", "default"]),
    ],
)
def test_safe_mode_passes_an_explicit_manual_flag(
    provider: str,
    expected: list[str],
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """Safe mode states the permission mode instead of staying silent.

    Before #1994 safe mode appended nothing, so ``claude-code`` came up in the
    auto mode persisted in its own settings and ``codex`` came up in YOLO —
    the user's Manual Approve selection had no effect on the process at all.
    """
    stable_binary("agent.exe")
    terminal.spawn_agent(get(provider), project_dir=tmp_path, dangerous=False)

    argv = spawned_argv[0]
    assert expected == argv[-len(expected) :], f"{provider} safe-mode argv did not end with {expected}: {argv}"


@pytest.mark.parametrize("descriptor", _agents(), ids=lambda d: d.key)
def test_bypass_mode_never_also_passes_the_manual_flag(
    descriptor: ProviderDescriptor,
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """The two permission fragments are exclusive, not additive."""
    stable_binary("agent.exe")
    terminal.spawn_agent(descriptor, project_dir=tmp_path, dangerous=True)

    argv = spawned_argv[0]
    for token in descriptor.manual_argv:
        assert token not in argv, f"{descriptor.key}: bypass argv leaked the manual flag {token!r}: {argv}"
    for token in descriptor.bypass_argv:
        assert token in argv, f"{descriptor.key}: bypass argv is missing {token!r}: {argv}"


# ---------------------------------------------------------------------------
# Finding 5a — codex received a prompt truncated at its first newline.
# ---------------------------------------------------------------------------


def test_cmd_launcher_truncates_a_multiline_argument_at_the_first_newline(tmp_path: Path) -> None:
    """The OS-level fact the codex fix rests on, pinned as an executable claim.

    ``codex`` installs from npm as ``codex.cmd`` and there is no ``codex.exe``
    on PATH, so ``CreateProcess`` runs it through ``cmd.exe``, whose parser ends
    the command line at the first line feed. This test demonstrates that on a
    batch launcher and its absence on a real executable, so a future reader can
    see *why* the flattening exists rather than taking it on trust.
    """
    if sys.platform != "win32":
        pytest.skip("cmd.exe command-line truncation is a Windows-only behaviour")

    echo_py = tmp_path / "echoargs.py"
    echo_py.write_text(
        textwrap.dedent(
            """
            import json, sys
            print("ARGS=" + json.dumps(sys.argv[1:]))
            """
        ).strip(),
        encoding="utf-8",
    )
    echo_cmd = tmp_path / "echoargs.cmd"
    echo_cmd.write_text(f'@echo off\n"{sys.executable}" "{echo_py}" %*\n', encoding="utf-8")

    multiline = "first line ends here:\n  second line\n\nthird line"

    via_exe = subprocess.run(
        [sys.executable, str(echo_py), "--", multiline],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    via_cmd = subprocess.run(
        [str(echo_cmd), "--", multiline],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert "third line" in via_exe, "a real executable must receive the whole argument"
    assert "third line" not in via_cmd, "expected cmd.exe to truncate at the first newline"


def test_batch_launcher_prompt_keeps_every_word(
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """A ``.cmd``-resolved provider gets the complete prompt on one line.

    This is the owner's finding 5a verbatim: the AI Block prompt reached codex
    cut off after ``manifest at:``, so the manifest path and the user's own
    task never arrived. Without the flattening this assertion fails at
    ``manifest.json`` — the very next token after the cut.
    """
    stable_binary("codex.CMD")
    prompt = "You are running as an AI Block. Your task is in the manifest at:\n  C:/p/manifest.json\n\nDo the thing.\n"

    terminal.spawn_agent(get("codex"), project_dir=tmp_path, dangerous=False, prompt=prompt)

    delivered = spawned_argv[0][-1]
    assert "\n" not in delivered, f"a batch launcher cannot carry a newline: {delivered!r}"
    for word in ("manifest.json", "C:/p/manifest.json", "Do the thing."):
        assert word in delivered, f"prompt lost {word!r}: {delivered!r}"


def test_real_executable_prompt_is_passed_through_untouched(
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """Providers that resolve to a real exe keep their exact multi-line prompt.

    The flattening is a workaround for one launcher shape and must not become a
    silent, global reformatting of every provider's prompt.
    """
    stable_binary("claude.EXE")
    prompt = "line one\n  line two\n\nline three\n"

    terminal.spawn_agent(get("claude-code"), project_dir=tmp_path, dangerous=False, prompt=prompt)

    assert spawned_argv[0][-1] == prompt


# ---------------------------------------------------------------------------
# Finding 5b — kimi-code exited 1 before painting anything.
# ---------------------------------------------------------------------------


def test_kimi_declares_that_it_cannot_take_a_command_line_prompt() -> None:
    """Verified by running the installed binary at 0.33.0.

    ``kimi -- "hello world"`` prints ``unknown command 'hello world'`` and exits
    1: ``kimi --help`` shows ``Usage: kimi [options] [command]`` with no
    ``[prompt]`` positional, so commander.js reads the first positional as a
    subcommand. ``-p/--prompt`` exists but runs one prompt non-interactively and
    exits, which cannot seed the interactive session an AI Block needs.
    """
    kimi = get("kimi-code")
    assert kimi.prompt_argv_prefix is None
    assert kimi.prompt_unsupported_reason


def test_kimi_launches_cleanly_when_no_prompt_is_requested(
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """A hand-launched Kimi chat tab must not carry a stray separator."""
    stable_binary("kimi.exe")
    terminal.spawn_agent(get("kimi-code"), project_dir=tmp_path, dangerous=False)

    assert "--" not in spawned_argv[0]


def test_spawning_kimi_with_a_prompt_fails_loudly(
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """Refuse rather than launch an agent that silently has no task.

    Previously this path appended ``["--", prompt]`` regardless, and the CLI
    exited 1 with an ``unknown command`` message buried in a PTY the user then
    watched close. Dropping the prompt instead would be worse: a healthy-looking
    agent that does nothing forever while the block's watcher waits.
    """
    stable_binary("kimi.exe")
    with pytest.raises(ValueError, match="cannot receive an initial prompt"):
        terminal.spawn_agent(get("kimi-code"), project_dir=tmp_path, dangerous=False, prompt="do the thing")


@pytest.mark.parametrize(
    "descriptor",
    [d for d in _agents() if d.prompt_argv_prefix is None],
    ids=lambda d: d.key,
)
def test_prompt_incapable_providers_explain_themselves(descriptor: ProviderDescriptor) -> None:
    """The reason string is user-facing, so it must exist and name the CLI."""
    assert descriptor.prompt_unsupported_reason
    assert descriptor.label.split()[0] in descriptor.prompt_unsupported_reason


# ---------------------------------------------------------------------------
# Finding 1 — the spawned CLI inherited the parent agent session's markers.
# ---------------------------------------------------------------------------


def test_parent_agent_session_markers_are_stripped_from_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """Starting SciStudio from inside an agent session must not infect the child.

    The owner's Claude Code tab announced ``Transcript saving is off — inherited
    CLAUDE_CODE_CHILD_SESSION marker``: the backend had been launched from a
    Claude Code session, the marker rode ``os.environ`` into the spawned PTY,
    and the child concluded it was a nested invocation and stopped recording its
    own transcript.
    """
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_SANDBOX", "seatbelt")

    env = terminal._build_child_env()

    assert "CLAUDE_CODE_CHILD_SESSION" not in env
    assert "CLAUDECODE" not in env
    assert "CODEX_SANDBOX" not in env


@pytest.mark.parametrize("descriptor", _agents(), ids=lambda d: d.key)
@pytest.mark.parametrize("dangerous", [False, True], ids=["manual", "bypass"])
def test_no_spawn_ever_answers_a_security_prompt_for_the_user(
    descriptor: ProviderDescriptor,
    dangerous: bool,
    tmp_path: Path,
    spawned_argv: list[list[str]],
    stable_binary,
) -> None:
    """#1994 finding 3: SciStudio must not disarm a CLI's own trust review.

    Codex 0.130+ gates hook *execution* behind an interactive review, and
    SciStudio's provisioned hooks sit behind it: a Codex TUI opened in a
    provisioned project shows ``SessionStart 2 0 2 … Press t to trust all;
    enter to review hooks`` — two declared, zero trusted — and fires none of
    them until the user answers.

    ``--dangerously-bypass-hook-trust`` would make them fire, and it is the
    wrong answer. It disarms the review for the entire config file, user
    additions included, on every launch — including one where the user chose
    Manual Approve. Removing one user decision in the same spawn that
    ``manual_argv`` exists to restore another cannot both be right, so the
    trust decision stays with the user. The panel is rendered into the PTY and
    is answerable there.

    Asserted across both permission modes and every provider: a bypass that
    crept in under ``dangerous`` only would be just as unauthorised, and the
    next provider added must not inherit one silently.
    """
    stable_binary("agent.exe")
    terminal.spawn_agent(descriptor, project_dir=tmp_path, dangerous=dangerous)

    leaked = [token for token in spawned_argv[0] if "hook-trust" in token or "bypass-hook" in token]
    assert not leaked, f"{descriptor.key}: spawn answered a trust prompt for the user: {leaked}"


def test_user_configuration_in_the_same_namespaces_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only session markers are stripped, never deliberate configuration.

    ``CLAUDE_*`` and ``ANTHROPIC_*`` also carry the config dir and credentials
    the spawned CLI needs; a prefix sweep would have broken authentication.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/somewhere")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    env = terminal._build_child_env()

    assert env["CLAUDE_CONFIG_DIR"] == "/somewhere"
    assert env["ANTHROPIC_API_KEY"] == "sk-test"
