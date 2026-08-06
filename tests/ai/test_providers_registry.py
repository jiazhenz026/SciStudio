"""ADR-034 multi-provider registry tests (issue #1994, spec T-001/T-003/T-004).

Three families live here:

* **Registry completeness** — an incomplete future descriptor must fail at test
  time, not at spawn time (spec §4.4). These assertions iterate the registry
  rather than naming providers, so a sixth provider is covered the moment it is
  added.
* **Argv snapshots** — one provider's flag spelling must never appear in
  another provider's argv.
* **MCP injection strategies** — including the merge-preserving write into the
  provider-owned ``<project>/.kimi-code/mcp.json`` (FR-017a/FR-017b).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from scistudio.ai.agent import providers_registry as registry
from scistudio.ai.agent import terminal
from scistudio.ai.agent.providers_registry import (
    McpStrategy,
    ProviderDescriptor,
    ProviderKind,
    SystemPromptStrategy,
)
from scistudio.cli import install

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePtyProcess:
    """Records the argv a spawn would have used without starting a process."""

    last: ClassVar[dict[str, Any]] = {}

    def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
        type(self).last = {"argv": argv, "args": args, "kwargs": kwargs}


def _spawn_argv(
    monkeypatch: pytest.MonkeyPatch,
    descriptor: ProviderDescriptor,
    project_dir: Path,
    *,
    dangerous: bool = True,
    prompt: str = "",
) -> list[str]:
    """Build the argv ``spawn_agent`` would use, with no real subprocess."""
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    # Pin binary resolution so the result does not depend on which CLIs happen
    # to be installed on the machine running the suite.
    monkeypatch.setattr(
        terminal,
        "resolve_binary",
        lambda desc, **_kwargs: Path(f"/fake/bin/{desc.binary_candidates[0]}"),
    )
    monkeypatch.setattr(
        terminal,
        "_write_system_prompt_tempfile",
        lambda pd: pd / "prompt.md",
    )
    terminal.spawn_agent(
        descriptor,
        project_dir=project_dir,
        dangerous=dangerous,
        prompt=prompt,
    )
    argv = _FakePtyProcess.last["argv"]
    assert isinstance(argv, list)
    return argv


def _declared_flags(descriptor: ProviderDescriptor) -> set[str]:
    """Flags a descriptor is *entitled* to emit."""
    flags = set(descriptor.bypass_argv)
    if descriptor.mcp.strategy is McpStrategy.FLAG and descriptor.mcp.flag:
        flags.add(descriptor.mcp.flag)
    if descriptor.system_prompt.strategy is SystemPromptStrategy.FLAG_FILE and descriptor.system_prompt.flag:
        flags.add(descriptor.system_prompt.flag)
    return flags


AGENTS = registry.agent_descriptors()


def _fake_binary(name: str) -> str:
    """Platform-native spelling of the stub binary path used in snapshots."""
    return str(Path(f"/fake/bin/{name}"))


# ---------------------------------------------------------------------------
# T-001: registry shape and completeness
# ---------------------------------------------------------------------------


def test_registry_order_is_the_frozen_cross_agent_contract() -> None:
    assert registry.agent_keys() == ("claude-code", "codex", "kimi-code", "qoder", "qoder-cn")
    assert registry.provider_keys() == (
        "claude-code",
        "codex",
        "kimi-code",
        "qoder",
        "qoder-cn",
        "user-terminal",
    )


def test_agent_keys_excludes_the_terminal_pseudo_provider() -> None:
    """FR-003: status and the Setup dropdown list only agent providers."""
    assert "user-terminal" not in registry.agent_keys()
    assert registry.get("user-terminal").kind is ProviderKind.TERMINAL
    assert all(d.kind is ProviderKind.AGENT for d in registry.agent_descriptors())


def test_get_rejects_unknown_provider_and_enumerates_the_accepted_set() -> None:
    """FR-023: the rejection message must name what is accepted."""
    with pytest.raises(KeyError) as excinfo:
        registry.get("gemini-cli")
    message = str(excinfo.value)
    for key in registry.provider_keys():
        assert key in message


@pytest.mark.parametrize("descriptor", AGENTS, ids=lambda d: d.key)
def test_agent_descriptor_is_a_complete_adapter_definition(descriptor: ProviderDescriptor) -> None:
    """FR-002: an incomplete provider must fail here, not at spawn time."""
    assert descriptor.key
    assert descriptor.label and descriptor.label != descriptor.key
    assert descriptor.kind is ProviderKind.AGENT
    assert descriptor.binary_candidates, "an agent must declare at least one binary name"
    assert all(name and not name.endswith(".exe") for name in descriptor.binary_candidates)
    assert descriptor.well_known_dirs, "an agent must declare a well-known install dir"
    assert descriptor.config_root, "an agent must declare a config root"
    assert descriptor.bypass_argv, "an agent must declare its own bypass-permission argv"

    assert descriptor.mcp.strategy is not McpStrategy.NONE
    if descriptor.mcp.strategy is McpStrategy.FLAG:
        assert descriptor.mcp.flag, "a flag strategy must name its flag"
    if descriptor.mcp.strategy is McpStrategy.PROJECT_FILE:
        assert descriptor.mcp.project_file, "a project-file strategy must name its file"

    if descriptor.system_prompt.strategy is SystemPromptStrategy.FLAG_FILE:
        assert descriptor.system_prompt.flag
        assert descriptor.system_prompt.supports_file_indirection
    else:
        # Ambient providers must be discoverable through a provisioned skills
        # tree, otherwise the composed prompt never reaches them (FR-019).
        assert descriptor.system_prompt.skill_dirs
        if descriptor.system_prompt.flag:
            # A provider with a prompt flag that is nonetheless ambient must
            # record why, so the choice is not mistaken for an oversight.
            assert descriptor.system_prompt.ambient_only_reason

    assert descriptor.credentials is not None
    assert descriptor.credentials.credential_path


def test_registry_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="duplicate provider key"):
        registry.ProviderRegistry((registry.get("codex"), registry.get("codex")))


def test_registry_module_does_not_import_api_or_blocks() -> None:
    """Spec §4.1: the registry must stay a leaf both layers can depend on.

    ``import-linter`` forbids ``scistudio.ai -> scistudio.api`` repo-wide but
    not ``scistudio.ai -> scistudio.blocks``, and a lazy function-body import
    would slip past a module-level check, so parse the source instead.
    """
    source = Path(registry.__file__).read_text(encoding="utf-8")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    for name in imported:
        assert not name.startswith("scistudio.api"), name
        assert not name.startswith("scistudio.blocks"), name


# ---------------------------------------------------------------------------
# FR-025 / FR-026: Qoder channels
# ---------------------------------------------------------------------------


def test_qoder_channels_are_two_independent_descriptors() -> None:
    intl = registry.get("qoder")
    china = registry.get("qoder-cn")

    assert intl is not china
    assert intl.key != china.key
    assert intl.label != china.label
    # FR-026: a channel is never an alternative binary candidate of the other.
    assert intl.binary_candidates == ("qodercli",)
    assert china.binary_candidates == ("qoderclicn",)
    assert not set(intl.binary_candidates) & set(china.binary_candidates)
    assert intl.config_root != china.config_root
    assert intl.well_known_dirs != china.well_known_dirs


def test_qoder_channels_share_every_strategy_field() -> None:
    """FR-025: the pair differs only in identity fields.

    This is the clearest demonstration that the registry is a descriptor table
    rather than a branch chain — if these ever diverge it must be because the
    CLIs diverged, not because the code duplicated a strategy.
    """
    intl = registry.get("qoder")
    china = registry.get("qoder-cn")

    assert intl.mcp == china.mcp
    assert intl.system_prompt == china.system_prompt
    assert intl.bypass_argv == china.bypass_argv
    assert intl.credentials == china.credentials
    assert intl.kind == china.kind


def test_qoder_prompt_flag_is_declared_but_never_used() -> None:
    """Spec §4.1: ``--append-system-prompt`` takes literal text on Qoder.

    The composed SciStudio prompt is unbounded, so it would land on the command
    line. Both channels receive it through ``.agents/skills`` like Codex.
    """
    for key in ("qoder", "qoder-cn"):
        descriptor = registry.get(key)
        assert descriptor.system_prompt.strategy is SystemPromptStrategy.AMBIENT
        assert descriptor.system_prompt.supports_file_indirection is False
        assert ".agents/skills" in descriptor.system_prompt.skill_dirs
        assert descriptor.system_prompt.ambient_only_reason


# ---------------------------------------------------------------------------
# Config root resolution (FR-002 environment overrides)
# ---------------------------------------------------------------------------


def test_kimi_config_root_honours_kimi_code_home(tmp_path: Path) -> None:
    """Kimi's own docs instruct callers never to assume ``~/.kimi-code``."""
    kimi = registry.get("kimi-code")
    home = tmp_path / "home"
    override = tmp_path / "elsewhere" / "kimi"

    assert kimi.resolve_config_root(home=home, env={}) == home / ".kimi-code"
    assert kimi.resolve_config_root(home=home, env={"KIMI_CODE_HOME": str(override)}) == override
    # The install dir and the credential probe both follow the override.
    assert kimi.well_known_directories(home=home, env={"KIMI_CODE_HOME": str(override)}) == (override / "bin",)
    assert (
        kimi.credential_file(home=home, env={"KIMI_CODE_HOME": str(override)})
        == override / "credentials" / "kimi-code.json"
    )


def test_qoder_channels_resolve_separate_config_roots_and_credentials(tmp_path: Path) -> None:
    home = tmp_path / "home"
    intl = registry.get("qoder")
    china = registry.get("qoder-cn")

    assert intl.credential_file(home=home, env={}) == home / ".qoder" / ".auth"
    assert china.credential_file(home=home, env={}) == home / ".qoder-cn" / ".auth"


def test_user_terminal_declares_no_agent_adapter_surface() -> None:
    shell = registry.get("user-terminal")
    assert shell.kind is ProviderKind.TERMINAL
    assert shell.binary_candidates == ()
    assert shell.mcp.strategy is McpStrategy.NONE
    assert shell.credentials is None
    assert shell.bypass_argv == ()


# ---------------------------------------------------------------------------
# T-003: argv snapshots, one per provider
# ---------------------------------------------------------------------------


def test_spawn_agent_rejects_the_terminal_pseudo_provider(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires an agent provider"):
        terminal.spawn_agent(registry.get("user-terminal"), project_dir=tmp_path, dangerous=False)


def test_claude_argv_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    argv = _spawn_argv(monkeypatch, registry.get("claude-code"), tmp_path)
    assert argv == [
        _fake_binary("claude"),
        "--append-system-prompt",
        f"@{tmp_path / 'prompt.md'}",
        "--mcp-config",
        str(tmp_path / ".scistudio" / "mcp.json"),
        "--dangerously-skip-permissions",
    ]


def test_codex_argv_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    argv = _spawn_argv(monkeypatch, registry.get("codex"), tmp_path)
    assert argv[0] == _fake_binary("codex")
    assert argv[-1] == "--dangerously-bypass-approvals-and-sandbox"
    assert argv.count("-c") == 3
    assert any(arg.startswith("mcp_servers.scistudio.command=") for arg in argv)
    # Codex has no system-prompt flag and no --mcp-config.
    assert "--append-system-prompt" not in argv
    assert "--mcp-config" not in argv


def test_kimi_argv_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    argv = _spawn_argv(monkeypatch, registry.get("kimi-code"), tmp_path)
    assert argv == [_fake_binary("kimi"), "--auto"]
    # FR-017: the MCP entry reaches Kimi through its own project-scope file.
    assert (tmp_path / ".kimi-code" / "mcp.json").is_file()


@pytest.mark.parametrize(
    ("key", "binary"),
    [("qoder", "qodercli"), ("qoder-cn", "qoderclicn")],
)
def test_qoder_argv_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, key: str, binary: str) -> None:
    argv = _spawn_argv(monkeypatch, registry.get(key), tmp_path)
    assert argv == [
        _fake_binary(binary),
        "--mcp-config",
        str(tmp_path / ".scistudio" / "mcp.json"),
        "--dangerously-skip-permissions",
    ]


@pytest.mark.parametrize("descriptor", AGENTS, ids=lambda d: d.key)
def test_no_foreign_provider_flag_appears_in_an_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    descriptor: ProviderDescriptor,
) -> None:
    """Spec §4.4: no provider's flag spelling may leak into another's argv.

    ``--dangerously-skip-permissions`` inside a Codex argv is a failure. Flags
    genuinely shared by two providers (Claude Code and Qoder both use
    ``--mcp-config``) are excluded per provider by :func:`_declared_flags`, so
    the check stays exact rather than merely "different".
    """
    own = _declared_flags(descriptor)
    foreign = {flag for other in AGENTS if other.key != descriptor.key for flag in _declared_flags(other)} - own
    assert foreign, "the test would be vacuous if every provider shared every flag"

    argv = _spawn_argv(monkeypatch, descriptor, tmp_path)
    leaked = sorted(foreign & set(argv))
    assert leaked == [], f"{descriptor.key} argv leaked foreign flags: {leaked}"


@pytest.mark.parametrize("descriptor", AGENTS, ids=lambda d: d.key)
def test_bypass_flags_are_omitted_in_manual_approve_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    descriptor: ProviderDescriptor,
) -> None:
    argv = _spawn_argv(monkeypatch, descriptor, tmp_path, dangerous=False)
    for flag in descriptor.bypass_argv:
        assert flag not in argv


@pytest.mark.parametrize("descriptor", AGENTS, ids=lambda d: d.key)
def test_prompt_is_positional_after_an_end_of_options_separator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    descriptor: ProviderDescriptor,
) -> None:
    """#1789: the AI Block prompt is the agent's positional argument.

    #1994 narrowed the claim to the providers that *have* a positional prompt.
    Kimi Code does not — its first positional is parsed as a subcommand, so
    appending one made it exit 1 — and it now declares that in the registry
    instead of being handed an argument it cannot parse.
    """
    if descriptor.prompt_argv_prefix is None:
        pytest.skip(f"{descriptor.key} has no positional prompt: {descriptor.prompt_unsupported_reason}")
    argv = _spawn_argv(monkeypatch, descriptor, tmp_path, prompt="do the task")
    assert argv[-2:] == ["--", "do the task"]
    if descriptor.mcp.strategy is McpStrategy.FLAG and descriptor.mcp.flag:
        # ``--mcp-config`` is variadic: the separator must sit after its value.
        assert argv.index(descriptor.mcp.flag) < argv.index("--")


@pytest.mark.parametrize("descriptor", AGENTS, ids=lambda d: d.key)
def test_no_prompt_means_no_trailing_separator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    descriptor: ProviderDescriptor,
) -> None:
    assert "--" not in _spawn_argv(monkeypatch, descriptor, tmp_path)


def test_only_flag_file_providers_write_a_system_prompt_tempfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A prompt file nothing consumes is an orphaned-file leak (FR-013)."""
    for descriptor in AGENTS:
        project_dir = tmp_path / descriptor.key
        project_dir.mkdir()
        _spawn_argv(monkeypatch, descriptor, project_dir)
        cleanup = _FakePtyProcess.last["kwargs"]["cleanup_paths"]
        if descriptor.system_prompt.strategy is SystemPromptStrategy.FLAG_FILE:
            assert cleanup == [project_dir / "prompt.md"]
        else:
            assert cleanup == []


# ---------------------------------------------------------------------------
# T-004: MCP injection strategies
# ---------------------------------------------------------------------------


def _read_servers(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data["mcpServers"]
    assert isinstance(servers, dict)
    return servers


def test_kimi_mcp_write_preserves_the_users_own_servers(tmp_path: Path) -> None:
    """FR-017a: ``.kimi-code/mcp.json`` is Kimi's file, not SciStudio's.

    Reusing the clobbering ``_ensure_mcp_config`` here would silently delete
    MCP servers the user registered themselves, with no recovery path.
    """
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    seeded = {
        "mcpServers": {
            "user-owned": {"command": "my-server", "args": ["--serve"], "env": {"TOKEN": "keep-me"}},
        },
        "someOtherTopLevelKey": {"kept": True},
    }
    config_path.write_text(json.dumps(seeded, indent=2), encoding="utf-8")

    written = terminal._merge_provider_mcp_config(kimi, tmp_path)

    assert written == config_path
    data = json.loads(config_path.read_text(encoding="utf-8"))
    servers = data["mcpServers"]
    assert servers["user-owned"] == seeded["mcpServers"]["user-owned"]
    assert data["someOtherTopLevelKey"] == {"kept": True}
    assert set(servers) == {"user-owned", "scistudio"}
    assert servers["scistudio"]["args"][-1] == "mcp-bridge"


def test_kimi_mcp_write_refuses_to_overwrite_a_malformed_file(tmp_path: Path) -> None:
    """FR-017b: a malformed provider-owned file must raise, never be replaced."""
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    original = '{"mcpServers": {"user-owned": {  <-- hand-edited, trailing junk'
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        terminal._merge_provider_mcp_config(kimi, tmp_path)

    message = str(excinfo.value)
    assert str(config_path) in message
    assert "Kimi Code" in message
    assert config_path.read_text(encoding="utf-8") == original


def test_kimi_mcp_write_refuses_a_non_object_document(tmp_path: Path) -> None:
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(RuntimeError, match="non-object JSON"):
        terminal._merge_provider_mcp_config(kimi, tmp_path)
    assert config_path.read_text(encoding="utf-8") == "[1, 2, 3]"


@pytest.mark.parametrize(
    ("servers_literal", "type_name"),
    [('"stdio"', "str"), ("[1, 2]", "list"), ("7", "int")],
)
def test_kimi_mcp_write_refuses_a_non_object_mcp_servers_value(
    tmp_path: Path,
    servers_literal: str,
    type_name: str,
) -> None:
    """FR-017a: the merge may change only the SciStudio server entry.

    A parseable document whose ``mcpServers`` is not an object is the quietest
    destructive case: coercing it to a fresh ``{}`` would drop a key SciStudio
    does not own with no error and no trace. It must raise like the malformed
    and non-object-document cases, and leave the file byte-for-byte intact.
    """
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    original = f'{{"mcpServers": {servers_literal}, "otherKey": {{"kept": true}}}}'
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        terminal._merge_provider_mcp_config(kimi, tmp_path)

    message = str(excinfo.value)
    assert "mcpServers" in message
    assert type_name in message
    assert str(config_path) in message
    assert "Kimi Code" in message
    assert config_path.read_text(encoding="utf-8") == original


def test_kimi_mcp_write_accepts_a_document_without_an_mcp_servers_key(tmp_path: Path) -> None:
    """A missing key is not a wrong key: it is created and other keys survive."""
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"otherKey": {"kept": True}}), encoding="utf-8")

    terminal._merge_provider_mcp_config(kimi, tmp_path)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["otherKey"] == {"kept": True}
    assert set(data["mcpServers"]) == {"scistudio"}


def test_kimi_mcp_write_creates_the_file_when_absent(tmp_path: Path) -> None:
    kimi = registry.get("kimi-code")
    written = terminal._merge_provider_mcp_config(kimi, tmp_path)
    assert written == tmp_path / ".kimi-code" / "mcp.json"
    assert set(_read_servers(written)) == {"scistudio"}


def test_kimi_mcp_write_treats_an_empty_file_as_absent(tmp_path: Path) -> None:
    """An empty file carries no user content, so there is nothing to preserve."""
    kimi = registry.get("kimi-code")
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("   \n", encoding="utf-8")

    terminal._merge_provider_mcp_config(kimi, tmp_path)
    assert set(_read_servers(config_path)) == {"scistudio"}


def test_kimi_mcp_write_is_idempotent(tmp_path: Path) -> None:
    kimi = registry.get("kimi-code")
    first = terminal._merge_provider_mcp_config(kimi, tmp_path).read_text(encoding="utf-8")
    second = terminal._merge_provider_mcp_config(kimi, tmp_path).read_text(encoding="utf-8")
    assert first == second


# ---------------------------------------------------------------------------
# Concurrency: the read half of the Windows busy-file defect
# ---------------------------------------------------------------------------


def _seed_kimi_config(tmp_path: Path, body: str) -> Path:
    config_path = tmp_path / ".kimi-code" / "mcp.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _fail_reads_of(
    monkeypatch: pytest.MonkeyPatch,
    target: Path,
    *,
    times: int,
    error: BaseException,
) -> dict[str, int]:
    """Make the first *times* reads of *target* raise *error*.

    Only that one path is affected; every other read (the MCP payload helpers
    consult the filesystem too) delegates to the real implementation, so the
    stub cannot mask an unrelated failure.
    """
    original = Path.read_text
    state = {"reads": 0}

    def patched(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == target:
            state["reads"] += 1
            if state["reads"] <= times:
                raise error
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", patched)
    return state


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture the backoff schedule without actually waiting for it."""
    slept: list[float] = []
    monkeypatch.setattr(terminal.time, "sleep", slept.append)
    return slept


def test_kimi_mcp_read_retries_while_the_file_is_busy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A transiently busy read must not fail the launch.

    On Windows a concurrent writer's ``os.replace`` makes the destination
    briefly unopenable, and ``open()`` does not pass ``FILE_SHARE_DELETE``, so
    an innocent reader gets ``PermissionError``. Measured with 240 overlapping
    merges against one file, this accounted for every residual failure once the
    write-side fix had landed.
    """
    kimi = registry.get("kimi-code")
    config_path = _seed_kimi_config(
        tmp_path,
        json.dumps({"mcpServers": {"user-owned": {"command": "x", "args": []}}}),
    )
    state = _fail_reads_of(monkeypatch, config_path, times=2, error=PermissionError("busy"))
    slept = _record_sleeps(monkeypatch)

    terminal._merge_provider_mcp_config(kimi, tmp_path)

    assert state["reads"] == 3, "the read should have been retried until it succeeded"
    # The schedule is A2's, imported rather than restated, so the two halves of
    # one defect cannot drift to different budgets.
    assert slept == list(install._REPLACE_RETRY_DELAYS[:2])
    # The merge still did its real job.
    servers = _read_servers(config_path)
    assert set(servers) == {"user-owned", "scistudio"}


def test_kimi_mcp_read_raises_when_the_file_stays_busy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A persistently busy read must surface, never be swallowed.

    Spending the budget and then giving up silently would be the failure mode
    the write-side fix exists to remove: an agent launched with no SciStudio
    tools and nothing telling the user why.
    """
    kimi = registry.get("kimi-code")
    original = '{"mcpServers": {"user-owned": {"command": "x"}}}'
    config_path = _seed_kimi_config(tmp_path, original)
    state = _fail_reads_of(monkeypatch, config_path, times=1000, error=PermissionError("still busy"))
    slept = _record_sleeps(monkeypatch)

    with pytest.raises(PermissionError, match="still busy"):
        terminal._merge_provider_mcp_config(kimi, tmp_path)

    # Every delay is spent, then one final unguarded attempt.
    assert slept == list(install._REPLACE_RETRY_DELAYS)
    assert state["reads"] == len(install._REPLACE_RETRY_DELAYS) + 1
    # ``read_bytes`` deliberately, so the assertion does not go through the
    # still-patched ``read_text`` it is checking the aftermath of.
    assert config_path.read_bytes().decode("utf-8") == original


def test_kimi_mcp_read_does_not_retry_a_permanent_os_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Only ``PermissionError`` is transient; the rest must fail fast.

    Waiting out an ``IsADirectoryError`` or a real I/O error cannot change the
    outcome, so burning the retry budget on it would only delay the report.
    """
    kimi = registry.get("kimi-code")
    config_path = _seed_kimi_config(tmp_path, "{}")
    state = _fail_reads_of(monkeypatch, config_path, times=1000, error=OSError("device is gone"))
    slept = _record_sleeps(monkeypatch)

    with pytest.raises(OSError, match="device is gone"):
        terminal._merge_provider_mcp_config(kimi, tmp_path)

    assert state["reads"] == 1, "a permanent OSError must raise on the first attempt"
    assert slept == []


def test_a_corrupt_file_is_refused_immediately_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A busy file and a corrupt file must stay separate code paths.

    Retrying malformed JSON would delay an error that no amount of waiting can
    clear, and — worse — blurring the two would invite a future "give up and
    overwrite" fallback on the path that must never overwrite (FR-017b).
    """
    kimi = registry.get("kimi-code")
    original = '{"mcpServers": {  <-- hand-edited'
    config_path = _seed_kimi_config(tmp_path, original)
    slept = _record_sleeps(monkeypatch)

    with pytest.raises(RuntimeError, match="malformed JSON"):
        terminal._merge_provider_mcp_config(kimi, tmp_path)

    assert slept == [], "a corrupt file must not be retried"
    assert config_path.read_text(encoding="utf-8") == original


def test_mcp_payload_is_identical_across_every_injection_strategy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FR-018: only the write location and mechanism differ per provider."""
    from scistudio.cli.install import _mcp_entry_payload

    flag_project = tmp_path / "flag"
    flag_project.mkdir()
    _spawn_argv(monkeypatch, registry.get("claude-code"), flag_project)
    flag_entry = _read_servers(flag_project / ".scistudio" / "mcp.json")["scistudio"]

    file_project = tmp_path / "file"
    file_project.mkdir()
    _spawn_argv(monkeypatch, registry.get("kimi-code"), file_project)
    file_entry = _read_servers(file_project / ".kimi-code" / "mcp.json")["scistudio"]

    assert flag_entry == _mcp_entry_payload(flag_project)
    assert file_entry == _mcp_entry_payload(file_project)
    # Same shape, differing only in the project dir each was anchored at.
    assert flag_entry["command"] == file_entry["command"]
    assert flag_entry["args"] == file_entry["args"]
