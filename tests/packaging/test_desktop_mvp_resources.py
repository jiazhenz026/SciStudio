"""Low-cost ADR-037 desktop MVP packaging/resource checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_DIR = REPO_ROOT / "desktop"


def _desktop_package_json() -> dict[str, object]:
    package_json = DESKTOP_DIR / "package.json"
    if not package_json.exists():
        pytest.skip("ADR-037 desktop package scaffold is not present yet; tracked by #1502.")
    return json.loads(package_json.read_text(encoding="utf-8"))


def test_desktop_package_declares_mvp_scripts() -> None:
    """The Electron MVP must expose the reviewer-facing commands from the spec."""
    package_data = _desktop_package_json()

    scripts = package_data.get("scripts")
    assert isinstance(scripts, dict)
    for script in ("build:frontend", "stage", "start", "dist:dir"):
        assert script in scripts
        assert isinstance(scripts[script], str)
        assert scripts[script].strip()


def test_desktop_stage_outputs_expected_resource_layout() -> None:
    """After `npm --prefix desktop run stage`, resources should be package-friendly."""
    _desktop_package_json()
    resources = DESKTOP_DIR / "resources"
    backend_src = resources / "backend" / "src"
    packages_keep = resources / "packages" / ".gitkeep"

    if not backend_src.exists() or not packages_keep.exists():
        pytest.skip("Run `npm --prefix desktop run stage` before validating staged resources (#1502).")

    assert (resources / "frontend").is_dir()
    assert (backend_src / "scistudio").is_dir()
    assert not (resources / "app").exists()
    assert packages_keep.is_file()
    assert (resources / "git").is_dir()


def test_portable_git_scripts_use_scistudio_skip_env_var() -> None:
    """Portable-git integrity bypass naming must not leak another project name."""
    powershell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.ps1").read_text(encoding="utf-8")
    shell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.sh").read_text(encoding="utf-8")

    combined = powershell_script + "\n" + shell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in powershell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in shell_script
    assert "SCIEASY_SKIP_GIT_SHA_VERIFY" not in combined
