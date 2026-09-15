"""#2379 — the Auto permission mode: registry flags, spawn argv, and refusals.

The per-provider flags asserted here were verified against the installed CLIs
on 2026-09-14 (``claude`` 2.1.210, ``codex`` 0.154.0, ``kimi`` 0.42.0) and,
for Qoder, against its published permissions page; the registry comments
record each source.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scistudio.ai.agent import terminal
from scistudio.ai.agent.providers_registry import (
    PERMISSION_MODES,
    REGISTRY,
    ProviderDescriptor,
    get,
)
from scistudio.ai.work_import.context import PERMISSION_MODES as WORK_IMPORT_PERMISSION_MODES
from scistudio.engine.pty_control import PtyTabSpec


@pytest.fixture
def spawned_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Capture the argv ``spawn_agent`` hands to :class:`PtyProcess`."""
    captured: list[list[str]] = []

    class _FakePty:
        def __init__(self, argv: list[str], cwd: Path, **_: object) -> None:
            captured.append(list(argv))

    monkeypatch.setattr(terminal, "PtyProcess", _FakePty)
    monkeypatch.setattr(terminal, "_resolve_agent_binary", lambda _descriptor: "agent")
    return captured


def _without_auto(key: str) -> ProviderDescriptor:
    return dataclasses.replace(get(key), auto_argv=(), auto_argv_absent_reason="fixture: no auto mode")


EXPECTED_AUTO_ARGV = {
    # `claude --help` at 2.1.210 lists `auto` among --permission-mode choices.
    "claude-code": ("--permission-mode", "auto"),
    # `codex --approve-for-me -a on-request --help` exits 0 at 0.154.0.
    "codex": ("--approve-for-me", "--ask-for-approval", "on-request"),
    # kimi 0.42.0: -y/--yolo is "Ask When Needed"; --auto is "Never Ask" (bypass).
    "kimi-code": ("--yolo",),
    # docs.qoder.com/en/cli/permissions: `--permission-mode auto`.
    "qoder": ("--permission-mode", "auto"),
    "qoder-cn": ("--permission-mode", "auto"),
}


def test_the_permission_mode_value_set_is_shared() -> None:
    assert PERMISSION_MODES == ("safe", "auto", "bypass")
    assert WORK_IMPORT_PERMISSION_MODES == PERMISSION_MODES
    assert "auto" in PtyTabSpec.__annotations__["permission_mode"]


def test_every_agent_has_an_expected_auto_argv_row() -> None:
    assert set(EXPECTED_AUTO_ARGV) == set(REGISTRY.agent_keys())


@pytest.mark.parametrize(("provider", "expected"), sorted(EXPECTED_AUTO_ARGV.items()))
def test_registry_records_each_providers_auto_flag(provider: str, expected: tuple[str, ...]) -> None:
    descriptor = get(provider)
    assert descriptor.auto_argv == expected
    assert descriptor.supports_auto_mode is True
    assert descriptor.permission_argv("auto") == expected


@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_every_agent_declares_an_auto_mode_or_says_why_not(descriptor: ProviderDescriptor) -> None:
    """An empty ``auto_argv`` is a claim about the CLI and must be written down."""
    assert bool(descriptor.auto_argv) != bool(descriptor.auto_argv_absent_reason), descriptor.key


@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_auto_argv_is_distinct_from_manual_and_bypass(descriptor: ProviderDescriptor) -> None:
    assert descriptor.auto_argv != descriptor.manual_argv
    assert descriptor.auto_argv != descriptor.bypass_argv


@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_safe_and_bypass_mapping_is_unchanged(descriptor: ProviderDescriptor) -> None:
    assert descriptor.permission_argv("safe") == descriptor.manual_argv
    assert descriptor.permission_argv("bypass") == descriptor.bypass_argv


def test_codex_manual_no_longer_passes_the_retired_untrusted_policy() -> None:
    """codex 0.149.0 retired ``-a untrusted``; passing it made Manual exit 2."""
    manual = get("codex").manual_argv
    assert "untrusted" not in manual
    assert manual == ("--ask-for-approval", "on-request", "--sandbox", "read-only")


def test_kimi_yolo_is_auto_and_kimi_auto_is_bypass() -> None:
    """Kimi's flag names run opposite to the picker's labels."""
    kimi = get("kimi-code")
    assert kimi.auto_argv == ("--yolo",)
    assert kimi.bypass_argv == ("--auto",)


def test_permission_argv_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="permission mode must be one of"):
        get("claude-code").permission_argv("dangerous")


def test_permission_argv_rejects_auto_without_an_auto_mode() -> None:
    descriptor = _without_auto("claude-code")
    assert descriptor.supports_auto_mode is False
    with pytest.raises(ValueError, match="Claude Code has no Auto permission mode"):
        descriptor.permission_argv("auto")


@pytest.mark.parametrize("descriptor", REGISTRY.agents(), ids=lambda d: d.key)
def test_auto_spawn_appends_only_the_auto_fragment(
    descriptor: ProviderDescriptor, tmp_path: Path, spawned_argv: list[list[str]]
) -> None:
    terminal.spawn_agent(descriptor, project_dir=tmp_path, dangerous=False, auto=True)

    argv = spawned_argv[0]
    assert argv[-len(descriptor.auto_argv) :] == list(descriptor.auto_argv)
    for token in set(descriptor.bypass_argv) - set(descriptor.auto_argv):
        assert token not in argv, f"{descriptor.key}: auto argv leaked bypass token {token!r}: {argv}"
    for token in set(descriptor.manual_argv) - set(descriptor.auto_argv):
        assert token not in argv, f"{descriptor.key}: auto argv leaked manual token {token!r}: {argv}"


def test_auto_and_dangerous_together_are_refused(tmp_path: Path, spawned_argv: list[list[str]]) -> None:
    with pytest.raises(ValueError, match="both Auto and Yolo/Bypass"):
        terminal.spawn_agent(get("claude-code"), project_dir=tmp_path, dangerous=True, auto=True)
    assert spawned_argv == []


def test_auto_for_a_provider_without_one_is_refused_before_any_side_effect(
    tmp_path: Path, spawned_argv: list[list[str]]
) -> None:
    with pytest.raises(ValueError, match="no Auto permission mode"):
        terminal.spawn_agent(_without_auto("claude-code"), project_dir=tmp_path, dangerous=False, auto=True)
    assert spawned_argv == []
    # Claude Code is FLAG_FILE, so a late refusal would have left a prompt file.
    assert not list(tmp_path.rglob("scistudio-prompt-*"))


@pytest.mark.parametrize(
    ("dangerous", "auto", "mode"),
    [(False, False, "safe"), (False, True, "auto"), (True, False, "bypass")],
)
def test_permission_mode_from_flags(dangerous: bool, auto: bool, mode: str) -> None:
    assert terminal.permission_mode_from_flags(dangerous=dangerous, auto=auto) == mode
