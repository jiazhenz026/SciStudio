"""#2452 — permission-mode argv must be accepted by each provider's CLI parser.

Codex Auto shipped as ``--approve-for-me --ask-for-approval on-request``. clap
rejects that pair and the PTY exited 2 before painting. The registry check
that let it through ran the argv with ``--help``, which returns before clap
validates argument combinations, so it proved nothing.

Two guards live here:

* A static table of mutual exclusions each CLI enforces, observed by launching
  the installed binary with stdin not a terminal (codex-cli 0.154.0, kimi
  0.42.0). Every mode's full spawn argv is checked against it, so the guard
  also covers flags added by other parts of the launch path such as the MCP
  overrides.
* An opt-in test that launches every installed provider with every mode's argv
  and asserts the CLI did not stop at argument parsing. It is skipped unless
  ``SCISTUDIO_RUN_CLI_ARGV_TESTS=1`` and the binary is on ``PATH``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scistudio.ai.agent import terminal
from scistudio.ai.agent.providers_registry import PERMISSION_MODES, REGISTRY, ProviderDescriptor

#: Flags each CLI refuses to combine, as ``({flag and its aliases}, {conflicting flags})``.
#: Aliases matter: ``-a`` and ``--ask-for-approval`` are the same clap argument.
MUTUAL_EXCLUSIONS: dict[str, tuple[tuple[frozenset[str], frozenset[str]], ...]] = {
    # codex-cli 0.154.0: "the argument '--approve-for-me' cannot be used with"
    # '--ask-for-approval', '--sandbox' and
    # '--dangerously-bypass-approvals-and-sandbox' (each exits 2).
    "codex": (
        (
            frozenset({"--approve-for-me"}),
            frozenset({"-a", "--ask-for-approval", "-s", "--sandbox", "--dangerously-bypass-approvals-and-sandbox"}),
        ),
    ),
    # kimi 0.42.0: "error: Cannot combine --yolo with --auto." (exits 1).
    "kimi-code": ((frozenset({"-y", "--yolo"}), frozenset({"--auto"})),),
}


def _flag_tokens(argv: list[str] | tuple[str, ...]) -> set[str]:
    """Option names in *argv*, with any ``=value`` suffix dropped."""
    return {token.split("=", 1)[0] for token in argv if token.startswith("-")}


def _conflicts(key: str, argv: list[str] | tuple[str, ...]) -> list[tuple[str, str]]:
    tokens = _flag_tokens(argv)
    found: list[tuple[str, str]] = []
    for flags, excluded in MUTUAL_EXCLUSIONS.get(key, ()):
        for flag in flags & tokens:
            found.extend((flag, other) for other in sorted(excluded & tokens))
    return found


@pytest.fixture
def spawned_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    captured: list[list[str]] = []

    class _FakePty:
        def __init__(self, argv: list[str], cwd: Path, **_: object) -> None:
            captured.append(list(argv))

    monkeypatch.setattr(terminal, "PtyProcess", _FakePty)
    monkeypatch.setattr(terminal, "_resolve_agent_binary", lambda _descriptor: "agent")
    return captured


def test_codex_auto_is_approve_for_me_alone() -> None:
    assert REGISTRY.get("codex").permission_argv("auto") == ("--approve-for-me",)


def test_the_conflict_table_catches_the_2452_argv() -> None:
    assert _conflicts("codex", ("--approve-for-me", "--ask-for-approval", "on-request")) == [
        ("--approve-for-me", "--ask-for-approval")
    ]
    assert _conflicts("codex", ("--approve-for-me", "-s", "workspace-write")) == [("--approve-for-me", "-s")]
    assert _conflicts("kimi-code", ("--yolo", "--auto")) == [("--yolo", "--auto")]


@pytest.mark.parametrize("mode", PERMISSION_MODES)
@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_no_mode_argv_combines_mutually_exclusive_flags(descriptor: ProviderDescriptor, mode: str) -> None:
    if mode == "auto" and not descriptor.supports_auto_mode:
        pytest.skip(f"{descriptor.key} has no Auto mode")
    assert _conflicts(descriptor.key, descriptor.permission_argv(mode)) == []


@pytest.mark.parametrize("mode", PERMISSION_MODES)
@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_full_spawn_argv_combines_no_mutually_exclusive_flags(
    descriptor: ProviderDescriptor, mode: str, tmp_path: Path, spawned_argv: list[list[str]]
) -> None:
    """The whole launch argv, MCP overrides included, stays conflict-free."""
    if mode == "auto" and not descriptor.supports_auto_mode:
        pytest.skip(f"{descriptor.key} has no Auto mode")
    terminal.spawn_agent(
        descriptor,
        project_dir=tmp_path,
        dangerous=mode == "bypass",
        auto=mode == "auto",
    )
    assert _conflicts(descriptor.key, spawned_argv[0]) == [], spawned_argv[0]


# ---------------------------------------------------------------------------
# Opt-in: parse each mode's argv with the installed CLI
# ---------------------------------------------------------------------------

#: Messages clap (codex) and commander (claude, kimi) print when they stop at
#: argument parsing. Neither ``--help`` nor ``--version`` is used: both return
#: before combinations are validated.
_PARSE_ERROR = re.compile(
    r"cannot be used with|unexpected argument|unknown option|invalid value|is invalid"
    r"|Cannot combine|argument missing|required arguments were not provided",
    re.IGNORECASE,
)

_RUN_CLI_TESTS = os.environ.get("SCISTUDIO_RUN_CLI_ARGV_TESTS") == "1"


@pytest.mark.serial
@pytest.mark.skipif(not _RUN_CLI_TESTS, reason="set SCISTUDIO_RUN_CLI_ARGV_TESTS=1 to launch installed agent CLIs")
@pytest.mark.parametrize("mode", PERMISSION_MODES)
@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_installed_cli_accepts_each_mode_argv(descriptor: ProviderDescriptor, mode: str, tmp_path: Path) -> None:
    binary = next((found for name in descriptor.binary_candidates if (found := shutil.which(name))), None)
    if binary is None:
        pytest.skip(f"{descriptor.key} is not on PATH")
    if mode == "auto" and not descriptor.supports_auto_mode:
        pytest.skip(f"{descriptor.key} has no Auto mode")

    argv = [binary, *descriptor.permission_argv(mode)]
    # stdin is not a terminal, so an interactive CLI that got past parsing
    # exits on its own ("stdin is not a terminal", or print mode with no
    # input); one that keeps running past the timeout also got past parsing.
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=tmp_path,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return
    output = f"{completed.stdout}\n{completed.stderr}"
    assert not _PARSE_ERROR.search(output), (
        f"{argv} was rejected by the parser (exit {completed.returncode}):\n{output}"
    )
    assert not (completed.returncode == 2 and "Usage:" in output), f"{argv} exited 2 with usage:\n{output}"
