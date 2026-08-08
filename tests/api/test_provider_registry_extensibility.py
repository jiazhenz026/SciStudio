"""ADR-034 User Story 7 — adding a sixth provider costs one registry row.

Spec §2 User Story 7 states the Independent Test verbatim:

    add a fixture provider descriptor in a test and assert it appears in
    ``_VALID_PROVIDERS``, ``/api/ai/status``, the AI Block config enum, and the
    frontend provider list without any other source edit.

Everything else in this change is machinery *for* that promise. Without this
test User Story 7 is an aspiration: each consumer has its own test proving it is
registry-derived today, but nothing proves the four of them stay in step when a
descriptor is genuinely added, which is the only event that matters.

**Why the modules are re-executed.** Two of the four consumers snapshot the
registry at import time — ``_state._VALID_PROVIDERS`` /
``_state._PROVIDER_SPAWNERS`` are module-level, and ``AIBlock.config_schema`` is
a ``ClassVar`` evaluated at class definition. That is correct for a process
where the registry is a static table, but it means a test that only patched
``REGISTRY`` would silently prove nothing about them. Re-executing the module
source is what makes the assertion real: it replays exactly what a fresh
interpreter does after the registry file gains a row. ``/api/ai/status`` reads
``agent_descriptors()`` per request and needs no replay, which is itself worth
pinning.

**Why not ``importlib.reload``.** Reloading in place is the obvious approach and
is wrong here. ``api/routes/ai_pty/__init__.py`` does
``from ._state import _active_ptys``, binding the live PTY registry *object* at
its own import time; reloading ``_state`` rebinds that name to a fresh ``dict``
while every other importer keeps pointing at the original, so the API package
and the module it re-exports from stop sharing state. Nothing in this file would
notice, but the next test to open a PTY would — the failure lands somewhere else
entirely, which is the worst kind. Loading an independent module object from the
same source keeps ``sys.modules`` untouched and cannot alias anything.

The frontend half of this story lives in
``frontend/src/components/AIChat/__tests__/ProviderExtensibility.test.tsx``:
the picker is driven by the status payload, so the assertion there is that a
provider key the frontend has never heard of renders from the payload alone.
The two halves meet at the payload this module asserts.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent import providers_registry as registry
from scistudio.ai.agent.providers_registry import (
    CredentialProbe,
    McpInjection,
    McpStrategy,
    ProviderDescriptor,
    ProviderKind,
    ProviderRegistry,
    SystemPromptInjection,
    SystemPromptStrategy,
)

#: A sixth provider that exists only for the duration of this module.
#:
#: Deliberately spelled out in full rather than cloned from an existing
#: descriptor: the point of the exercise is that a maintainer writing one of
#: these from scratch, touching no other file, gets a working provider. Its
#: strategy fields are the two most common shapes (``--mcp-config`` flag,
#: ambient skills discovery) so it exercises real code paths rather than a
#: degenerate one.
FIXTURE = ProviderDescriptor(
    key="fixture-agent",
    label="Fixture Agent CLI",
    kind=ProviderKind.AGENT,
    binary_candidates=("fixtureagent",),
    well_known_dirs=((".fixture-agent", "bin"),),
    config_root=(".fixture-agent",),
    config_root_env=None,
    mcp=McpInjection(strategy=McpStrategy.FLAG, flag="--mcp-config"),
    system_prompt=SystemPromptInjection(
        strategy=SystemPromptStrategy.AMBIENT,
        skill_dirs=(".agents/skills",),
    ),
    credentials=CredentialProbe(credential_path=(".auth",)),
    bypass_argv=("--fixture-bypass",),
)

#: Modules that snapshot the registry at import time and must be replayed.
#:
#: Both import only absolutely, so a standalone execution of their source needs
#: no package context beyond what ``sys.modules`` already holds.
_IMPORT_TIME_CONSUMERS = (
    "scistudio.api.routes.ai_pty._state",
    "scistudio.blocks.ai.ai_block",
)


def _reexecute(canonical: ModuleType, dotted_name: str) -> ModuleType:
    """Execute *canonical*'s source again as a brand-new module object.

    Deliberately never registered in ``sys.modules`` under its real name: the
    canonical module keeps running, every existing importer keeps its bindings,
    and this copy exists only for the duration of one test. What comes back is
    what a fresh interpreter would have built against the patched registry.
    """
    source = Path(canonical.__file__ or "")
    spec = importlib.util.spec_from_file_location(f"{dotted_name}__us7_replay", source)
    assert spec is not None and spec.loader is not None
    replayed = importlib.util.module_from_spec(spec)
    # Absolute imports only, but ``__package__`` keeps the module well-formed.
    replayed.__package__ = dotted_name.rsplit(".", 1)[0]
    spec.loader.exec_module(replayed)
    return replayed


@pytest.fixture
def sixth_provider() -> Iterator[dict[str, ModuleType]]:
    """Append :data:`FIXTURE` to the registry and replay the import-time consumers.

    Yields the replayed modules keyed by their canonical dotted name. On
    teardown the registry is restored; nothing else needs undoing, because the
    replayed copies were never installed anywhere. Restoration runs even when
    the body fails, since a leaked sixth provider would corrupt every later
    assertion about the registry in ways that are painful to attribute.

    The canonical modules are imported *before* the patch, deliberately. If one
    of them happened to be imported for the first time while the registry was
    patched — which depends on nothing more than test ordering, and
    ``pytest-randomly`` changes that per run — the canonical
    ``AIBlock.config_schema`` would snapshot six providers and keep them for the
    whole session. That is not hypothetical: it is what this fixture did before
    ``test_teardown_leaves_the_canonical_modules_untouched`` caught it.
    """
    canonical = {name: importlib.import_module(name) for name in _IMPORT_TIME_CONSUMERS}
    original = registry.REGISTRY
    registry.REGISTRY = ProviderRegistry((*original.descriptors, FIXTURE))
    try:
        yield {name: _reexecute(module, name) for name, module in canonical.items()}
    finally:
        registry.REGISTRY = original


def test_the_fixture_provider_is_absent_before_it_is_registered() -> None:
    """The control. Without this, every assertion below could be trivially true."""
    assert "fixture-agent" not in registry.provider_keys()
    assert "fixture-agent" not in registry.agent_keys()


def test_registry_derived_views_pick_up_the_sixth_provider(sixth_provider: dict[str, ModuleType]) -> None:
    """The registry's own agent/terminal views extend without an edit (FR-003)."""
    assert registry.agent_keys()[-1] == "fixture-agent"
    assert registry.get("fixture-agent") is FIXTURE
    # It joins the agent view, not the terminal one.
    assert "user-terminal" not in registry.agent_keys()


def test_ws_whitelist_and_spawner_map_pick_up_the_sixth_provider(sixth_provider: dict[str, ModuleType]) -> None:
    """FR-006 / FR-023: ``_VALID_PROVIDERS`` and ``_PROVIDER_SPAWNERS`` extend.

    These were the two hand-maintained literals ADR-034 exists to remove. A
    sixth provider that reached the status endpoint but was rejected by the
    WebSocket whitelist would be listed in the picker and fail on Launch.
    """
    state = sixth_provider["scistudio.api.routes.ai_pty._state"]
    assert "fixture-agent" in state._VALID_PROVIDERS
    assert tuple(state._VALID_PROVIDERS) == registry.provider_keys()
    assert "fixture-agent" in state._PROVIDER_SPAWNERS
    assert set(state._PROVIDER_SPAWNERS) == set(registry.provider_keys())


def test_ai_block_config_enum_picks_up_the_sixth_provider(sixth_provider: dict[str, ModuleType]) -> None:
    """FR-015: the enum widens and the default does not move.

    #2014: the enum is the *capability-filtered* agent set, not every agent
    key — chat-only providers such as ``kimi-code`` are excluded. The fixture
    descriptor keeps the default ``prompt_argv_prefix``, so it is capable and
    still appears with no edit here.
    """
    from scistudio.ai.agent.availability import session_unsupported_reason

    ai_block = sixth_provider["scistudio.blocks.ai.ai_block"]
    provider_schema = ai_block.AIBlock.config_schema["properties"]["provider"]
    capable = [d.key for d in registry.agent_descriptors() if session_unsupported_reason(d) is None]
    assert provider_schema["enum"] == capable
    assert "fixture-agent" in provider_schema["enum"]
    assert provider_schema["default"] == "claude-code"


def test_ai_block_validate_accepts_the_sixth_provider(
    sixth_provider: dict[str, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-014: validation checks against the registry, not a literal set.

    Binary discovery is stubbed because the fixture CLI does not exist; the
    assertion under test is that the *key* is accepted, which is the half a
    hand-maintained list would have got wrong.
    """
    ai_block = sixth_provider["scistudio.blocks.ai.ai_block"]
    monkeypatch.setattr(ai_block, "_discover_provider_binary", lambda _descriptor: "/fake/bin/fixtureagent")
    ai_block.AIBlock().validate_config({"provider": "fixture-agent", "user_prompt": "do the thing"})

    with pytest.raises(ValueError, match="fixture-agent"):
        ai_block.AIBlock().validate_config({"provider": "not-a-provider", "user_prompt": "hi"})


def test_status_endpoint_serves_the_sixth_provider(
    client: TestClient,
    sixth_provider: dict[str, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """FR-008 / FR-020b: a sixth entry appears, with its label, in registry order.

    This is the payload the frontend picker renders, so it is also the seam the
    frontend half of User Story 7 attaches to: the picker never learns the key
    from anywhere else.
    """
    from scistudio.api.routes import ai as ai_routes

    home = tmp_path / "us7_home"
    home.mkdir()
    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    body = client.get("/api/ai/status").json()
    assert [p["name"] for p in body["providers"]] == list(registry.agent_keys())

    entry = next(p for p in body["providers"] if p["name"] == "fixture-agent")
    assert entry == {
        "name": "fixture-agent",
        "available": False,
        "version": None,
        "logged_in": False,
        "label": "Fixture Agent CLI",
    }


def test_the_sixth_provider_spawns_through_the_generic_argv_builder(
    sixth_provider: dict[str, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """FR-007: a descriptor nobody wrote spawn code for still produces argv.

    The strongest form of the User Story 7 claim. If any per-provider spawn
    branch survived, a provider absent from it would either raise or silently
    lose its flags here.
    """
    from scistudio.ai.agent import terminal

    spawned: dict[str, Any] = {}

    class _FakePty:
        def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
            spawned["argv"] = argv

    monkeypatch.setattr(terminal, "PtyProcess", _FakePty)
    monkeypatch.setattr(terminal, "resolve_binary", lambda desc, **_k: None)

    terminal.spawn_agent(FIXTURE, project_dir=tmp_path, dangerous=True)

    argv = spawned["argv"]
    assert argv[0] == "fixtureagent"
    assert "--mcp-config" in argv
    assert argv[-1] == "--fixture-bypass"
    # No other provider's bypass spelling leaked in from a surviving branch.
    for descriptor in registry.agent_descriptors():
        if descriptor.key == "fixture-agent":
            continue
        assert not set(descriptor.bypass_argv) & set(argv), descriptor.key


def test_teardown_leaves_the_canonical_modules_untouched() -> None:
    """Ordered after the fixture users; a leak here would poison later tests.

    Asserted rather than assumed. Two things could go wrong and neither is
    visible where it happens: the registry could stay patched, or a replayed
    module could have escaped into ``sys.modules`` and started shadowing the
    real one. Both would surface as an unrelated failure much later.
    """
    from scistudio.api.routes import ai_pty
    from scistudio.api.routes.ai_pty import _state
    from scistudio.blocks.ai.ai_block import AIBlock

    assert "fixture-agent" not in registry.provider_keys()
    assert "fixture-agent" not in _state._VALID_PROVIDERS
    assert "fixture-agent" not in _state._PROVIDER_SPAWNERS
    assert "fixture-agent" not in AIBlock.config_schema["properties"]["provider"]["enum"]
    assert not [name for name in sys.modules if name.endswith("__us7_replay")]
    # The PTY registry object the API package re-exports must still be the one
    # ``_state`` owns. An ``importlib.reload`` here would have broken exactly
    # this identity, and nothing in this file would have noticed.
    assert ai_pty._active_ptys is _state._active_ptys
