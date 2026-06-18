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
    parsed: object = json.loads(package_json.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return {str(key): value for key, value in parsed.items()}


def test_desktop_package_declares_mvp_scripts() -> None:
    """The Electron MVP must expose the reviewer-facing commands from the spec."""
    package_data = _desktop_package_json()

    scripts = package_data.get("scripts")
    assert isinstance(scripts, dict)
    for script in (
        "build:frontend",
        "build:python",
        "build:python:mac",
        "stage",
        "stage:sh",
        "start",
        "dist:dir",
        "dist:win",
        "dist:dmg",
    ):
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


def test_desktop_main_checks_windows_pty_python_dependency() -> None:
    """The desktop shell must not silently choose a Python without pywinpty."""
    main_js = (DESKTOP_DIR / "main.js").read_text(encoding="utf-8")

    assert "verifyPtyCapablePython" in main_js
    assert "find_spec('winpty')" in main_js
    assert "find_spec('pywinpty')" in main_js
    assert "SCISTUDIO_DESKTOP_PYTHON" in main_js


def test_desktop_has_portable_python_runtime_builder() -> None:
    """The desktop MVP must have a reproducible self-contained Python builder."""
    script = DESKTOP_DIR / "scripts" / "build-python-runtime.ps1"
    content = script.read_text(encoding="utf-8")

    assert script.exists()
    assert "python.org/ftp/python" in content
    assert "get-pip.py" in content
    assert "pip install --no-warn-script-location $RepoRoot" in content
    assert "import scistudio, fastapi, uvicorn, winpty" in content


def test_desktop_has_macos_dmg_builder() -> None:
    """The macOS DMG path must include a standalone Python runtime builder."""
    package_data = _desktop_package_json()
    scripts = package_data["scripts"]
    assert isinstance(scripts, dict)
    assert "build-python-runtime-macos.sh" in scripts["build:python:mac"]
    assert "--mac dmg --x64" in scripts["dist:dmg"]

    script = DESKTOP_DIR / "scripts" / "build-python-runtime-macos.sh"
    content = script.read_text(encoding="utf-8")
    assert "python-build-standalone" in content
    assert "resources/python" in content or 'PYTHON_ROOT="$RESOURCES_ROOT/python"' in content
    assert 'pip install --no-warn-script-location "$REPO_ROOT"' in content
    assert "import scistudio, fastapi, uvicorn, pty" in content

    workflow = REPO_ROOT / ".github" / "workflows" / "desktop-macos-dmg.yml"
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "pull_request:" in workflow_text
    assert "runs-on: macos-13" in workflow_text
    assert "npm --prefix desktop run build:python:mac" in workflow_text
    assert "npm --prefix desktop run dist:dmg" in workflow_text
    assert "desktop/dist/*.dmg" in workflow_text


def test_desktop_has_windows_installer_builder() -> None:
    """The Windows chain must build a real installer, not only win-unpacked."""
    package_data = _desktop_package_json()
    scripts = package_data["scripts"]
    assert isinstance(scripts, dict)
    assert "--win nsis --x64" in scripts["dist:win"]

    build = package_data["build"]
    assert isinstance(build, dict)
    win_config = build["win"]
    assert isinstance(win_config, dict)
    assert "nsis" in win_config["target"]
    assert win_config["signAndEditExecutable"] is False
    nsis_config = build["nsis"]
    assert isinstance(nsis_config, dict)
    assert nsis_config["oneClick"] is False
    assert nsis_config["allowToChangeInstallationDirectory"] is True

    workflow = REPO_ROOT / ".github" / "workflows" / "desktop-windows-installer.yml"
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in workflow_text
    assert "npm --prefix desktop run build:python" in workflow_text
    assert "npm --prefix desktop run stage" in workflow_text
    assert "npm --prefix desktop run dist:win" in workflow_text
    assert "desktop/dist/*.exe" in workflow_text
    assert "scistudio-windows-installer" in workflow_text


def test_portable_git_scripts_use_scistudio_skip_env_var() -> None:
    """Portable-git integrity bypass naming must not leak another project name."""
    powershell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.ps1").read_text(encoding="utf-8")
    shell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.sh").read_text(encoding="utf-8")

    combined = powershell_script + "\n" + shell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in powershell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in shell_script
    assert "SCIEASY_SKIP_GIT_SHA_VERIFY" not in combined
