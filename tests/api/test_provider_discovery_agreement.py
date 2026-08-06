"""ADR-034 discovery agreement across the three consumers (issue #1994).

The registry's discovery tests (``tests/ai/test_windows_executable_resolution.py``)
prove ``resolve_binary`` behaves correctly. The status tests
(``tests/api/test_provider_discovery.py``) prove the endpoint uses it. The AI
Block tests prove the block calls it. What none of them proves is the property
FR-005 actually states:

    Provider binary discovery MUST return **the same result** for the chat path
    and the AI Block path.

Three call sites agreeing with the resolver individually is not the same claim
as the three agreeing with each other, and the pre-registry defect was exactly a
disagreement: the block called ``shutil.which`` while the Setup screen listed a
provider the block then failed to find. This module drives one fake home and
compares the three answers directly, so a future call site that reintroduces a
bare ``which`` shows up as a mismatch rather than as a subtly different
availability report in the UI.

It also lifts two of spec §4.4's checks from the resolver level to the level the
spec words them at. §4.4 asks that a fake home containing only the Qoder
security-scan sidecar "must report both Qoder channels **unavailable**", and
that a single installed channel leaves the other unavailable — both statements
about ``GET /api/ai/status``, which is where a user would see the consequence.
The existing tests assert the resolver returns ``None``; these assert the
endpoint the picker reads says ``available: false``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent import providers_registry
from scistudio.api.routes import ai as ai_routes
from scistudio.blocks.ai import ai_block


def _install(directory: Path, name: str) -> Path:
    """Create a fake installed CLI, matching the host platform's spelling.

    Unlike the resolver's own tests this does not simulate a platform: the
    point here is that three real call sites agree on *this* machine, so the
    binary has to be findable by the resolver as it actually runs.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (f"{name}.cmd" if sys.platform == "win32" else name)
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A home directory with no CLI in it and nothing on PATH.

    ``Path.home`` is patched on the class, which is what every one of the three
    consumers ultimately resolves through — that shared root is precisely why
    they are able to agree at all.
    """
    home = tmp_path / "agreement_home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)
    monkeypatch.delenv("KIMI_CODE_HOME", raising=False)
    yield home


@pytest.fixture
def stub_version_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer ``--version`` successfully and every auth command with failure.

    The fake binaries are empty files; without this the status endpoint would
    report them unavailable for the wrong reason and the test would pass
    vacuously.
    """

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="9.9.9\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="no")

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)


def _entry(body: dict[str, object], name: str) -> dict[str, object]:
    providers = body["providers"]
    assert isinstance(providers, list)
    return next(p for p in providers if p["name"] == name)


# ---------------------------------------------------------------------------
# FR-005 — the three consumers must agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_chat_status_and_block_paths_resolve_identically_when_installed(
    key: str,
    fake_home: Path,
    stub_version_probe: None,
) -> None:
    """Every provider, installed only in its well-known directory.

    Parametrised over the registry rather than over a list of interesting
    providers, so a sixth one is covered on the day it is added — which is when
    a new call site is most likely to be written against ``shutil.which`` out of
    habit.
    """
    descriptor = providers_registry.get(key)
    install_dir = descriptor.well_known_directories(home=fake_home, env={})[0]
    installed = _install(install_dir, descriptor.binary_candidates[0])

    from_registry = providers_registry.resolve_binary(descriptor)
    from_block = ai_block._discover_provider_binary(descriptor)
    status_binary, available, _version = ai_routes._binary_status(descriptor)

    assert from_registry == installed, f"{key}: registry resolver disagreed"
    assert Path(str(from_block)) == installed, f"{key}: AI Block path disagreed"
    assert status_binary is not None
    assert Path(status_binary) == installed, f"{key}: status path disagreed"
    assert available is True


@pytest.mark.parametrize("key", providers_registry.agent_keys())
def test_chat_status_and_block_paths_agree_on_absence(key: str, fake_home: Path) -> None:
    """The mirror case. Disagreeing about *absence* is the more damaging half.

    A block that thinks a provider is missing while the picker offers it
    produces a validate-time failure the user cannot explain from the UI.
    """
    descriptor = providers_registry.get(key)

    assert providers_registry.resolve_binary(descriptor) is None
    assert ai_block._discover_provider_binary(descriptor) is None
    assert ai_routes._binary_status(descriptor) == (None, False, None)


def test_block_and_status_paths_both_honour_kimi_code_home(
    fake_home: Path,
    stub_version_probe: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The environment override must move discovery for both consumers.

    Kimi's own documentation forbids assuming ``~/.kimi-code`` (spec §2 Edge
    Cases). An override honoured by one consumer and not the other is the same
    disagreement as a missing well-known directory, just harder to spot.
    """
    kimi = providers_registry.get("kimi-code")
    override = tmp_path / "elsewhere" / "kimi"
    installed = _install(override / "bin", "kimi")
    # A decoy at the default location proves the override is read, not ignored.
    _install(fake_home / ".kimi-code" / "bin", "kimi")
    monkeypatch.setenv("KIMI_CODE_HOME", str(override))

    assert providers_registry.resolve_binary(kimi) == installed
    assert Path(str(ai_block._discover_provider_binary(kimi))) == installed
    status_binary, available, _ = ai_routes._binary_status(kimi)
    assert status_binary is not None
    assert Path(status_binary) == installed
    assert available is True


# ---------------------------------------------------------------------------
# Spec §4.4 — sidecar rejection, asserted at the endpoint the user sees
# ---------------------------------------------------------------------------


def test_status_reports_both_qoder_channels_unavailable_when_only_the_sidecar_exists(
    client: TestClient,
    fake_home: Path,
    stub_version_probe: None,
) -> None:
    """FR-027 at the status endpoint, which is what the picker renders.

    ``~/.qodersec/bin/qodercli`` is the security-scan plugin's pinned internal
    copy: older than the real install and unauthenticated. Offering it would
    put a broken agent in the dropdown, and the user would have no way to tell
    it apart from a genuine install.
    """
    _install(fake_home / ".qodersec" / "bin", "qodercli")
    _install(fake_home / ".qodersec" / "bin", "qodersec")

    body = client.get("/api/ai/status").json()
    for key in ("qoder", "qoder-cn"):
        entry = _entry(body, key)
        assert entry["available"] is False, f"{key} resolved to the security-scan sidecar"
        assert entry["version"] is None
        assert entry["logged_in"] is False


@pytest.mark.parametrize(
    ("installed", "missing"),
    [("qoder", "qoder-cn"), ("qoder-cn", "qoder")],
)
def test_status_reports_the_uninstalled_qoder_channel_unavailable(
    client: TestClient,
    fake_home: Path,
    stub_version_probe: None,
    installed: str,
    missing: str,
) -> None:
    """FR-026 at the status endpoint.

    Spec §2: "the other channel is shown as not installed rather than silently
    resolving to the installed channel's binary". Silent fallback would launch
    the wrong account and the wrong model catalog under the right label, which
    is worse than an unavailable entry.
    """
    descriptor = providers_registry.get(installed)
    _install(
        descriptor.well_known_directories(home=fake_home, env={})[0],
        descriptor.binary_candidates[0],
    )

    body = client.get("/api/ai/status").json()
    assert _entry(body, installed)["available"] is True
    assert _entry(body, missing)["available"] is False
    # Distinct labels, so the picker cannot present them as one entry (FR-025).
    assert _entry(body, installed)["label"] != _entry(body, missing)["label"]
