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
import re
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

_PROVIDER_KEYS = {"key", "label", "state", "cause", "next_step", "session_unsupported_reason"}
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
        "next_step": None,
        "session_unsupported_reason": None,
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
def test_minimal_call_argv_is_well_formed(key: str, tmp_path: Path) -> None:
    """Each row carries the prompt exactly once and starts with the binary."""
    call = availability_module.MINIMAL_CALLS[key]
    argv = call.build_argv("/fake/bin/cli", economy=True, workdir=tmp_path)
    assert argv[0] == "/fake/bin/cli"
    assert argv.count(availability_module.LIVE_CALL_PROMPT) == 1
    assert argv[-1] == availability_module.LIVE_CALL_PROMPT
    if call.prompt_flag is not None:
        assert argv[-2] == call.prompt_flag
    for fragment in call.economy_argv:
        assert fragment in argv


# The three mechanisms that bound a probe, one provider key per mechanism.
#
# The previous version of the test below asserted a universal ("no probe may
# read, write or execute") over a hardcoded list of four of the five providers.
# ``kimi-code`` was silently absent, and the shipped system therefore fired a
# fully tool-enabled agent on dialog open while a test named
# ``test_the_probe_never_grants_the_cli_tools`` passed. A partition is used here
# instead of a list so a sixth provider cannot be omitted the same way: the
# union has to equal ``MINIMAL_CALLS`` exactly, and there is no row a provider
# can be added to that does not also state what bounds it.
_TOOL_FREE_BY_FLAG = {"claude-code", "qoder", "qoder-cn"}
"""``--tools ""`` — an empty allowlist, so the model has no tools at all."""

_TOOL_FREE_BY_AGENT_FILE = {"kimi-code"}
"""No tool flag exists, so the empty allowlist arrives as an agent definition."""

_SANDBOXED = {"codex"}
"""No tool switch and no agent file; the read-only sandbox is the bound.

The single justified exception to "cannot read": Codex's sandbox permits
reading and forbids writing and executing, which is the strongest bound that
CLI offers. The probe's cwd is a fresh temporary directory, so what it can read
is the user's filesystem rather than their project.
"""


def test_every_probe_states_what_bounds_it() -> None:
    """Every ``MINIMAL_CALLS`` row is classified, and none is classified twice.

    This is the guard the old hardcoded list was not. A provider added to
    ``MINIMAL_CALLS`` without a decision about its tool restriction fails here
    rather than shipping an unbounded probe behind a test that reads as coverage.
    """
    classified = _TOOL_FREE_BY_FLAG | _TOOL_FREE_BY_AGENT_FILE | _SANDBOXED
    assert classified == set(availability_module.MINIMAL_CALLS)
    assert len(_TOOL_FREE_BY_FLAG) + len(_TOOL_FREE_BY_AGENT_FILE) + len(_SANDBOXED) == len(classified)


@pytest.mark.parametrize("key", sorted(_TOOL_FREE_BY_FLAG))
def test_a_flag_bounded_probe_grants_no_tools(key: str, tmp_path: Path) -> None:
    """``--tools ""`` — the CLI cannot read, write, or execute anything."""
    argv = availability_module.MINIMAL_CALLS[key].build_argv("cli", economy=False, workdir=tmp_path)
    assert argv[argv.index("--tools") + 1] == ""


@pytest.mark.parametrize("key", sorted(_SANDBOXED))
def test_a_sandboxed_probe_cannot_write_or_execute(key: str, tmp_path: Path) -> None:
    """Codex has no tool switch, so its read-only sandbox is what bounds it."""
    argv = availability_module.MINIMAL_CALLS[key].build_argv("cli", economy=False, workdir=tmp_path)
    assert argv[argv.index("--sandbox") + 1] == "read-only"


@pytest.mark.parametrize("key", sorted(_TOOL_FREE_BY_AGENT_FILE))
def test_an_agent_file_bounded_probe_declares_an_empty_tool_allowlist(key: str, tmp_path: Path) -> None:
    """The file is real, is named on the argv, and grants nothing.

    Kimi Code 0.33.0 exposes no tool-disabling or sandbox flag — ``--plan`` is
    refused outright alongside ``-p`` — but an agent definition's ``tools``
    frontmatter field IS its tool allowlist, and an empty one is an empty
    allowlist rather than "unrestricted".
    """
    call = availability_module.MINIMAL_CALLS[key]
    assert call.probe_file is not None
    argv = call.build_argv("cli", economy=False, workdir=tmp_path)
    assert argv[argv.index(call.probe_file.flag) + 1] == str(tmp_path / call.probe_file.name)
    assert 'tools: ""' in call.probe_file.content
    assert 'disallowedTools: "*"' in call.probe_file.content


def test_an_agent_file_probe_writes_its_restriction_before_calling(
    monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    """The restriction exists on disk while the call it bounds is running.

    Read from *inside* the fake subprocess rather than after the fact: an argv
    naming a file that is not there yet is an unrestricted call, and a check
    that ran afterwards could not tell the two apart. The probe's temporary
    directory is removed on the way out, so nothing survives.
    """
    descriptor = providers_registry.get("kimi-code")
    call = availability_module.MINIMAL_CALLS["kimi-code"]
    seen: list[str | None] = []

    def handler(argv: list[str], **_kwargs: Any) -> Any:
        path = Path(argv[argv.index(call.probe_file.flag) + 1]) if call.probe_file else None
        seen.append(path.read_text(encoding="utf-8") if path and path.is_file() else None)
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    assert availability_module._live_call_cause(descriptor) is None
    assert seen == [call.probe_file.content if call.probe_file else None]


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


# ---------------------------------------------------------------------------
# SC-002 — guidance that names a specific next action
#
# FR-031's table gives two of the four states a guidance column: "Installation
# instructions" and "Login instructions for the detected provider". Both audits
# on 2026-08-07 found that what shipped named the providers and then named no
# action at all. The instruction is composed in ``availability.py``, from the
# registry, because every fact in it — which executable, which directories,
# which sign-in command — belongs to ADR-034, and a second copy of it in the
# frontend would be wrong the first time a provider was added.
# ---------------------------------------------------------------------------


def test_every_registry_agent_has_a_login_row() -> None:
    """A sixth provider cannot land without a decision about its sign-in.

    ``None`` is a legitimate value — it means "checked, and this CLI exposes no
    sign-in command" — and it routes to a hint naming the binary and the
    credential file instead. What must not happen is a provider falling through
    to that generic hint because nobody looked.
    """
    assert set(availability_module.LOGIN_COMMANDS) == set(providers_registry.agent_keys())


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_the_install_hint_names_the_executable_and_where_it_was_sought(key: str) -> None:
    """Not a command — the executable, and every directory SciStudio searched.

    ADR-034 FR-014 already records why this is not an install command: the only
    install command SciStudio owns cannot install a vendor's CLI, and an earlier
    hint pointing at it left discovery failing. What the user can act on is what
    was actually checked, and both facts are read off the descriptor so a
    registry change cannot leave the sentence stale.
    """
    descriptor = providers_registry.get(key)
    hint = availability_module.install_hint(descriptor)

    assert descriptor.label in hint
    for candidate in descriptor.binary_candidates:
        assert f"`{candidate}`" in hint
    assert "PATH" in hint
    for segments in descriptor.well_known_dirs:
        tail = segments[1:] if segments[0] == providers_registry.CONFIG_ROOT else segments
        assert "/".join(tail) in hint


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_the_login_hint_names_a_command_or_the_file_that_decides_it(key: str) -> None:
    """A verified command where one exists, and a real action where none does.

    "Sign in the way that agent expects" is precisely what a user in this state
    does not know, so a hint that names nothing is the defect. A hint naming a
    command that does not exist is worse — it makes SciStudio look like the
    broken part — which is why the two unverified providers get the binary and
    the credential file SciStudio reads rather than a guess.
    """
    descriptor = providers_registry.get(key)
    hint = availability_module.login_hint(descriptor)
    command = availability_module.LOGIN_COMMANDS[key]

    if command is not None:
        assert f"`{command}`" in hint
        # The command has to start with a binary this descriptor actually names.
        assert command.split()[0] in descriptor.binary_candidates
    else:
        assert f"`{descriptor.binary_candidates[0]}`" in hint
        assert descriptor.credentials is not None
        assert descriptor.credentials.credential_path[-1] in hint


def test_a_missing_cli_is_told_what_to_install(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    _stub_status_rows(monkeypatch, [_row("claude-code", available=False, logged_in=False)])
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    entry = _by_key(client.get("/api/ai/availability").json(), "claude-code")
    assert entry["state"] == "not_installed"
    assert entry["next_step"] == availability_module.install_hint(providers_registry.get("claude-code"))


def test_a_signed_out_cli_is_told_how_to_sign_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    _stub_status_rows(monkeypatch, [_row("codex", logged_in=False)])
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    entry = _by_key(client.get("/api/ai/availability").json(), "codex")
    assert entry["state"] == "not_authenticated"
    assert "codex login" in (entry["next_step"] or "")


def test_no_next_step_is_offered_where_scistudio_does_not_know_one(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    """``call_failed`` and ``ready`` carry no next step, for opposite reasons.

    A ready provider needs no action. A failed call has a ``cause`` instead, and
    FR-034 forbids sending a user whose CLI demonstrably runs off to fix their
    install — which a next step in this state would amount to, whatever it said.
    """
    _stub_status_rows(monkeypatch, [_row("claude-code"), _row("codex")])

    def handler(argv: list[str], **_: Any) -> Any:
        if "codex" in argv[0]:
            return _completed(argv, returncode=1, stderr="quota exceeded\n")
        return _completed(argv)

    _stub_live_call(monkeypatch, handler)

    body = client.get("/api/ai/availability").json()
    assert _by_key(body, "claude-code")["state"] == "ready"
    assert _by_key(body, "claude-code")["next_step"] is None
    assert _by_key(body, "codex")["state"] == "call_failed"
    assert _by_key(body, "codex")["next_step"] is None


# ---------------------------------------------------------------------------
# The session capability — separate from the availability grade
# ---------------------------------------------------------------------------


def test_a_provider_that_cannot_take_an_opening_prompt_says_so(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    """``kimi-code`` is reported ready AND unable to run a session.

    Both halves matter. It answers live calls, so grading it anything but
    ``ready`` would be a false report about a working agent — and it parses its
    first positional argument as a subcommand, so the one-line pointer every
    SciStudio-started session is delivered with never reaches it. A consumer
    reading only the grade auto-selects an agent that cannot start, which is the
    2026-08-07 no-context audit's P1.
    """
    _stub_status_rows(monkeypatch, [_row("kimi-code"), _row("claude-code")])
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    body = client.get("/api/ai/availability").json()
    kimi = _by_key(body, "kimi-code")
    assert kimi["state"] == "ready"
    assert kimi["session_unsupported_reason"] == providers_registry.get("kimi-code").prompt_unsupported_reason
    assert _by_key(body, "claude-code")["session_unsupported_reason"] is None


def test_the_session_capability_is_reported_in_every_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_home: Path
) -> None:
    """It is a fact about the CLI, not about the user's setup.

    Installing or signing in changes the state and changes nothing here, so a
    consumer must be able to read it without first getting the provider to
    ``ready`` — otherwise "install this" is offered for a provider installing
    will not help.
    """
    _stub_status_rows(monkeypatch, [_row("kimi-code", available=False, logged_in=False)])
    _stub_live_call(monkeypatch, lambda argv, **_: _completed(argv))

    entry = _by_key(client.get("/api/ai/availability").json(), "kimi-code")
    assert entry["state"] == "not_installed"
    assert entry["session_unsupported_reason"]


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_the_session_capability_is_derived_from_the_registry(key: str) -> None:
    """One reading of ``prompt_argv_prefix``, shared by every caller.

    ``spawn_agent`` raises for these providers, the AI Block refuses them at
    config time, and the work-import endpoint refuses them before writing
    anything. All three mean the same thing, so they ask the same function.
    """
    descriptor = providers_registry.get(key)
    reason = availability_module.session_unsupported_reason(descriptor)

    if descriptor.prompt_argv_prefix is None:
        assert reason == descriptor.prompt_unsupported_reason
    else:
        assert reason is None


# ---------------------------------------------------------------------------
# The client's cap on the probe, pinned against the server's own budget
# ---------------------------------------------------------------------------


_USE_AGENT_AVAILABILITY_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "components"
    / "BringInMyWorkDialog.parts"
    / "useAgentAvailability.ts"
)


def _ts_number(source: str, name: str, known: dict[str, float] | None = None) -> float:
    """Read an exported numeric constant out of a TypeScript module.

    Read rather than imported: the two sides are different languages with no
    shared build step. This direction — Python reading TypeScript — is the cheap
    one, because the authoritative values are the server's and they live here,
    and because a Python test can read a ``.ts`` file with no toolchain at all
    while a vitest test would have to parse Python to learn them.

    Handles a sum of literals and already-resolved constants, which is the shape
    the client cap is written in on purpose — deriving it from the mirrored
    server budget is what makes it structurally impossible for the cap to fall
    below the budget. Anything else raises rather than guessing: a constant that
    stops being arithmetic is a change someone has to come back and re-pin.
    """
    match = re.search(rf"export const {name}\s*=\s*([^;\n]+)", source)
    assert match is not None, f"{name} is no longer an exported constant"
    expression = match.group(1).strip().rstrip(";")
    resolved = known or {}
    total = 0.0
    for raw_term in expression.split("+"):
        term = raw_term.strip()
        # ``_`` is a digit separator in a numeric literal and part of the name
        # in an identifier, so it is only stripped from the former.
        total += resolved[term] if term in resolved else float(term.replace("_", ""))
    return total


def test_the_client_probe_cap_is_longer_than_the_servers_own_budget() -> None:
    """A slow-but-working agent must not be reported as failed by the client.

    The server bounds a whole report at ``REPORT_BUDGET_SECONDS`` and reports
    whatever is still outstanding as timed out. A client cap below that gives up
    while the server is legitimately still working: the dialog then renders
    ``call_failed`` guidance and withholds the start action for an agent that
    was about to answer. That shipped at 10 s against a 20 s budget, with the
    slowest measured successful call at 8.3 s — 1.7 s of margin for a working
    setup.

    Pinned across the boundary because neither side can see the other. The two
    constants are in different languages and nothing failed when they drifted.
    """
    source = _USE_AGENT_AVAILABILITY_TS.read_text(encoding="utf-8")
    mirrored_budget_ms = _ts_number(source, "SERVER_REPORT_BUDGET_MS")
    client_cap_ms = _ts_number(
        source,
        "PROBE_TIMEOUT_MS",
        {"SERVER_REPORT_BUDGET_MS": mirrored_budget_ms},
    )

    # The client's mirror of the server budget is the server budget.
    assert mirrored_budget_ms == availability_module.REPORT_BUDGET_SECONDS * 1000
    # And its own cap leaves room for the round trip on top of that.
    assert client_cap_ms > mirrored_budget_ms
