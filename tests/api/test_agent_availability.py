"""Tests for graded agent availability — ADR-053 spec 2, FR-031 to FR-036.

The behaviour under test is the *increment over ADR-034*. Presence — is the CLI
installed, is a credential file there — is already covered by
``tests/api/test_provider_discovery.py`` and is deliberately not re-tested here;
what is tested is that presence is **consumed** rather than re-derived
(FR-032), and that the two states presence cannot answer are separated by a real
call (FR-033).

The case worth naming is ``test_authenticated_provider_whose_live_call_fails``:
a provider that is installed, whose ``--version`` works, and whose credential
file is on disk, but whose call comes back refused. Every presence check in the
repository calls that user ready. It is the user this whole feature exists for,
and it is why the live call is not optional.

Every test drives fakes for ``shutil.which``, ``Path.home``, and
``subprocess.run``, so nothing here depends on which agent CLIs are installed on
the machine running the suite, and no test ever makes a billed request.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent import availability as availability_module
from scistudio.ai.agent import providers_registry
from scistudio.ai.agent.availability import (
    AvailabilityState,
    ProviderAvailability,
    aggregate_state,
    resolve_availability,
)
from scistudio.api.routes import ai as ai_routes

_PROVIDER_KEYS = {"key", "label", "state", "cause"}
_STATE_VALUES = {"not_installed", "not_authenticated", "call_failed", "ready"}


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_cache() -> Any:
    """Drop the shared memoised report around every test.

    ``probe_availability`` memoises module-globally on purpose (a live call is
    billed), which would otherwise leak one test's report into the next.
    """
    availability_module.clear_availability_cache()
    yield
    availability_module.clear_availability_cache()


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an empty throwaway directory.

    The live call resolves its binary through the registry, which reads the home
    directory for off-PATH installs; without this the result would depend on the
    developer's own machine.
    """
    home = tmp_path / "availability_home"
    home.mkdir()
    monkeypatch.setattr(availability_module.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    return home


def _which_bare_only(name: str) -> str | None:
    """PATH stub answering only extension-less names (see test_provider_discovery)."""
    if Path(name).suffix:
        return None
    return f"/fake/bin/{name}"


def _row(
    name: str,
    *,
    available: bool = True,
    logged_in: bool = True,
    label: str | None = None,
) -> dict[str, Any]:
    """One ``GET /api/ai/status`` row, in that endpoint's exact shape."""
    return {
        "name": name,
        "available": available,
        "version": "1.2.3" if available else None,
        "logged_in": logged_in,
        "label": label or providers_registry.get(name).label,
    }


def _all_rows(**common: Any) -> list[dict[str, Any]]:
    """A status row per registered agent provider, with *common* applied to each.

    Defaults to installed and logged in, which is the only starting point from
    which the live call decides anything.
    """
    return [_row(key, **common) for key in providers_registry.agent_keys()]


def _completed(argv: list[str], returncode: int = 0, stdout: str | None = None, stderr: str = "") -> Any:
    """A fake provider result. A failing CLI prints nothing on stdout by default."""
    if stdout is None:
        stdout = "ok\n" if returncode == 0 else ""
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def _stub_live_call(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> list[list[str]]:
    """Replace the live call's subprocess with *handler*, recording every argv."""
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.append(list(argv))
        return handler(argv, **kwargs)

    monkeypatch.setattr(availability_module.subprocess, "run", fake_run)
    monkeypatch.setattr(availability_module.shutil, "which", _which_bare_only)
    return seen


def _stub_status_rows(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    """Serve fixed status rows to the endpoint.

    The rows themselves are ADR-034's contract and are tested in
    ``test_provider_discovery.py``; pinning them here isolates the grading
    behaviour this module owns.
    """

    async def fake_status_rows() -> list[dict[str, Any]]:
        return rows

    monkeypatch.setattr(ai_routes, "_status_rows", fake_status_rows)


def _by_key(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(entry for entry in body["providers"] if entry["key"] == key)


# ---------------------------------------------------------------------------
# Contract C1 — response shape
# ---------------------------------------------------------------------------


def test_response_matches_contract_c1(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Exactly the keys, values, and ordering the checklist §7.1 contract fixes.

    Pinned tightly because a second agent is writing the consumer against this
    contract in parallel; a field renamed here is a break they cannot see.
    """
    _stub_status_rows(monkeypatch, _all_rows())
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    response = client.get("/api/ai/availability")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == {"state", "providers"}
    assert body["state"] in _STATE_VALUES
    assert [entry["key"] for entry in body["providers"]] == list(providers_registry.agent_keys())
    for entry in body["providers"]:
        assert set(entry) == _PROVIDER_KEYS
        assert entry["state"] in _STATE_VALUES
    assert _by_key(body, "claude-code") == {
        "key": "claude-code",
        "label": "Claude Code",
        "state": "ready",
        "cause": None,
    }


def test_labels_come_from_the_status_rows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Display names are carried through, not re-derived — no second label map."""
    _stub_status_rows(monkeypatch, _all_rows())
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    labels = {entry["key"]: entry["label"] for entry in body["providers"]}
    assert labels == {d.key: d.label for d in providers_registry.agent_descriptors()}
    # The two Qoder channels stay distinguishable in a picker.
    assert labels["qoder"] != labels["qoder-cn"]


# ---------------------------------------------------------------------------
# FR-031 / FR-032 — the four states
# ---------------------------------------------------------------------------


def test_not_installed_comes_from_the_status_row(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """``available: false`` maps straight to ``not_installed`` (FR-032)."""
    _stub_status_rows(monkeypatch, _all_rows(available=False))
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    assert body["state"] == "not_installed"
    assert {entry["state"] for entry in body["providers"]} == {"not_installed"}
    assert all(entry["cause"] is None for entry in body["providers"])
    # No CLI is invoked for a provider that is not there — the point of FR-032.
    assert seen == []


def test_not_authenticated_comes_from_the_status_row(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """``available: true, logged_in: false`` maps to ``not_authenticated`` (FR-032).

    And costs nothing: a user who has not logged in yet must not be billed for a
    call that cannot possibly succeed.
    """
    _stub_status_rows(monkeypatch, _all_rows(logged_in=False))
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    assert body["state"] == "not_authenticated"
    assert {entry["state"] for entry in body["providers"]} == {"not_authenticated"}
    assert seen == []


def test_ready_requires_the_live_call_to_succeed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """``ready`` is only ever reported after a real call came back (FR-033)."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    assert body["state"] == "ready"
    assert _by_key(body, "claude-code")["state"] == "ready"
    assert _by_key(body, "claude-code")["cause"] is None
    assert seen, "a ready verdict must be backed by an actual invocation"
    assert seen[0][0].endswith("claude")
    assert "--print" in seen[0]


def test_authenticated_provider_whose_live_call_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """The user this feature exists for: installed, logged in, out of quota.

    The status row here is indistinguishable from a working provider's — the
    binary resolved, ``--version`` answered, credentials are on disk — so every
    presence check reports ready. Only the live call finds the truth, and it has
    to find it *now* rather than several steps into a session (FR-033).
    """
    row = _row("claude-code")
    assert row["available"] is True and row["logged_in"] is True
    _stub_status_rows(monkeypatch, [row])
    _stub_live_call(
        monkeypatch,
        lambda argv, **_: _completed(
            argv,
            returncode=1,
            stdout="",
            stderr="API Error: 429 quota exceeded for this organization\n",
        ),
    )

    body = client.get("/api/ai/availability").json()
    assert body["state"] == "call_failed"
    entry = _by_key(body, "claude-code")
    assert entry["state"] == "call_failed"
    assert "quota exceeded" in (entry["cause"] or "")


def test_every_state_can_be_reported_in_one_report(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """All four states resolve side by side, per provider (FR-031)."""
    _stub_status_rows(
        monkeypatch,
        [
            _row("claude-code"),
            _row("codex"),
            _row("kimi-code", logged_in=False),
            _row("qoder", available=False),
        ],
    )

    def handler(argv: list[str], **_: Any) -> Any:
        if "codex" in argv[0]:
            return _completed(argv, returncode=1, stderr="stream error: connection refused\n")
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    body = client.get("/api/ai/availability").json()
    states = {entry["key"]: entry["state"] for entry in body["providers"]}
    assert states == {
        "claude-code": "ready",
        "codex": "call_failed",
        "kimi-code": "not_authenticated",
        "qoder": "not_installed",
    }
    assert "connection refused" in (_by_key(body, "codex")["cause"] or "")
    # ``cause`` is populated only for ``call_failed`` (contract C1).
    assert [entry["key"] for entry in body["providers"] if entry["cause"]] == ["codex"]


def test_a_provider_the_registry_does_not_know_is_not_installed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """An unregistered row cannot be launched by any surface, so it is not installed."""
    _stub_status_rows(
        monkeypatch,
        [{"name": "ghost-cli", "available": True, "version": "9.9", "logged_in": True, "label": "Ghost"}],
    )
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    assert _by_key(body, "ghost-cli")["state"] == "not_installed"
    assert seen == []


# ---------------------------------------------------------------------------
# FR-034 — the cause, and what it must never say
# ---------------------------------------------------------------------------


def test_cause_drops_reinstall_guidance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """A CLI's own "try reinstalling" line is stripped, the real cause kept (FR-034).

    SciStudio found the binary, read its version, and got an error back from the
    provider's *service*. Repeating the CLI's reinstall advice would send a user
    whose install demonstrably runs to fix something that is not broken.
    """
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    _stub_live_call(
        monkeypatch,
        lambda argv, **_: _completed(
            argv,
            returncode=1,
            stderr=(
                "Error: credit balance is too low to make this request\n"
                "Try reinstalling the CLI: npm install -g @anthropic-ai/claude-code\n"
            ),
        ),
    )

    cause = _by_key(client.get("/api/ai/availability").json(), "claude-code")["cause"] or ""
    assert "credit balance is too low" in cause
    assert "reinstall" not in cause.lower()
    assert "npm install -g" not in cause


def test_cause_falls_back_when_only_reinstall_guidance_was_offered(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Nothing usable left after filtering yields an honest generic cause."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    _stub_live_call(
        monkeypatch,
        lambda argv, **_: _completed(argv, returncode=1, stderr="Please re-install the CLI and try again.\n"),
    )

    cause = _by_key(client.get("/api/ai/availability").json(), "claude-code")["cause"] or ""
    assert cause == availability_module._CAUSE_NO_MESSAGE
    assert "install" not in cause.lower()


def test_a_silent_success_is_not_ready(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Exit 0 with no response is not evidence a call worked."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv, stdout="   \n"))

    entry = _by_key(client.get("/api/ai/availability").json(), "claude-code")
    assert entry["state"] == "call_failed"
    assert entry["cause"] == availability_module._CAUSE_NO_OUTPUT


def test_a_timed_out_call_reports_its_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """``subprocess`` timing out is a reported state, not an exception (FR-035)."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])

    def hanging(argv: list[str], **kwargs: Any) -> Any:
        assert kwargs["timeout"] == availability_module.LIVE_CALL_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(cmd=argv[0], timeout=kwargs["timeout"])

    _stub_live_call(monkeypatch, hanging)

    entry = _by_key(client.get("/api/ai/availability").json(), "claude-code")
    assert entry["state"] == "call_failed"
    assert "did not respond within" in (entry["cause"] or "")


def test_an_unlaunchable_binary_reports_a_cause(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """An ``OSError`` from spawn degrades to a cause rather than a 500."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])

    def raising(argv: list[str], **_: Any) -> Any:
        raise OSError("[WinError 193] %1 is not a valid Win32 application")

    _stub_live_call(monkeypatch, raising)

    response = client.get("/api/ai/availability")
    assert response.status_code == 200
    entry = _by_key(response.json(), "claude-code")
    assert entry["state"] == "call_failed"
    assert "not a valid Win32 application" in (entry["cause"] or "")


# ---------------------------------------------------------------------------
# FR-035 — the probe never blocks its caller
# ---------------------------------------------------------------------------


@pytest.mark.serial
def test_a_hanging_provider_degrades_to_a_reported_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """A provider that ignores its own timeout is reported around, not waited on.

    The fake here does what a wedged Windows child does: it blows straight
    through the ``timeout`` argument. If the report waited for it, a surface
    would sit empty until it finished — the stuck surface FR-035 forbids. The
    assertion is on elapsed wall-clock time, because "returns a state" and
    "returns a state *without waiting*" are different claims and only the second
    one is the requirement.
    """
    _stub_status_rows(monkeypatch, [_row("claude-code"), _row("codex")])
    monkeypatch.setattr(availability_module, "REPORT_BUDGET_SECONDS", 0.2)

    def wedged(argv: list[str], **_: Any) -> Any:
        if "claude" in argv[0]:
            time.sleep(2.0)  # ignores the timeout it was handed
        return _completed(argv)

    _stub_live_call(monkeypatch, wedged)

    started = time.monotonic()
    body = client.get("/api/ai/availability").json()
    elapsed = time.monotonic() - started

    assert elapsed < 1.5, "the report waited for the wedged provider"
    stuck = _by_key(body, "claude-code")
    assert stuck["state"] == "call_failed"
    assert "did not respond within" in (stuck["cause"] or "")
    # The healthy provider is still graded normally, and still makes the report
    # usable: one wedged CLI must not cost the user their working one.
    assert _by_key(body, "codex")["state"] == "ready"
    assert body["state"] == "ready"


def test_providers_are_probed_concurrently(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Total latency is the slowest provider, not the sum of all of them (FR-035).

    A serial probe would make the report's cost scale with the registry, which
    is exactly the shape that turns a fifth provider into a broken surface.
    """
    _stub_status_rows(monkeypatch, _all_rows())
    delay = 0.3

    def slow(argv: list[str], **_: Any) -> Any:
        time.sleep(delay)
        return _completed(argv)

    _stub_live_call(monkeypatch, slow)

    started = time.monotonic()
    body = client.get("/api/ai/availability").json()
    elapsed = time.monotonic() - started

    assert body["state"] == "ready"
    assert len(body["providers"]) == 5
    assert elapsed < delay * len(body["providers"])


# ---------------------------------------------------------------------------
# Contract C1 — aggregate ranking
# ---------------------------------------------------------------------------


def _availability(state: AvailabilityState) -> ProviderAvailability:
    return ProviderAvailability(key="p", label="P", state=state)


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ((), AvailabilityState.NOT_INSTALLED),
        ((AvailabilityState.READY,), AvailabilityState.READY),
        ((AvailabilityState.NOT_INSTALLED, AvailabilityState.READY), AvailabilityState.READY),
        ((AvailabilityState.CALL_FAILED, AvailabilityState.READY), AvailabilityState.READY),
        (
            (AvailabilityState.CALL_FAILED, AvailabilityState.NOT_AUTHENTICATED),
            AvailabilityState.CALL_FAILED,
        ),
        (
            (AvailabilityState.NOT_INSTALLED, AvailabilityState.CALL_FAILED),
            AvailabilityState.CALL_FAILED,
        ),
        (
            (AvailabilityState.NOT_INSTALLED, AvailabilityState.NOT_AUTHENTICATED),
            AvailabilityState.NOT_AUTHENTICATED,
        ),
        ((AvailabilityState.NOT_INSTALLED,), AvailabilityState.NOT_INSTALLED),
    ],
)
def test_aggregate_state_ranking(
    states: tuple[AvailabilityState, ...],
    expected: AvailabilityState,
) -> None:
    """``ready`` if any; otherwise ``call_failed`` > ``not_authenticated`` > ``not_installed``.

    The asymmetry is the requirement, not an optimisation: a user with a working
    Claude Code and an unconfigured Codex has a usable agent, and a surface that
    reported the worst state would block them over a CLI they never intended to
    use (FR-005).
    """
    assert aggregate_state([_availability(state) for state in states]) is expected


def test_empty_registry_reports_not_installed() -> None:
    """No agent providers at all means no agent (contract C1)."""
    report = asyncio.run(resolve_availability([]))
    assert report.state is AvailabilityState.NOT_INSTALLED
    assert report.providers == ()


def test_a_mixed_report_does_not_block_the_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """One usable provider makes the aggregate ready however bad the rest are (FR-005)."""
    _stub_status_rows(
        monkeypatch,
        [_row("claude-code"), _row("codex"), _row("kimi-code", available=False)],
    )

    def handler(argv: list[str], **_: Any) -> Any:
        if "codex" in argv[0]:
            return _completed(argv, returncode=1, stderr="quota exceeded\n")
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    body = client.get("/api/ai/availability").json()
    assert body["state"] == "ready"
    assert _by_key(body, "codex")["state"] == "call_failed"
    assert _by_key(body, "kimi-code")["state"] == "not_installed"


# ---------------------------------------------------------------------------
# The minimal call table
# ---------------------------------------------------------------------------


def test_every_registry_agent_has_a_minimal_call() -> None:
    """A sixth provider cannot land without its own live-call row.

    Without this the new provider would fall through to the ungradable branch,
    which is honest but useless: FR-033 makes the live call the only evidence
    that permits ``ready``, so a missing row silently costs that provider its
    best state.
    """
    assert set(availability_module.MINIMAL_CALLS) == set(providers_registry.agent_keys())


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_minimal_call_argv_is_well_formed(key: str) -> None:
    """Each row carries the prompt exactly once and starts with the binary."""
    call = availability_module.MINIMAL_CALLS[key]
    argv = call.build_argv("/fake/bin/cli", economy=True)
    assert argv[0] == "/fake/bin/cli"
    assert argv.count(availability_module.LIVE_CALL_PROMPT) == 1
    assert argv[-1] == availability_module.LIVE_CALL_PROMPT
    if call.prompt_flag is not None:
        assert argv[-2] == call.prompt_flag
    for fragment in call.economy_argv:
        assert fragment in argv


def test_the_probe_never_grants_the_cli_tools(fake_home: Path) -> None:
    """No probe may read, write, or execute on the user's machine.

    A call fired on dialog open must have nothing to reason about afterwards.
    Where the CLI has a tool switch it is turned off outright; Codex has none,
    so its read-only sandbox is what bounds it.
    """
    calls = availability_module.MINIMAL_CALLS
    for key in ("claude-code", "qoder", "qoder-cn"):
        argv = calls[key].build_argv("cli", economy=False)
        assert argv[argv.index("--tools") + 1] == ""
    codex_argv = calls["codex"].build_argv("cli", economy=False)
    assert codex_argv[codex_argv.index("--sandbox") + 1] == "read-only"


def test_the_probe_runs_outside_the_server_working_directory(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
    tmp_path: Path,
) -> None:
    """A probe must not load a project's agent configuration into a billed call."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    seen_cwd: list[str] = []

    def handler(argv: list[str], **kwargs: Any) -> Any:
        seen_cwd.append(str(kwargs["cwd"]))
        assert kwargs["stdin"] == subprocess.DEVNULL
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    assert client.get("/api/ai/availability").json()["state"] == "ready"
    assert seen_cwd
    assert seen_cwd[0] != str(Path.cwd())
    assert "scistudio-availability-" in seen_cwd[0]


def test_a_failed_economy_attempt_is_retried_at_the_default_model(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """A user whose backend lacks the cheap model alias is not called broken.

    The economy hints name a model alias or a config key to cut the bill by an
    order of magnitude. A gateway or enterprise backend may not carry that
    alias, and reporting such a user ``call_failed`` would be a false alarm
    about a working setup — so the failure is retried once at their own default
    before anything is reported.
    """
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    economy = availability_module.MINIMAL_CALLS["claude-code"].economy_argv
    assert economy

    def handler(argv: list[str], **_: Any) -> Any:
        if economy[0] in argv:
            return _completed(argv, returncode=1, stderr="model not found: haiku\n")
        return _completed(argv)

    seen = _stub_live_call(monkeypatch, handler)

    body = client.get("/api/ai/availability").json()
    assert _by_key(body, "claude-code")["state"] == "ready"
    assert len(seen) == 2
    assert economy[0] in seen[0]
    assert economy[0] not in seen[1]


def test_a_genuinely_failing_provider_is_not_retried_forever(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Both attempts failing reports the *default-model* cause, once."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    economy = availability_module.MINIMAL_CALLS["claude-code"].economy_argv

    def handler(argv: list[str], **_: Any) -> Any:
        detail = "cheap model refused" if economy[0] in argv else "quota exceeded"
        return _completed(argv, returncode=1, stderr=f"{detail}\n")

    seen = _stub_live_call(monkeypatch, handler)

    entry = _by_key(client.get("/api/ai/availability").json(), "claude-code")
    assert entry["state"] == "call_failed"
    assert entry["cause"] == "quota exceeded"
    assert len(seen) == 2


def test_a_provider_without_economy_hints_makes_one_attempt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """No economy hints means no retry — there is nothing to fall back from."""
    assert availability_module.MINIMAL_CALLS["qoder"].economy_argv == ()
    _stub_status_rows(monkeypatch, [_row("qoder")])
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv, returncode=1, stderr="denied\n"))

    assert _by_key(client.get("/api/ai/availability").json(), "qoder")["state"] == "call_failed"
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# Sharing the report across surfaces
# ---------------------------------------------------------------------------


def test_the_report_is_memoised_between_callers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """Two surfaces asking inside the window share one answer.

    Availability is consumed by more than one surface (FR-036), and every live
    call is a billed request. Charging the user once per surface per open would
    make the shared module more expensive than a private one.
    """
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    first = client.get("/api/ai/availability").json()
    second = client.get("/api/ai/availability").json()
    assert first == second
    assert len(seen) == 1


def test_refresh_bypasses_the_memoised_report(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """An explicit retry re-probes, so a user who just fixed their quota sees it."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    quota_exhausted = {"value": True}

    def handler(argv: list[str], **_: Any) -> Any:
        if quota_exhausted["value"]:
            return _completed(argv, returncode=1, stderr="quota exceeded\n")
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    assert client.get("/api/ai/availability").json()["state"] == "call_failed"
    quota_exhausted["value"] = False
    # Without ``refresh`` the user would still be reading the failure below.
    assert client.get("/api/ai/availability").json()["state"] == "call_failed"
    assert client.get("/api/ai/availability?refresh=true").json()["state"] == "ready"


def test_an_expired_report_is_recomputed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """The memo is a window, not a latch."""
    _stub_status_rows(monkeypatch, [_row("claude-code")])
    seen = _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))
    monkeypatch.setattr(availability_module, "CACHE_TTL_SECONDS", 0.0)

    client.get("/api/ai/availability")
    client.get("/api/ai/availability")
    assert len(seen) == 2


# ---------------------------------------------------------------------------
# FR-032 — one discovery path, end to end
# ---------------------------------------------------------------------------


def test_availability_runs_on_the_status_endpoints_own_discovery(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No stubbed rows: the same probes feed both endpoints, off-PATH included.

    Kimi Code is installed only in its well-known directory here — never on
    PATH — so a grading path that had grown its own discovery would report it
    ``not_installed`` while ``/api/ai/status`` reported it present. Driving both
    endpoints from one set of fakes is what pins them together (FR-032, FR-005).
    """
    home = tmp_path / "shared_home"
    kimi_bin = home / ".kimi-code" / "bin"
    kimi_bin.mkdir(parents=True)
    for name in ("kimi", "kimi.cmd"):
        (kimi_bin / name).write_text("#!/bin/sh\n", encoding="utf-8")
    credential = home / ".kimi-code" / "credentials" / "kimi-code.json"
    credential.parent.mkdir(parents=True)
    credential.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(availability_module.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)
    monkeypatch.setattr(availability_module.shutil, "which", lambda _name: None)

    def fake_run(argv: list[str], **_: Any) -> Any:
        if argv[1:] == ["--version"]:
            return _completed(argv, stdout="0.33.0\n")
        return _completed(argv)

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)
    monkeypatch.setattr(availability_module.subprocess, "run", fake_run)

    status = client.get("/api/ai/status").json()
    availability = client.get("/api/ai/availability").json()

    status_kimi = next(entry for entry in status["providers"] if entry["name"] == "kimi-code")
    assert status_kimi["available"] is True
    assert status_kimi["logged_in"] is True
    assert _by_key(availability, "kimi-code")["state"] == "ready"
    # Providers with nothing installed agree across both endpoints.
    assert next(e for e in status["providers"] if e["name"] == "qoder")["available"] is False
    assert _by_key(availability, "qoder")["state"] == "not_installed"
    assert [entry["key"] for entry in availability["providers"]] == [entry["name"] for entry in status["providers"]]
