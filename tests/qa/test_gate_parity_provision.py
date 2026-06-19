"""Unit tests for §7.10 isolated per-worktree venv auto-provisioning.

These tests exercise the real provisioning logic with the venv/install
subprocess MOCKED — they never create a real venv or hit the network, so they
stay fast and green in CI. They cover:

- venv path resolution (per-worktree, gitignored under ``.workflow/local``);
- cross-platform executable resolution (Windows ``Scripts`` vs POSIX ``bin``);
- the cache marker (re-provision on change, skip when unchanged);
- fail-closed behaviour on venv-creation / install error;
- ``--mode ci`` does NOT provision.

The autouse ``_stub_parity_provisioning`` fixture (conftest) replaces
``parity.provision_venv`` for the rest of the QA suite; here we capture and
restore the REAL implementation so we test it directly.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

import scistudio.qa.governance.gate_record.checks as checks
import scistudio.qa.governance.gate_record.parity as parity

# Capture the real implementation before the autouse conftest fixture stubs it.
_REAL_PROVISION_VENV = parity.provision_venv


@pytest.fixture
def real_provision(monkeypatch: pytest.MonkeyPatch):
    """Restore the real provision_venv (autouse conftest stubs it)."""

    monkeypatch.setattr(parity, "provision_venv", _REAL_PROVISION_VENV)
    return _REAL_PROVISION_VENV


# ---------------------------------------------------------------------------
# venv path + gitignore.
# ---------------------------------------------------------------------------


def test_venv_path_is_per_worktree_and_under_local(tmp_path: Path) -> None:
    venv = parity.venv_path(tmp_path)
    assert venv == tmp_path / ".workflow/local/venv"
    # Each worktree (repo_root) gets its OWN venv path.
    other = tmp_path / "other-worktree"
    assert parity.venv_path(other) != venv


def test_venv_path_is_gitignored() -> None:
    # The venv lives under .workflow/local/, which .gitignore ignores.
    gitignore = Path(__file__).resolve().parents[2] / ".gitignore"
    text = gitignore.read_text(encoding="utf-8")
    assert ".workflow/local/" in text


# ---------------------------------------------------------------------------
# Cross-platform executable resolution.
# ---------------------------------------------------------------------------


def test_resolve_venv_executable_none_when_no_venv(tmp_path: Path) -> None:
    assert parity.resolve_venv_executable(tmp_path, "ruff") is None


def test_resolve_venv_executable_windows_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "nt")
    venv = parity.venv_path(tmp_path)
    scripts = venv / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "ruff.exe").write_text("", encoding="utf-8")
    (scripts / "python.exe").write_text("", encoding="utf-8")
    resolved = parity.resolve_venv_executable(tmp_path, "ruff")
    assert resolved is not None and resolved.name == "ruff.exe"
    py = parity.venv_python(venv)
    assert py.name == "python.exe" and py.parent.name == "Scripts"


def test_resolve_venv_executable_posix_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    venv = parity.venv_path(tmp_path)
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "mypy").write_text("", encoding="utf-8")
    (bin_dir / "python").write_text("", encoding="utf-8")
    resolved = parity.resolve_venv_executable(tmp_path, "mypy")
    assert resolved is not None and resolved.name == "mypy"
    py = parity.venv_python(venv)
    assert py.name == "python" and py.parent.name == "bin"


# ---------------------------------------------------------------------------
# Cache marker: re-provision on change, skip when unchanged.
# ---------------------------------------------------------------------------


def test_marker_changes_with_deps(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["ruff>=0.11"]\n', encoding="utf-8"
    )
    marker_a = parity.provisioning_marker(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project.optional-dependencies]\ndev = ["ruff>=0.11", "mypy>=1.15"]\n', encoding="utf-8"
    )
    marker_b = parity.provisioning_marker(tmp_path)
    assert marker_a != marker_b
    assert marker_a.startswith("sha256:")


def test_local_ci_tool_dependencies_are_in_dev_extra() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    assert "semantic_dup" in checks.CHECK_CATALOG
    assert "wheel_release_smoke" in checks.CHECK_CATALOG
    assert "python_tests" in checks.CHECK_CATALOG
    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    dev_deps = parity._dev_extras(repo_root)
    normalized = [dep.lower() for dep in dev_deps]
    runtime_or_dev = [*(str(dep).lower() for dep in project.get("dependencies", [])), *normalized]
    assert any(dep.lower().startswith("fastembed") for dep in dev_deps)
    assert any(dep.startswith("build") for dep in normalized)
    assert any(dep.startswith("pandas") for dep in runtime_or_dev)
    assert any(dep.startswith("setuptools") for dep in normalized)
    assert any(dep.startswith("tifffile") for dep in normalized)


def _make_src(repo: Path) -> None:
    (repo / "src" / "scistudio").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "scistudio" / "__init__.py").write_text("", encoding="utf-8")


def test_warm_venv_with_matching_marker_skips_reprovision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision
) -> None:
    _make_src(tmp_path)
    venv = parity.venv_path(tmp_path)
    venv.mkdir(parents=True)
    # Seed a marker matching the current fingerprint => warm.
    (venv / parity._MARKER_NAME).write_text(parity.provisioning_marker(tmp_path) + "\n", encoding="utf-8")

    created: list[str] = []
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: created.append("create") or (True, "ok"))
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: created.append("install") or (True, "ok"))
    monkeypatch.setattr(parity, "check_importable_env", lambda _repo, **_k: True)

    report = real_provision(tmp_path)
    assert report.ok and report.venv_path == venv
    # Warm hit: neither create nor install was invoked.
    assert created == []


def test_marker_mismatch_triggers_reprovision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    venv = parity.venv_path(tmp_path)
    venv.mkdir(parents=True)
    (venv / parity._MARKER_NAME).write_text("sha256:stale\n", encoding="utf-8")
    (venv / "stale.txt").write_text("old dependency state", encoding="utf-8")

    calls: list[str] = []

    def _fake_create(_repo_root: Path, venv_path: Path) -> tuple[bool, str]:
        calls.append("create")
        assert not venv_path.exists()
        venv_path.mkdir(parents=True)
        return True, "ok"

    monkeypatch.setattr(parity, "_create_venv", _fake_create)
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: calls.append("install") or (True, "ok"))
    monkeypatch.setattr(parity, "check_importable_env", lambda _repo, **_k: True)

    report = real_provision(tmp_path)
    assert report.ok and report.provisioned
    assert calls == ["create", "install"]
    assert not (venv / "stale.txt").exists()
    # The fresh marker is written so the next run is warm.
    assert (venv / parity._MARKER_NAME).read_text(encoding="utf-8").strip() == parity.provisioning_marker(tmp_path)


def test_stale_venv_removal_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    venv = parity.venv_path(tmp_path)
    venv.mkdir(parents=True)
    (venv / parity._MARKER_NAME).write_text("sha256:stale\n", encoding="utf-8")

    monkeypatch.setattr(parity, "_remove_stale_venv", lambda *a, **k: (False, "refusing test path"))
    create_called: list[str] = []
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: create_called.append("create") or (True, "ok"))

    report = real_provision(tmp_path)
    assert not report.ok
    assert any("cannot remove stale isolated per-worktree venv" in gap for gap in report.gaps)
    assert create_called == []


# ---------------------------------------------------------------------------
# Fail-closed on provisioning error.
# ---------------------------------------------------------------------------


def test_fail_closed_on_venv_creation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: (False, "uv venv failed: no network"))
    install_called: list[str] = []
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: install_called.append("x") or (True, "ok"))
    report = real_provision(tmp_path)
    assert not report.ok and not report.importable
    assert any("cannot create isolated per-worktree venv" in g for g in report.gaps)
    # Install is never attempted after a creation failure.
    assert install_called == []


def test_fail_closed_on_install_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: (False, "pip failed: ResolutionImpossible"))
    report = real_provision(tmp_path)
    assert not report.ok and not report.importable
    assert any("cannot install CI-equivalent deps" in g for g in report.gaps)


def test_fail_closed_when_provisioned_venv_not_importable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision
) -> None:
    _make_src(tmp_path)
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(parity, "check_importable_env", lambda _repo, **_k: False)
    report = real_provision(tmp_path)
    assert not report.ok
    assert any("cannot import scistudio" in g for g in report.gaps)


# ---------------------------------------------------------------------------
# CRITICAL: --mode ci does NOT provision.
# ---------------------------------------------------------------------------


def test_ci_mode_does_not_provision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    provisioned: list[str] = []
    monkeypatch.setattr(parity, "_create_venv", lambda *a, **k: provisioned.append("create") or (True, "ok"))
    monkeypatch.setattr(parity, "_install_deps", lambda *a, **k: provisioned.append("install") or (True, "ok"))
    # ci mode validates the PYTHONPATH=src fallback instead of provisioning.
    monkeypatch.setattr(parity, "check_importable_env", lambda _repo, **_k: True)
    report = parity.assess_parity(tmp_path, mode="ci")
    assert provisioned == []
    assert report.venv_path is None
    assert not report.provisioned


def test_local_mode_provisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provision) -> None:
    _make_src(tmp_path)
    seen: list[str] = []

    def _fake_provision(repo_root: Path, **_k: object) -> parity.ParityReport:
        seen.append("provision")
        return parity.ParityReport(importable=True, venv_path=parity.venv_path(repo_root), provisioned=True)

    monkeypatch.setattr(parity, "provision_venv", _fake_provision)
    for mode in ("local", "pre-commit", "pre-push", "pre-pr"):
        seen.clear()
        report = parity.assess_parity(tmp_path, mode=mode)
        assert seen == ["provision"], mode
        assert report.provisioned, mode


def test_explicit_provision_false_skips(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_src(tmp_path)
    provisioned: list[str] = []
    monkeypatch.setattr(parity, "provision_venv", lambda *a, **k: provisioned.append("x") or parity.ParityReport(True))
    monkeypatch.setattr(parity, "check_importable_env", lambda _repo, **_k: True)
    parity.assess_parity(tmp_path, mode="local", provision=False)
    assert provisioned == []
