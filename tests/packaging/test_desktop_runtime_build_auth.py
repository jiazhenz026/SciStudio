"""The desktop runtime builds must authenticate their GitHub API query (#2162).

All three build scripts ask the GitHub releases API which python-build-standalone
asset to fetch. Unauthenticated, that call draws on a rate limit shared by every
Actions runner on the same egress IP — 60 requests an hour for the whole pool —
which is how a 0.3.4 macOS build died 0.24 seconds in with
``curl: (56) ... 403``, before signing was even attempted. Earlier builds had
succeeded, so the difference was timing rather than configuration: nothing about
the repository changed, and nothing warned.

These are source-level assertions because the alternative is a release build that
fails on someone else's traffic. They cover both halves of the fix — the scripts
sending the header, and the workflows actually passing a token, which none of
them did.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "desktop" / "scripts"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

RELEASES_API = "api.github.com/repos/astral-sh/python-build-standalone/releases"

SHELL_SCRIPTS = ("build-python-runtime-macos.sh", "build-python-runtime-linux.sh")
BUILD_WORKFLOWS = (
    "desktop-macos-dmg.yml",
    "desktop-linux-appimage.yml",
    "desktop-windows-installer.yml",
)


@pytest.mark.parametrize("name", SHELL_SCRIPTS)
def test_shell_scripts_send_an_authorization_header(name: str) -> None:
    body = (SCRIPTS / name).read_text(encoding="utf-8")
    assert RELEASES_API in body, f"{name} no longer queries the releases API"
    assert "Authorization: Bearer" in body, f"{name} queries the API unauthenticated"


def test_powershell_script_sends_an_authorization_header() -> None:
    body = (SCRIPTS / "build-python-runtime.ps1").read_text(encoding="utf-8")
    assert RELEASES_API in body, "the Windows script no longer queries the releases API"
    assert 'Authorization" ] = "Bearer' in body or 'Authorization"] = "Bearer' in body, (
        "the Windows script queries the API unauthenticated"
    )


@pytest.mark.parametrize("name", (*SHELL_SCRIPTS, "build-python-runtime.ps1"))
def test_scripts_still_run_without_a_token(name: str) -> None:
    """A developer running these locally has no token; the header must be optional.

    Making the header unconditional would trade a CI failure for a local one.
    """
    body = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "GITHUB_TOKEN" in body and "GH_TOKEN" in body, f"{name} should read both token variables"
    # Some form of "only when set" guard has to be present.
    assert re.search(r'if \[ -n "\$GH_API_TOKEN" \]|if \(\$GhToken\)', body), (
        f"{name} must omit the header when no token is set"
    )


@pytest.mark.parametrize("name", BUILD_WORKFLOWS)
def test_workflows_pass_a_token_to_the_runtime_build(name: str) -> None:
    """The scripts can read a token, but Actions does not supply one by default."""
    body = (WORKFLOWS / name).read_text(encoding="utf-8")
    assert "build:python" in body, f"{name} no longer builds the runtime"
    assert "GITHUB_TOKEN: ${{ github.token }}" in body, f"{name} does not pass a token to the runtime build step"


@pytest.mark.parametrize("name", (*SHELL_SCRIPTS, "build-python-runtime.ps1"))
def test_the_asset_download_stays_unauthenticated(name: str) -> None:
    """Only the API query is authenticated.

    The download uses ``browser_download_url``, which is public CDN; sending an
    Authorization header there is at best pointless and at worst a redirect that
    leaks the token to a third-party host.
    """
    body = (SCRIPTS / name).read_text(encoding="utf-8")
    download_lines = [
        line
        for line in body.splitlines()
        if ("ASSET_URL" in line or "AssetUrl" in line)
        and ("curl" in line or "Invoke-WebRequest" in line or "WebClient" in line)
    ]
    for line in download_lines:
        assert "Authorization" not in line, f"{name}: the asset download must not be authenticated"
