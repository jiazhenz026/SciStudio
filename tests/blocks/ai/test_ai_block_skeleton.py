"""Tests for AIBlock (ADR-035 §3.1, §3.2, §3.5, §3.6, §3.9) — Phase 2A.

Originally a skeleton (xfail) file; flipped to real tests by I35a per
the test plan in ``ai_block.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.ai.agent import providers_registry
from scistudio.ai.agent.availability import session_unsupported_reason
from scistudio.ai.agent.providers_registry import agent_descriptors, agent_keys
from scistudio.blocks.ai.ai_block import (
    REUSE_LAST_OUTPUT_KEY,
    AIBlock,
    _output_path_overrides,
    _reuse_last_output_enabled,
)
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.state import ExecutionMode
from tests.blocks.ai.conftest import StubAgent  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# ClassVar contract — these can run today (no NotImplementedError).
# ---------------------------------------------------------------------------


def test_ai_block_is_external_mode() -> None:
    """ADR-035 §3.1: AIBlock must declare ExecutionMode.EXTERNAL."""
    assert AIBlock.execution_mode is ExecutionMode.EXTERNAL


def test_ai_block_is_variadic_both_directions() -> None:
    """ADR-035 §3.1: variadic_inputs and variadic_outputs both True."""
    assert AIBlock.variadic_inputs is True
    assert AIBlock.variadic_outputs is True


def test_ai_block_terminate_grace_is_10s() -> None:
    """ADR-035 §3.1: terminate_grace_sec = 10.0."""
    assert AIBlock.terminate_grace_sec == 10.0


def test_ai_block_config_schema_has_required_fields() -> None:
    schema = AIBlock.config_schema
    props = schema["properties"]
    assert "provider" in props
    assert "permission_mode" in props
    assert "user_prompt" in props
    # AIBlock runs without a wall-clock timeout (2026-06 config pass): the
    # ``timeout_sec`` field was removed from the schema.
    assert "timeout_sec" not in props
    assert schema["required"] == ["user_prompt"]


# ---------------------------------------------------------------------------
# FR-012: the worker composes no provider argv at all
# ---------------------------------------------------------------------------


def _config(**kwargs: object) -> BlockConfig:
    return BlockConfig(params=dict(kwargs))


def test_ai_block_no_longer_composes_spawn_argv() -> None:
    """ADR-034 FR-012: the argv builder and its flag table are gone.

    ``_build_spawn_argv`` composed a command line the engine discarded (it
    read only ``argv[0]``), and ``_BYPASS_FLAG`` was a second copy of
    per-provider knowledge that now lives only in the registry. Either
    name reappearing means the duplication is back, and with it the
    orphaned system-prompt file of FR-013.
    """
    from scistudio.blocks.ai import ai_block as mod

    assert not hasattr(AIBlock, "_build_spawn_argv")
    assert not hasattr(mod, "_BYPASS_FLAG")
    assert not hasattr(mod, "_discover_provider")


def test_ai_block_discovery_uses_the_registry_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-005: the block path and the chat path share one resolver.

    The old ``shutil.which`` lookup could never find Kimi Code or either
    Qoder channel — none of them is on PATH — so the block would call a
    provider uninstalled while the chat Setup screen offered it.
    """
    from scistudio.blocks.ai import ai_block as mod

    seen: list[str] = []

    def spy(descriptor: object, **_kw: object) -> Path:
        seen.append(descriptor.key)  # type: ignore[attr-defined]
        return Path("/fake/bin/agent")

    # Patch the registry's own resolver, not a local copy: the assertion is
    # that the block reaches *that* function, so a same-named local stub
    # would prove nothing.
    monkeypatch.setattr(providers_registry, "resolve_binary", spy)
    # #1994: kimi-code is rejected later in validate_config (it has no
    # positional prompt, so it cannot run as an AI Block at all) — but the
    # discovery call this test is about happens first, so the spy still records
    # it. Asserting through the raise keeps the original claim intact.
    with pytest.raises(ValueError, match="cannot run as an AI Block"):
        AIBlock().validate_config(_config(provider="kimi-code", user_prompt="hi"))
    assert seen == ["kimi-code"]
    assert mod._discover_provider_binary(providers_registry.get("qoder-cn")) == Path("/fake/bin/agent")
    assert seen == ["kimi-code", "qoder-cn"]


def test_clear_expected_outputs_removes_stale_files(project_dir: Path) -> None:
    """#1789: leftover declared outputs are cleared before the agent runs, so a
    stale file from a previous run cannot complete the block instantly via the
    FileWatcher path."""
    from scistudio.blocks.ai.ai_block import _clear_expected_outputs

    stale = project_dir / "out.csv"
    stale.write_text("stale output from a previous run", encoding="utf-8")
    _clear_expected_outputs({"out": {"expected_path": "./out.csv", "expected_type": "DataFrame"}}, project_dir)
    assert not stale.exists()


def test_clear_expected_outputs_tolerates_missing_file(project_dir: Path) -> None:
    """A fresh project with no prior output is a no-op, not an error."""
    from scistudio.blocks.ai.ai_block import _clear_expected_outputs

    _clear_expected_outputs({"out": {"expected_path": "./never-written.csv"}}, project_dir)


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


@pytest.fixture()
def _provider_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every registry provider resolve, so tests need no real CLI."""
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider_binary", lambda _d: Path("/fake/bin/agent"))


@pytest.fixture()
def _provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every registry provider resolve to nothing."""
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider_binary", lambda _d: None)


@pytest.mark.parametrize("provider", agent_keys())
def test_validate_succeeds_for_every_registry_provider(provider: str, _provider_installed: None) -> None:
    """FR-014: every agent key in the registry is an accepted provider.

    #1994 added one qualifier. Being in the registry still means the key is
    recognised, but a provider whose CLI has no positional prompt cannot carry
    an AI Block task and is refused here — with its own explanation — rather
    than spawned into a PTY that exits 1.
    """
    from scistudio.ai.agent.providers_registry import get as registry_get

    descriptor = registry_get(provider)
    if descriptor.prompt_argv_prefix is None:
        with pytest.raises(ValueError, match="cannot run as an AI Block") as excinfo:
            AIBlock().validate_config(_config(provider=provider, user_prompt="hi"))
        assert "unknown provider" not in str(excinfo.value)
        return
    AIBlock().validate_config(_config(provider=provider, user_prompt="hi"))


def test_validate_rejects_provider_outside_the_registry(_provider_installed: None) -> None:
    """FR-014: an unknown key is rejected and the accepted set is named."""
    with pytest.raises(ValueError, match="unknown provider") as excinfo:
        AIBlock().validate_config(_config(provider="grok", user_prompt="hi"))
    for key in agent_keys():
        assert key in str(excinfo.value)


@pytest.mark.parametrize("provider", agent_keys())
def test_validate_missing_binary_names_provider_and_binary(provider: str, _provider_missing: None) -> None:
    """FR-014: the error carries the two facts the user can act on."""
    from scistudio.ai.agent.providers_registry import get as registry_get

    descriptor = registry_get(provider)
    with pytest.raises(ValueError) as excinfo:
        AIBlock().validate_config(_config(provider=provider, user_prompt="hi"))
    message = str(excinfo.value)
    assert provider in message
    assert descriptor.label in message
    for candidate in descriptor.binary_candidates:
        assert candidate in message


@pytest.mark.parametrize("provider", agent_keys())
def test_validate_missing_binary_suggests_no_scistudio_install(provider: str, _provider_missing: None) -> None:
    """FR-014: no `scistudio install` hint, in any spelling.

    That command wires SciStudio's MCP server and skills into a CLI the
    user already has — it cannot install the CLI — so following it left
    discovery failing. The old message emitted
    ``scistudio install --target claude-code``, which the install CLI
    rejects outright, so the user got a command that failed twice over.
    """
    with pytest.raises(ValueError) as excinfo:
        AIBlock().validate_config(_config(provider=provider, user_prompt="hi"))
    assert "scistudio install" not in str(excinfo.value)


def test_validate_rejects_empty_prompt(_provider_installed: None) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AIBlock().validate_config(_config(provider="claude-code", user_prompt="   "))


# NOTE: ``test_validate_rejects_negative_timeout`` removed — AIBlock no longer
# has a configurable timeout (runs to completion / cancellation), so there is
# no timeout value to validate.


# ---------------------------------------------------------------------------
# run() — happy paths via StubAgent
# ---------------------------------------------------------------------------


def _prepared_block(
    output_ports: list[dict[str, object]] | None = None,
) -> AIBlock:
    """Construct an AIBlock for direct ``run()`` invocation.

    The worker-side block state machine was removed in #1334; AIBlock no
    longer needs IDLE→READY→RUNNING priming before ``run()``.
    """
    instance_config: dict[str, object] = {}
    if output_ports is not None:
        instance_config["output_ports"] = output_ports
    return AIBlock(config=instance_config)


def test_run_writes_manifest_with_correct_shape(project_dir: Path, stub_agent: StubAgent) -> None:
    """Manifest contains block name, type, deadline, and declared output."""
    stub_agent.outputs = {"metadata": ("results/metadata.csv", "a,b\n1,2\n")}
    block = _prepared_block(
        output_ports=[
            {
                "name": "metadata",
                "types": ["DataFrame"],
                "expected_path": "./results/metadata.csv",
            }
        ]
    )
    cfg = _config(
        user_prompt="extract metadata",
        provider="claude-code",
        timeout_sec=30,
        project_dir=str(project_dir),
        block_id="extract_metadata",
    )
    block.run(inputs={}, config=cfg)

    # Find the run dir created by the block.
    runs_root = project_dir / ".scistudio" / "ai-block-runs"
    run_dirs = list(runs_root.iterdir())
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["block"]["name"] == "extract_metadata"
    assert manifest["block"]["type"] == "AIBlock"
    assert manifest["user_prompt"] == "extract metadata"
    assert "metadata" in manifest["outputs"]
    assert manifest["outputs"]["metadata"]["expected_path"] == "./results/metadata.csv"
    # AIBlock runs without a wall-clock timeout, so no deadline is recorded.
    assert manifest["completion"]["deadline"] is None


def test_run_request_pty_tab_with_safe_permission(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        permission_mode="safe",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    block.run(inputs={}, config=cfg)
    assert len(stub_agent.request_calls) == 1
    spec = stub_agent.request_calls[0]
    assert spec.permission_mode == "safe"
    assert spec.provider == "claude-code"


def test_run_request_pty_tab_with_bypass_permission(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        permission_mode="bypass",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    block.run(inputs={}, config=cfg)
    spec = stub_agent.request_calls[0]
    assert spec.permission_mode == "bypass"
    assert spec.provider == "claude-code"


@pytest.mark.parametrize("provider", agent_keys())
def test_run_carries_the_configured_provider_to_the_engine(
    provider: str,
    project_dir: Path,
    stub_agent: StubAgent,
) -> None:
    """FR-010: the block states its provider; nothing downstream guesses it.

    Parametrised over every registry key because the deleted argv
    inference defaulted anything it did not recognise to ``claude-code``,
    so a per-provider assertion is the only shape that catches a
    regression for the three newly added CLIs.
    """
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider=provider,
        project_dir=str(project_dir),
    )
    block.run(inputs={}, config=cfg)
    assert stub_agent.request_calls[0].provider == provider


def test_run_rejects_a_provider_outside_the_registry(project_dir: Path, stub_agent: StubAgent) -> None:
    """An unknown provider fails the run rather than spawning claude-code."""
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(user_prompt="hi", provider="grok", project_dir=str(project_dir))
    with pytest.raises(ValueError, match="unknown provider"):
        block.run(inputs={}, config=cfg)


def test_run_leaves_no_orphaned_temp_file(project_dir: Path, stub_agent: StubAgent) -> None:
    """ADR-034 FR-013: an AI Block run creates no file nobody deletes.

    ``_build_spawn_argv`` called ``_write_system_prompt_tempfile`` and put
    the path into an argv the engine discarded, so the file under
    ``<project>/.scistudio/.tmp/`` was orphaned on every run: the real
    spawn wrote its own file and ``PtyProcess.kill_tree`` only ever knew
    about that one. Nothing in the system could delete the worker's copy.
    """
    tmp_dir = project_dir / ".scistudio" / ".tmp"
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(user_prompt="hi", provider="claude-code", project_dir=str(project_dir))
    block.run(inputs={}, config=cfg)

    leftovers = sorted(p.name for p in tmp_dir.glob("*")) if tmp_dir.exists() else []
    assert leftovers == [], f"AI Block run left orphaned temp files: {leftovers}"


def test_run_completion_via_mcp_finish_ai_block(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"metadata": ("metadata.csv", "name,value\nfoo,1\n")}
    stub_agent.finish_via = "mcp"
    block = _prepared_block(
        output_ports=[
            {
                "name": "metadata",
                "types": ["DataFrame"],
                "expected_path": "./metadata.csv",
            }
        ]
    )
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    result = block.run(inputs={}, config=cfg)
    assert "metadata" in result
    assert any(n[1] == "completed" for n in stub_agent.notifications)


def test_run_completion_via_file_watcher(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    stub_agent.finish_via = "file_only"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=15,
    )
    result = block.run(inputs={}, config=cfg)
    assert "out" in result


def test_run_completion_via_mark_done_button(project_dir: Path, stub_agent: StubAgent) -> None:
    # The agent produces the output during the run, then the user clicks "Mark
    # done". (#1789: declared outputs are cleared before the agent starts, so the
    # file must be written by the agent during the run — not pre-created before
    # run() — to survive and pass output validation.)
    stub_agent.outputs = {"out": ("out.csv", "a,b\n1,2\n")}
    stub_agent.finish_via = "mark_done"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    result = block.run(inputs={}, config=cfg)
    assert "out" in result


# ---------------------------------------------------------------------------
# run() — error / cancellation paths
# ---------------------------------------------------------------------------


def test_run_validation_fail_returns_error_state(project_dir: Path, stub_agent: StubAgent) -> None:
    """Loader exception → block transitions to ERROR; run_dir preserved."""
    # Stub writes an empty file (size 0). The resulting ValueError differs
    # slightly between Python versions and between entry paths: LoadData on
    # an empty CSV raises ValueError("...is empty"), while the MCP signal
    # parse path raises ValueError("...malformed MCP signal at ...:
    # Expecting value..."). Either is an acceptable failure mode for this
    # skeleton-phase test — both transition the block to ERROR and preserve
    # the run_dir, which is what this test verifies. Relaxing the regex
    # unblocks Python 3.11 CI on docs-only PRs (#909 tracks the proper fix
    # — error-path distinction belongs in src/scistudio/blocks/ai/, not here).
    stub_agent.outputs = {"out": ("out.csv", "")}
    stub_agent.finish_via = "mcp"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(ValueError, match=r"is empty|Expecting value|malformed MCP signal"):
        block.run(inputs={}, config=cfg)
    # Run dir preserved.
    runs_root = project_dir / ".scistudio" / "ai-block-runs"
    assert any(p.is_dir() for p in runs_root.iterdir())


def test_run_spawn_fail_returns_error(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.spawn_error = FileNotFoundError("claude binary gone")
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(RuntimeError, match="PTY spawn failed"):
        block.run(inputs={}, config=cfg)


# NOTE: ``test_run_timeout_cancels`` removed — AIBlock no longer enforces a
# wall-clock timeout (``watcher.wait(timeout_sec=None)``); cancellation now only
# happens via tab close / workflow cancel, covered by the close/cancel cases.


def test_run_malformed_mcp_signal_errors(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.finish_via = "error"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(ValueError, match="malformed MCP signal"):
        block.run(inputs={}, config=cfg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_output_path_overrides_extracts_correctly() -> None:
    cfg = BlockConfig(
        params={
            "output_ports": [
                {"name": "a", "types": ["DataFrame"], "expected_path": "./a.csv"},
                {"name": "b", "types": ["Text"]},  # no expected_path
                "not a dict",  # ignored
            ]
        }
    )
    overrides = _output_path_overrides(cfg)
    assert overrides == {"a": "./a.csv"}


# ---------------------------------------------------------------------------
# T-009 / FR-015 — registry-derived, capability-filtered provider enum
# ---------------------------------------------------------------------------


def _capable_agent_keys() -> list[str]:
    """Registry agent keys that can carry an AI Block task, in order."""
    return [d.key for d in agent_descriptors() if session_unsupported_reason(d) is None]


def test_config_schema_provider_enum_is_registry_derived() -> None:
    """FR-015 + #2014: the enum is exactly the registry's AI-Block-capable
    agent keys, in order.

    Equality rather than containment: a hand-maintained literal that
    happened to include the capable keys plus a stale extra would pass a
    containment check, and User Story 7 requires that adding a sixth
    provider needs no edit here. #2014 narrowed the derivation from every
    agent key to the capability-filtered set, so a chat-only provider can
    never leak into the enum.
    """
    enum = AIBlock.config_schema["properties"]["provider"]["enum"]
    assert enum == _capable_agent_keys()


def test_config_schema_provider_enum_lists_only_capable_agents() -> None:
    """The prompt-capable providers are selectable on the block; #2014:
    ``kimi-code`` is chat-only and must not appear."""
    enum = AIBlock.config_schema["properties"]["provider"]["enum"]
    assert set(enum) == {"claude-code", "codex", "qoder", "qoder-cn"}
    assert "kimi-code" not in enum
    assert "user-terminal" not in enum


def test_config_schema_enum_never_advertises_a_provider_validation_rejects(
    _provider_installed: None,
) -> None:
    """#2014 regression: the schema enum and ``validate_config`` agree.

    The bug was a one-way disagreement — the enum advertised ``kimi-code``
    while validation refused it — so pin both directions: every enum member
    validates, and every registry agent *absent* from the enum is refused
    with the chat-only explanation rather than spawned into a PTY that
    exits 1.
    """
    enum = AIBlock.config_schema["properties"]["provider"]["enum"]
    for provider in enum:
        AIBlock().validate_config(_config(provider=provider, user_prompt="hi"))
    for descriptor in agent_descriptors():
        if descriptor.key in enum:
            continue
        with pytest.raises(ValueError, match="cannot run as an AI Block"):
            AIBlock().validate_config(_config(provider=descriptor.key, user_prompt="hi"))


def test_config_schema_provider_default_is_still_claude_code() -> None:
    """FR-015: widening the enum must not move the default."""
    assert AIBlock.config_schema["properties"]["provider"]["default"] == "claude-code"


def test_existing_claude_code_workflow_config_still_validates(_provider_installed: None) -> None:
    """Enum widening is backward compatible for workflows saved before it.

    A workflow YAML carrying ``provider: claude-code`` — the only value
    most saved workflows have — must load and validate unchanged.
    """
    enum = AIBlock.config_schema["properties"]["provider"]["enum"]
    assert "claude-code" in enum
    AIBlock().validate_config(_config(provider="claude-code", user_prompt="do the thing"))


# ---------------------------------------------------------------------------
# reuse_last_output toggle (#1898 / ADR-035 Addendum 1)
# ---------------------------------------------------------------------------


def test_config_schema_has_reuse_last_output_boolean() -> None:
    """The toggle is a boolean config field so it renders as a checkbox."""
    field = AIBlock.config_schema["properties"]["reuse_last_output"]
    assert field["type"] == "boolean"
    assert field["default"] is False
    # Not required — default off keeps the block's behavior unchanged.
    assert "reuse_last_output" not in AIBlock.config_schema["required"]


def test_reuse_last_output_enabled_reads_flag() -> None:
    assert _reuse_last_output_enabled(_config(reuse_last_output=True)) is True
    assert _reuse_last_output_enabled(_config(reuse_last_output=False)) is False
    # Absent → off (unchanged default behavior).
    assert _reuse_last_output_enabled(_config()) is False
    assert REUSE_LAST_OUTPUT_KEY == "reuse_last_output"


def test_run_reuses_last_output_and_skips_agent(project_dir: Path, stub_agent: StubAgent) -> None:
    """Toggle on + prior output present → re-emit it without spawning the agent."""
    prior = project_dir / "out.csv"
    prior.write_text("a,b\n1,2\n", encoding="utf-8")
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # No PTY tab requested: the agent never ran.
    assert stub_agent.request_calls == []
    # The prior output file was NOT cleared (reuse must leave it intact).
    assert prior.exists()
    # Durable audit marker: the execution's run dir carries reuse.json (and NOT
    # a manifest.json), so an audit can tell a reuse from a genuine agent run.
    runs_root = project_dir / ".scistudio" / "ai-block-runs"
    run_dirs = list(runs_root.iterdir())
    assert len(run_dirs) == 1
    marker = json.loads((run_dirs[0] / "reuse.json").read_text(encoding="utf-8"))
    assert marker["reused_last_output"] is True
    assert marker["outputs"] == {"out": "./out.csv"}
    assert not (run_dirs[0] / "manifest.json").exists()


def test_run_reuse_falls_back_when_no_prior_output(project_dir: Path, stub_agent: StubAgent) -> None:
    """Toggle on but nothing to reuse → fall back to a normal agent run."""
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # Fallback ran the agent: exactly one PTY request.
    assert len(stub_agent.request_calls) == 1


def test_run_reuse_falls_back_when_any_declared_output_missing(project_dir: Path, stub_agent: StubAgent) -> None:
    """Reuse requires every declared output; a partial prior run is a miss."""
    # Only ``a`` exists from a prior run; ``b`` was never produced.
    (project_dir / "a.csv").write_text("x\n1\n", encoding="utf-8")
    stub_agent.outputs = {
        "a": ("a.csv", "x\n1\n"),
        "b": ("b.csv", "y\n2\n"),
    }
    block = _prepared_block(
        output_ports=[
            {"name": "a", "types": ["DataFrame"], "expected_path": "./a.csv"},
            {"name": "b", "types": ["DataFrame"], "expected_path": "./b.csv"},
        ]
    )
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert {"a", "b"} <= set(result)
    # Missing ``b`` forced a real run.
    assert len(stub_agent.request_calls) == 1


def test_run_ignores_prior_output_when_toggle_off(project_dir: Path, stub_agent: StubAgent) -> None:
    """Default (toggle off): a prior output file must not short-circuit the run."""
    (project_dir / "out.csv").write_text("stale\n", encoding="utf-8")
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        # reuse_last_output omitted → defaults off.
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # Agent ran despite the pre-existing file (opt-in only).
    assert len(stub_agent.request_calls) == 1
