"""ADR-034 — the provider survives every hop from AI Block config to the UI.

Spec §4.4 asks for "an end-to-end provider-propagation test for the
engine-initiated path covering all four links, so a future refactor cannot
reintroduce a default at any single hop". FR-020c names the frontend four:
engine emit -> ``handleBlockPty.ts`` -> ``blockPtyHandlers`` -> the store. Those
are covered by ``frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx``
and ``frontend/src/hooks/useWebSocket.test.ts``.

The chain does not start at the engine, though. Before the emit there are three
more hops on the backend, and FR-010 covers them: the AI Block states its
provider, ``PtyTabSpec`` carries it, ``request_pty_tab`` puts it on the IPC wire,
the internal HTTP route reads it back out, and ``open_engine_initiated_tab``
spawns it. Each of those had a test — except the route.

That gap was measured rather than assumed. Replacing
``internal_routes.py``'s ``spec.get("provider", "")`` with a literal
``"claude-code"`` left ``tests/api``, ``tests/engine``, and ``tests/blocks/ai``
entirely green. A hardcoded provider at the exact seam where the worker process
hands off to the API process is the same defect FR-022 removed from the store,
and it would have shipped invisibly. This module closes it, and covers the whole
backend run so the hops are asserted together rather than one at a time — a
chain is only as good as its untested link.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent.providers_registry import agent_keys
from scistudio.ai.agent.terminal import PtyProcess
from scistudio.api.routes import ai_pty
from scistudio.api.routes.ai_pty import (
    _active_ptys,
    _engine_tab_to_run,
    register_ai_pty_subscriber,
    unregister_ai_pty_subscriber,
)

# Real ``PtyProcess`` children, same as ``test_ai_pty_engine_spawn.py``: isolate
# from xdist so a hang or leak cannot take a parallel worker down (#1896).
pytestmark = pytest.mark.serial

#: A provider that is not the historical default, used wherever one provider is
#: enough. Every fallback this suite guards against resolves to ``claude-code``,
#: so asserting against it would pass on the broken code too.
NON_DEFAULT_PROVIDER = "kimi-code"


def _echo_argv() -> list[str]:
    return [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('READY\\n'); sys.stdout.flush()",
    ]


@pytest.fixture
def spawned_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Capture the provider key each spawn was asked for.

    Substituting ``_spawn`` is the standard seam in this package: it keeps a
    real PTY (so the tab genuinely registers and broadcasts) while making the
    provider observable without a provider CLI on the machine.
    """
    captured: list[str] = []

    def fake(
        *,
        provider: str,
        project_dir: Path,
        dangerous: bool,
        extra_env: dict[str, str] | None = None,
        prompt: str = "",
    ) -> PtyProcess:
        captured.append(provider)
        return PtyProcess(_echo_argv(), cwd=project_dir, cols=80, rows=24, extra_env=extra_env)

    monkeypatch.setattr(ai_pty._state, "_spawn", fake)
    _active_ptys.clear()
    _engine_tab_to_run.clear()
    yield captured
    for pty in list(_active_ptys.values()):
        with contextlib.suppress(Exception):
            pty.kill_tree()
    _active_ptys.clear()
    _engine_tab_to_run.clear()


@pytest.fixture
def ipc_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "propagation-chain-token"
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", token)
    return token


def _request_tab(
    client: TestClient,
    token: str,
    project: Path,
    provider: str,
    run_id: str,
) -> Any:
    return client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "🤖 chain",
                "provider": provider,
                "cwd": str(project),
                "initial_stdin": "",
                "block_run_id": run_id,
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": token},
    )


# ---------------------------------------------------------------------------
# The previously unguarded link: the internal IPC route
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", agent_keys())
def test_the_ipc_route_forwards_the_requested_provider_to_the_spawn(
    client: TestClient,
    opened_project: Path,
    ipc_token: str,
    spawned_providers: list[str],
    provider: str,
) -> None:
    """FR-010: the route reads the provider off the spec and forwards it.

    Parametrised across the whole registry rather than one interesting key: a
    route that special-cased the two original providers and defaulted the three
    new ones would pass a single-provider test and fail exactly the users this
    change exists to serve.
    """
    response = _request_tab(client, ipc_token, opened_project, provider, f"rid-{provider}")

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert spawned_providers == [provider]


def test_the_ipc_route_substitutes_no_default_when_the_provider_is_missing(
    client: TestClient,
    opened_project: Path,
    ipc_token: str,
    spawned_providers: list[str],
) -> None:
    """An absent provider must fail the request, not silently become the default.

    The pre-ADR-034 engine guessed ``claude-code`` from ``argv[0]`` and returned
    it for anything it did not recognise. Reintroducing that as a route-level
    ``.get(..., "claude-code")`` would be invisible to every other test, so the
    absence case is pinned here alongside the passthrough.
    """
    response = client.post(
        "/api/ai/pty/internal/request-tab",
        json={
            "type": "request_pty_tab",
            "spec": {
                "title": "🤖 chain",
                "cwd": str(opened_project),
                "initial_stdin": "",
                "block_run_id": "rid-no-provider",
                "permission_mode": "safe",
            },
        },
        headers={"X-SciStudio-IPC-Token": ipc_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tab_id"] is None
    assert body["error"], "a spec with no provider was accepted"
    assert spawned_providers == [], f"a provider was spawned anyway: {spawned_providers}"


def test_the_ipc_route_rejects_a_provider_outside_the_registry(
    client: TestClient,
    opened_project: Path,
    ipc_token: str,
    spawned_providers: list[str],
) -> None:
    """FR-023: an unknown key is refused and the accepted set is enumerated."""
    response = _request_tab(client, ipc_token, opened_project, "gemini-cli", "rid-unknown")

    body = response.json()
    assert body["tab_id"] is None
    error = body["error"]
    assert "gemini-cli" in error
    for key in agent_keys():
        assert key in error, f"the rejection omits accepted provider {key!r}: {error}"
    assert spawned_providers == []


# ---------------------------------------------------------------------------
# The whole backend chain in one run
# ---------------------------------------------------------------------------


def test_the_provider_survives_the_ipc_route_the_spawn_and_the_broadcast(
    client: TestClient,
    opened_project: Path,
    ipc_token: str,
    spawned_providers: list[str],
) -> None:
    """One request, three observations, one non-default provider.

    Asserting the hops separately leaves room for two of them to agree on the
    wrong value; asserting them from a single request is what makes the chain
    claim real. ``block_pty_opened`` is the frame the frontend four-link chain
    starts from, so this test ends exactly where
    ``TerminalTab.test.tsx`` begins.
    """
    received: list[dict[str, Any]] = []
    register_ai_pty_subscriber(received.append)
    try:
        response = _request_tab(
            client,
            ipc_token,
            opened_project,
            NON_DEFAULT_PROVIDER,
            "rid-full-chain",
        )
        assert response.status_code == 200
        tab_id = response.json()["tab_id"]
        assert tab_id

        # The broadcast is scheduled on the event loop the route ran under.
        asyncio.run(asyncio.sleep(0.05))
    finally:
        unregister_ai_pty_subscriber(received.append)

    # Hop 1: the route forwarded what the worker asked for.
    assert spawned_providers == [NON_DEFAULT_PROVIDER]

    # Hop 2: the tab the engine registered belongs to that run.
    assert _engine_tab_to_run[tab_id] == "rid-full-chain"

    # Hop 3: the frame the frontend will receive names the same provider.
    opened = next(m for m in received if m.get("type") == "block_pty_opened")
    assert opened["provider"] == NON_DEFAULT_PROVIDER
    assert opened["tab_id"] == tab_id
    assert opened["provider"] != "claude-code"


def test_two_tabs_with_different_providers_do_not_cross_contaminate(
    client: TestClient,
    opened_project: Path,
    ipc_token: str,
    spawned_providers: list[str],
) -> None:
    """Concurrent AI Blocks on different CLIs must not share a provider.

    Spec §2 Edge Cases keeps the PTY registry provider-agnostic, which is only
    safe if the provider travels with each request rather than sitting in
    module state. A cached "last provider" would pass every single-tab test
    here and fail this one.
    """
    first = _request_tab(client, ipc_token, opened_project, "qoder-cn", "rid-a")
    second = _request_tab(client, ipc_token, opened_project, "codex", "rid-b")

    assert first.json()["error"] is None
    assert second.json()["error"] is None
    assert spawned_providers == ["qoder-cn", "codex"]
    assert first.json()["tab_id"] != second.json()["tab_id"]
