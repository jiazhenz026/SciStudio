"""The parity venv must install the CI-pinned tool versions, not merely hash them.

Regression guard for a silent CI-equivalence failure found while delivering
#1994. ``provisioning_marker`` already hashes ``resolve_ci_tool_versions``, so a
reader of that function reasonably concludes the pins are enforced. They were
not: ``_install_deps`` installed ``-e ".[dev]"`` and stopped, and ``[dev]``
declares ``ruff>=0.11`` with no upper bound.

The failure mode is what makes it worth a test rather than a comment. Because
the marker matched, the drifted venv was treated as warm and reused, so nothing
ever rebuilt it. The gate reported ``format_check`` failures on files that CI —
running the pinned version — formats cleanly, and it reported them
indefinitely.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record import parity


def _record_commands(monkeypatch: Any, *, uv_available: bool) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **_: Any) -> tuple[bool, str]:
        commands.append(cmd)
        return True, "ok"

    monkeypatch.setattr(parity, "_run", fake_run)
    monkeypatch.setattr(parity, "_uv_available", lambda: uv_available)
    monkeypatch.setattr(
        parity,
        "resolve_ci_tool_versions",
        lambda _root: {"ruff": "9.9.9", "mypy": "8.8.8"},
    )
    return commands


def test_uv_path_installs_the_ci_pinned_tool_versions(monkeypatch: Any, tmp_path: Path) -> None:
    commands = _record_commands(monkeypatch, uv_available=True)

    ok, _summary = parity._install_deps(tmp_path, tmp_path / "venv")

    assert ok
    flat = [" ".join(cmd) for cmd in commands]
    assert any("-e .[dev]" in line for line in flat), flat
    assert any("ruff==9.9.9" in line and "mypy==8.8.8" in line for line in flat), flat


def test_pip_fallback_installs_the_ci_pinned_tool_versions(monkeypatch: Any, tmp_path: Path) -> None:
    commands = _record_commands(monkeypatch, uv_available=False)

    ok, _summary = parity._install_deps(tmp_path, tmp_path / "venv")

    assert ok
    flat = [" ".join(cmd) for cmd in commands]
    assert any("ruff==9.9.9" in line and "mypy==8.8.8" in line for line in flat), flat


def test_a_failed_editable_install_does_not_go_on_to_install_pins(monkeypatch: Any, tmp_path: Path) -> None:
    """A broken base install must surface, not be masked by a later success."""
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], **_: Any) -> tuple[bool, str]:
        commands.append(cmd)
        return ("-e" not in cmd), "boom" if "-e" in cmd else "ok"

    monkeypatch.setattr(parity, "_run", fake_run)
    monkeypatch.setattr(parity, "_uv_available", lambda: True)
    monkeypatch.setattr(parity, "resolve_ci_tool_versions", lambda _root: {"ruff": "9.9.9"})

    ok, summary = parity._install_deps(tmp_path, tmp_path / "venv")

    assert not ok
    assert summary == "boom"
    assert not any("ruff==9.9.9" in " ".join(cmd) for cmd in commands), commands


def test_resolved_pins_come_from_the_files_ci_actually_pins() -> None:
    """The pins are only meaningful if they track CI's own declarations.

    ``ci.yml`` and ``.pre-commit-config.yaml`` carry a comment instructing that
    they be bumped together; this asserts the resolver reads that pair rather
    than the unbounded ``[dev]`` floor.
    """
    repo_root = Path(__file__).resolve().parents[2]
    resolved = parity.resolve_ci_tool_versions(repo_root)

    assert "ruff" in resolved
    ci_yml = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert f"ruff=={resolved['ruff']}" in ci_yml
