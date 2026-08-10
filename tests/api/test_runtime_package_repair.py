"""Scheduling tests for the desktop package dependency repair (#2068).

The repair ends in ``pip install`` subprocesses and was measured at 11.7s in the
common case and 36s at worst. It used to be the first statement of
``ApiRuntime._configure_static_registries``, which put that cost between
uvicorn's "Waiting for application startup." and readiness — against the
desktop's 30s HTTP readiness timeout, so the slow case did not merely feel slow,
it failed the launch outright.
"""

from __future__ import annotations

import threading

import pytest

from scistudio.api import runtime as runtime_module
from scistudio.api.runtime import ApiRuntime

pytestmark = pytest.mark.serial


class _RegistryStub:
    """Minimal object carrying the real method under test.

    A full ``ApiRuntime`` would scan the block and type registries, which is what
    this test is trying to observe rather than perform.
    """

    _start_background_package_repair = ApiRuntime._start_background_package_repair

    def __init__(self) -> None:
        self.refreshed: list[str] = []

    def refresh_type_registry(self) -> None:
        self.refreshed.append("type")

    def refresh_block_registry(self) -> None:
        self.refreshed.append("block")


def _capture_threads(monkeypatch: pytest.MonkeyPatch) -> list[threading.Thread]:
    created: list[threading.Thread] = []
    real_thread = threading.Thread

    def capture(*args: object, **kwargs: object) -> threading.Thread:
        thread = real_thread(*args, **kwargs)  # type: ignore[arg-type]
        created.append(thread)
        return thread

    monkeypatch.setattr(runtime_module.threading, "Thread", capture)
    return created


def test_package_repair_runs_off_the_startup_path(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    def fake_repair() -> bool:
        entered.set()
        assert release.wait(5)
        return True

    monkeypatch.setattr(runtime_module, "_is_bundled_desktop_run", lambda: True)
    monkeypatch.setattr(runtime_module, "_repair_desktop_package_dependencies", fake_repair)
    created = _capture_threads(monkeypatch)

    stub = _RegistryStub()
    stub._start_background_package_repair()

    # Startup has already moved on while the repair is still mid-flight.
    assert entered.wait(5)
    assert stub.refreshed == []

    release.set()
    created[0].join(5)
    # A repair rewrites the dependency cache the registries were scanned against,
    # so they are rebuilt once it lands.
    assert stub.refreshed == ["type", "block"]


def test_package_repair_skips_registry_refresh_when_nothing_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_module, "_is_bundled_desktop_run", lambda: True)
    monkeypatch.setattr(runtime_module, "_repair_desktop_package_dependencies", lambda: False)
    created = _capture_threads(monkeypatch)

    stub = _RegistryStub()
    stub._start_background_package_repair()
    created[0].join(5)

    assert stub.refreshed == []


def test_package_repair_is_skipped_outside_a_bundled_desktop_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_module, "_is_bundled_desktop_run", lambda: False)
    monkeypatch.setattr(
        runtime_module,
        "_repair_desktop_package_dependencies",
        lambda: pytest.fail("repair must not run outside a bundled desktop run"),
    )
    created = _capture_threads(monkeypatch)

    _RegistryStub()._start_background_package_repair()

    assert created == []
