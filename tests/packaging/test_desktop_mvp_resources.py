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


def test_desktop_runtime_env_adds_common_user_cli_paths() -> None:
    """Dock/Finder-launched desktop sessions must still find user CLIs."""
    main_js = (DESKTOP_DIR / "main.js").read_text(encoding="utf-8")

    assert "commonUserCliDirs" in main_js
    assert 'path.join(userHome, ".local", "bin")' in main_js
    assert 'path.join(userHome, ".npm-global", "bin")' in main_js
    assert '"/opt/homebrew/bin"' in main_js
    assert '"/usr/local/bin"' in main_js


def test_desktop_runtime_env_imports_macos_login_shell_environment() -> None:
    """macOS packaged apps must pass login-shell auth env to provider CLIs."""
    main_js = (DESKTOP_DIR / "main.js").read_text(encoding="utf-8")

    assert "spawnSync" in main_js
    assert "function macLoginShellEnv()" in main_js
    assert 'process.platform !== "darwin"' in main_js
    assert "/usr/bin/env -0" in main_js
    assert "__SCISTUDIO_ENV_START__" in main_js
    assert "...loginShellEnv" in main_js
    assert 'pathEntries.push(loginShellEnv.PATH || "")' in main_js


def test_desktop_dev_runner_points_vite_proxy_at_runtime_port() -> None:
    """Desktop dev must not proxy PTY WebSockets to an unrelated backend."""
    start_dev_js = (DESKTOP_DIR / "scripts" / "start-dev.js").read_text(encoding="utf-8")

    assert "const apiProxyTarget" in start_dev_js
    assert "SCISTUDIO_API_PROXY" in start_dev_js
    assert "`http://127.0.0.1:${runtimePort}`" in start_dev_js
    assert "SCISTUDIO_API_PROXY: apiProxyTarget" in start_dev_js


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
    # #1747: local manual builds are arm64-only; the bundled Python (built per
    # `uname -m`) and the Electron shell must share one architecture.
    assert "--mac dmg --arm64" in scripts["dist:dmg"]

    script = DESKTOP_DIR / "scripts" / "build-python-runtime-macos.sh"
    content = script.read_text(encoding="utf-8")
    assert "python-build-standalone" in content
    assert "resources/python" in content or 'PYTHON_ROOT="$RESOURCES_ROOT/python"' in content
    assert 'pip install --no-warn-script-location "$REPO_ROOT"' in content
    assert "import scistudio, fastapi, uvicorn, pty" in content

    workflow = REPO_ROOT / ".github" / "workflows" / "desktop-macos-dmg.yml"
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow_text
    assert "pull_request:" not in workflow_text
    assert "push:" not in workflow_text
    # #1747: arm64 (Apple Silicon) runner so the whole chain is arm64-consistent
    # (an Intel runner would bundle x64 Python in an arm64 shell).
    assert "runs-on: macos-15\n" in workflow_text
    assert "macos-15-intel" not in workflow_text
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
    assert "workflow_dispatch:" in workflow_text
    assert "pull_request:" not in workflow_text
    assert "push:" not in workflow_text
    assert "runs-on: windows-latest" in workflow_text
    assert "npm --prefix desktop run build:python" in workflow_text
    assert "npm --prefix desktop run stage" in workflow_text
    assert "npm --prefix desktop run dist:win" in workflow_text
    assert "desktop/dist/*.exe" in workflow_text
    assert "scistudio-windows-installer" in workflow_text


def test_stage_scripts_refresh_packaged_spa_static() -> None:
    """#1747: both staging scripts must refresh the packaged SPA
    (``scistudio/api/static``) from the freshly built ``frontend/dist``.

    A bundled desktop app serves ONLY ``scistudio/api/static`` (see
    ``scistudio.api.app._resolve_spa_static_dir`` in ``SCISTUDIO_BUNDLED`` mode),
    and that repo copy is a gitignored build artifact the wheel build hook skips
    refreshing once populated. If either staging path (POSIX ``stage-resources.sh``
    or Windows ``stage-resources.ps1``) omits the refresh, that platform's
    installer ships a stale SPA. The two scripts must stay in sync.
    """
    sh = (DESKTOP_DIR / "scripts" / "stage-resources.sh").read_text(encoding="utf-8")
    ps1 = (DESKTOP_DIR / "scripts" / "stage-resources.ps1").read_text(encoding="utf-8")
    # POSIX path uses forward slashes; PowerShell path uses backslashes.
    assert "scistudio/api/static" in sh
    assert "scistudio\\api\\static" in ps1


def test_desktop_declares_packaged_app_icons() -> None:
    """The desktop shell should not ship with the default Electron icon."""
    package_data = _desktop_package_json()
    build = package_data["build"]
    assert isinstance(build, dict)

    directories = build["directories"]
    assert isinstance(directories, dict)
    assert directories["buildResources"] == "assets"

    files = build["files"]
    assert isinstance(files, list)
    assert "assets/icon.png" in files

    win_config = build["win"]
    assert isinstance(win_config, dict)
    assert win_config["icon"] == "icon.ico"

    mac_config = build["mac"]
    assert isinstance(mac_config, dict)
    assert mac_config["icon"] == "icon.icns"

    assets_dir = DESKTOP_DIR / "assets"
    for filename in ("icon.svg", "icon.png", "icon.ico", "icon.icns"):
        asset = assets_dir / filename
        assert asset.is_file()
        assert asset.stat().st_size > 0

    source_svg = (assets_dir / "icon.svg").read_text(encoding="utf-8")
    assert "<svg" in source_svg
    assert 'aria-label="SciStudio"' in source_svg

    main_js = (DESKTOP_DIR / "main.js").read_text(encoding="utf-8")
    assert "function appIconPath()" in main_js
    assert '"assets", "icon.png"' in main_js
    assert "icon: appIconPath()" in main_js


def test_portable_git_scripts_use_scistudio_skip_env_var() -> None:
    """Portable-git integrity bypass naming must not leak another project name."""
    powershell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.ps1").read_text(encoding="utf-8")
    shell_script = (DESKTOP_DIR / "scripts" / "fetch-git-portable.sh").read_text(encoding="utf-8")

    combined = powershell_script + "\n" + shell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in powershell_script
    assert "SCISTUDIO_SKIP_GIT_SHA_VERIFY" in shell_script
    assert "SCIEASY_SKIP_GIT_SHA_VERIFY" not in combined
