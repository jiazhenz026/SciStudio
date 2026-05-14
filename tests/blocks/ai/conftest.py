"""Shared fixtures for AIBlock tests (ADR-035 Phase 2A).

This file provides a ``StubAgent`` fixture that simulates a claude/codex
agent **without spawning a real subprocess**. Tests configure the stub
to write the outputs the test expects and then write the
``finish_ai_block`` MCP signal — exactly mirroring what the real agent
would do, but synchronously and on a thread the test owns.

The stub also monkeypatches:
  * ``scieasy.engine.pty_control.request_pty_tab`` — returns a fake
    ``tab_id`` and triggers the stub's behaviour.
  * ``scieasy.engine.pty_control.notify_block_pty_event`` — recorded for
    assertions.
  * ``scieasy.blocks.ai.ai_block._discover_provider`` — always returns a
    fake binary path so tests don't depend on claude/codex being
    installed in CI.

Tests should NOT touch the real PTY subsystem; that's I35b's territory
and gets its own integration tests.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


@dataclass
class StubAgent:
    """Fake agent that the test wires into ``request_pty_tab``.

    Configure ``outputs`` (port_name → file content + expected path) and
    optionally ``finish_via`` (``"mcp"`` for the MCP signal path,
    ``"file_only"`` to rely on the file watcher, ``"mark_done"`` to
    signal user mark-done, ``"close"`` to simulate user closing the
    tab without producing output).
    """

    outputs: dict[str, tuple[str, str]] = field(default_factory=dict)
    """Mapping ``port_name → (rel_path_from_project_dir, file_content)``."""

    finish_via: str = "mcp"
    """One of: ``mcp``, ``file_only``, ``mark_done``, ``close``, ``error``."""

    delay: float = 0.0
    """Optional delay (seconds) before the stub takes any action."""

    notifications: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    """Records of ``(block_run_id, event, detail)`` from notify_block_pty_event."""

    request_calls: list[Any] = field(default_factory=list)
    """Records of ``PtyTabSpec`` arguments to request_pty_tab."""

    spawn_error: Exception | None = None
    """If set, ``request_pty_tab`` raises this instead of running the stub."""

    _project_dir: Path | None = None
    _run_dir: Path | None = None

    def attach(self, project_dir: Path) -> None:
        """Bind the stub to the project_dir the test created."""
        self._project_dir = project_dir

    def _emit(self, run_id: str) -> None:
        """Write the configured output files + the chosen completion signal."""
        import time

        if self.delay:
            time.sleep(self.delay)
        assert self._project_dir is not None, "StubAgent.attach() must be called first"

        # Resolve run_dir from convention.
        run_dir = self._project_dir / ".scieasy" / "ai-block-runs" / run_id
        signals = run_dir / "signals"

        if self.finish_via == "close":
            # Don't write outputs; don't write signal. Test should rely on
            # cancel() / timeout to break the wait.
            return

        if self.finish_via == "error":
            # Write a malformed MCP signal so the watcher raises ValueError.
            (signals).mkdir(parents=True, exist_ok=True)
            (signals / "finish_ai_block.json").write_text("{not json", encoding="utf-8")
            return

        # Write outputs to disk.
        mcp_outputs: dict[str, str] = {}
        for port_name, (rel_path, content) in self.outputs.items():
            target = self._project_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            mcp_outputs[port_name] = rel_path

        if self.finish_via == "mcp":
            (signals).mkdir(parents=True, exist_ok=True)
            (signals / "finish_ai_block.json").write_text(json.dumps({"outputs": mcp_outputs}), encoding="utf-8")
        elif self.finish_via == "mark_done":
            (signals).mkdir(parents=True, exist_ok=True)
            (signals / "mark_done.json").write_text(json.dumps({"timestamp": "stub"}), encoding="utf-8")
        # finish_via=="file_only": just leave the output files; the
        # FileWatcher path will eventually pick them up.

    def make_request_handler(self) -> Callable[[Any], str]:
        """Build the ``request_pty_tab`` replacement closure."""

        def _handler(spec: Any) -> str:
            self.request_calls.append(spec)
            if self.spawn_error is not None:
                raise self.spawn_error
            run_id = spec.block_run_id
            # Run the agent simulation in a background thread so the
            # caller's wait loop has a chance to start polling.
            threading.Thread(target=self._emit, args=(run_id,), daemon=True).start()
            return f"tab-{run_id}"

        return _handler

    def make_notify_handler(self) -> Callable[..., None]:
        """Build the ``notify_block_pty_event`` replacement closure."""

        def _handler(block_run_id: str, event: str, detail: Any = None) -> None:
            self.notifications.append((block_run_id, event, detail or {}))

        return _handler


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Provide a fresh project_dir for each test."""
    p = tmp_path / "project"
    p.mkdir()
    return p


@pytest.fixture
def stub_agent(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> StubAgent:
    """Wire a StubAgent into ``pty_control`` + ``_discover_provider``.

    Default behaviour: no outputs, ``finish_via="mcp"``. Tests modify
    ``stub_agent.outputs`` and ``stub_agent.finish_via`` before calling
    ``AIBlock.run()``.
    """
    stub = StubAgent()
    stub.attach(project_dir)

    # Patch pty_control to use the stub.
    from scieasy.engine import pty_control

    monkeypatch.setattr(pty_control, "request_pty_tab", stub.make_request_handler())
    monkeypatch.setattr(pty_control, "notify_block_pty_event", stub.make_notify_handler())

    # Patch the discover lookup so tests don't depend on claude/codex
    # being installed.
    from scieasy.blocks.ai import ai_block as ai_block_module

    monkeypatch.setattr(ai_block_module, "_discover_provider", lambda provider: "/fake/bin/" + provider)

    return stub
