#!/usr/bin/env python3
"""Publish a SciStudio desktop OTA hot-update patch.

A patch is a *full snapshot* of the staged backend source tree
(``desktop/resources/backend/src``, which already embeds the built frontend at
``scistudio/api/static``). It is uploaded as an asset on a rolling, per-channel
GitHub pre-release together with a ``manifest.json`` that the desktop client
(``desktop/main.js``) reads at launch.

Design (issue #1775):

* Patches are full snapshots, never deltas. A client several builds behind
  downloads the latest snapshot and replaces its source tree in one step.
* The build number is the patch sequence. Its source of truth is the published
  manifest, not any local counter: the next build is
  ``max(latest_published_build, installer_baseline_build) + 1`` so it is always
  strictly greater than what any shipped installer reports. ``--build`` names a
  number outright, for the one case the sequence cannot express (#2206): a
  reinstall notice aimed at clients the sequence has already moved past.
* ``base`` (the ``a.b.c`` from ``desktop/package.json``) is the installer
  baseline. The patch records ``requires.min_base = base``; a client whose
  installer base is older must reinstall instead of hot-patching.

Publishing is intentionally decoupled from local/dev builds: a developer builds
and tests locally (OTA disabled, see ``stage-resources`` ``ota-config.json``),
then runs this script from the *same checkout* to publish what was tested.

#2307: once the upload succeeds, the same build is published to PyPI as the
open-source wheel. The script dispatches ``.github/workflows/pypi-publish.yml``
for the checkout's HEAD commit, which builds ``scistudio==<base>a<build>`` with
the frontend and attaches it to the GitHub Release ``v<base>-<channel>``. See
``decide_pypi_publish`` for when it does not.

Usage::

    python scripts/ota_publish.py --channel alpha
    python scripts/ota_publish.py --channel alpha --dry-run
    python scripts/ota_publish.py --channel alpha --notes "Fix Export logs dialog"
    python scripts/ota_publish.py --channel alpha --no-pypi

Requires the GitHub CLI (``gh``) authenticated with write access to the repo,
except under ``--dry-run`` which only builds the snapshot and manifest locally.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

DEFAULT_REPO = "jiazhenz026/SciStudio"
REPO_ROOT = Path(__file__).resolve().parent.parent
STAGED_SRC = REPO_ROOT / "desktop" / "resources" / "backend" / "src"
DESKTOP_DIR = REPO_ROOT / "desktop"
REINSTALL_NOTICE_TEMPLATE = REPO_ROOT / "scripts" / "templates" / "reinstall-notice.html"

# #2097: the Electron shell rides inside the same snapshot as the backend tree,
# under ``shell/``. These are exactly the files the frozen bootstrap loader can
# hand over to. ``bootstrap.js`` is deliberately absent: it is the loader
# itself, it ships in the asar, and a patch must never be able to replace it.
# ``package.json`` is absent too -- the loader supplies the installed baseline,
# and a manifest inside the patch would be the patch describing itself.
SHELL_FILES = (
    "main.js",
    "menu.js",
    "ota.js",
    "runtime-port.js",
    # #2280: required by main.js and menu.js; a patch without it cannot load.
    "background-mode.js",
    # #2396: required by main.js; the in-app installer's decisions and helper scripts.
    "installer.js",
    "gui-capture.js",
    "preload.js",
    # #2280: the external-AI connection window and its sandboxed preload.
    "connection-preload.js",
    "splash.html",
    "connection.html",
    # splash.html references this with a RELATIVE src, so it has to travel with
    # the shell. Without it a patched splash resolves the logo against the patch
    # directory, finds nothing, and renders the loading screen with a broken
    # image -- observed on the first real patched launch. connection.html uses
    # it the same way.
    "assets/icon.png",
    # #2280: tray images, resolved next to main.js. Electron loads the @2x
    # siblings by itself on HiDPI displays, so they have to travel too.
    "assets/tray.png",
    "assets/tray@2x.png",
    "assets/trayTemplate.png",
    "assets/trayTemplate@2x.png",
)
DESKTOP_PACKAGE_JSON = REPO_ROOT / "desktop" / "package.json"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)-build(\d+))?$")

# #2307: the PyPI workflow's file name is fixed by the trusted publisher
# registered on PyPI, and it runs from main's copy of the workflow.
PYPI_WORKFLOW = "pypi-publish.yml"
PYPI_WORKFLOW_BRANCH = "main"
PYPI_PROJECT = "scistudio"

# The PyPI version comes from the same deriver the wheel is stamped with, so the
# number printed here is the number the workflow publishes.
_SRC_DIR = REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from scistudio.version import format_pep440  # noqa: E402


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested in tests/scripts/test_ota_publish.py)
# --------------------------------------------------------------------------- #
def parse_version(version: str) -> dict:
    """Parse a SciStudio display/SemVer version into base/channel/build.

    Accepts ``a.b.c-<channel>-build<NNNN>`` (prerelease) or ``a.b.c`` (stable).
    """
    match = _VERSION_RE.match(version.strip())
    if not match:
        raise ValueError(f"Unrecognized version string: {version!r}")
    major, minor, patch, channel, build = match.groups()
    return {
        "base": f"{major}.{minor}.{patch}",
        "channel": channel or "stable",
        "build": int(build) if build is not None else 0,
    }


def next_build_number(latest_published_build: int | None, baseline_build: int) -> int:
    """Return the next monotonic patch build number.

    The patch sequence must stay strictly above both the latest already-published
    patch and the installer baseline, so a fresh install (whose effective build is
    the baseline) always sees the first patch as newer.
    """
    candidates = [baseline_build]
    if latest_published_build is not None:
        candidates.append(latest_published_build)
    return max(candidates) + 1


def resolve_build_number(
    override: int | None,
    latest_published_build: int | None,
    baseline_build: int,
    min_base: str | None,
) -> int:
    """Pick the build number this publish will carry.

    Without an override the sequence is monotonic (``next_build_number``).

    #2206: the reinstall notice reaches old-base clients by sitting in a build
    *window* -- strictly above the last build those clients applied, and at or
    below the new installer's baseline, so the new-base population evaluates
    ``up-to-date`` and keeps its working SPA. Once an ordinary patch for the new
    base is published, the monotonic sequence has walked past that window and
    the notice can only be restored by naming its number.

    Going backwards is therefore legitimate, and only for that case: it is
    refused unless ``--min-base`` names the older population the publish is
    aimed at. A build at or below the sequence with no such target would land
    on nobody at best, and replace a working SPA with a notice at worst.
    """
    if override is None:
        return next_build_number(latest_published_build, baseline_build)
    if override < 1:
        raise ValueError(f"--build must be a positive build number; got {override}.")
    sequence = max(baseline_build, latest_published_build or 0)
    if override <= sequence and not min_base:
        raise ValueError(
            f"--build {override} is at or below the current sequence ({sequence}). "
            "Only a migration notice aimed at an older base may publish backwards; "
            "pass --min-base <that base> as well, or drop --build."
        )
    return override


def asset_name(build: int) -> str:
    return f"backend-build{build}.tar.gz"


def asset_url(repo: str, tag: str, name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{name}"


def channel_tag(channel: str) -> str:
    return f"ota-{channel}"


def build_manifest(
    *,
    channel: str,
    base: str,
    build: int,
    url: str,
    sha256: str,
    size: int,
    notes: str,
    published_at: str,
    min_build: int | None = None,
    min_base: str | None = None,
    installer: dict | None = None,
) -> dict:
    """Assemble the manifest document the desktop client compares against.

    #1868: pass ``min_build`` to mark the patch mandatory — clients whose
    effective build is below it must take the update before they can continue
    (the desktop shell blocks startup). Omit it for an ordinary optional patch.

    #2169: ``min_base`` defaults to this build's own base, which is right for an
    ordinary patch and wrong for the one case ``--reinstall-notice`` exists for.
    After a base bump the derived value is the *new* base, so every client on the
    old base evaluates to ``incompatible`` rather than ``patch`` — and the
    incompatible branch never downloads anything, so the notice page is never
    fetched and the user gets the plain native dialog the notice was written to
    avoid. Pass ``min_base`` at or below the target clients' base to reach them.

    #2396: ``installer`` (from ``installer_from_release``) names the next
    installer per platform. A shell that knows the field offers to download and
    install it; older shells ignore it.
    """
    requires: dict[str, object] = {"min_base": min_base or base}
    if min_build is not None:
        requires["min_build"] = min_build
    manifest: dict[str, object] = {
        "channel": channel,
        "base": base,
        "build": build,
        "requires": requires,
        "url": url,
        "sha256": sha256,
        "size": size,
        "notes": notes,
        "published_at": published_at,
    }
    if installer is not None:
        manifest["installer"] = installer
    return manifest


# #2396: the installer asset each platform key maps to, by the file names the
# desktop builds emit (electron-builder artifactName settings in
# desktop/package.json). Every key must be present: the owner scoped the in-app
# installer to all three platforms, and a manifest that names an installer some
# users cannot download strands them.
#
# The Windows name also accepts electron-builder's default "SciStudio Setup
# <version>.exe", and the dots GitHub substitutes for its spaces on upload, so a
# release built before nsis.artifactName was pinned still maps. The AppImage
# accepts the "-x86_64" suffix a forced arch would add.
_INSTALLER_VERSION = r"(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z]+-build\d+)?)"
INSTALLER_ASSET_PATTERNS: dict[str, re.Pattern[str]] = {
    "darwin-arm64": re.compile(rf"^SciStudio-{_INSTALLER_VERSION}-arm64\.dmg$"),
    "darwin-x64": re.compile(rf"^SciStudio-{_INSTALLER_VERSION}-x64\.dmg$"),
    "win32-x64": re.compile(rf"^SciStudio[-. ]Setup[-. ]{_INSTALLER_VERSION}\.exe$"),
    "linux-x64": re.compile(rf"^SciStudio-{_INSTALLER_VERSION}(?:-x86_64)?\.AppImage$"),
}


def installer_from_release(release: dict[str, Any]) -> dict[str, Any]:
    """Build the manifest ``installer`` field from a GitHub release (#2396).

    *release* is the ``gh api repos/<repo>/releases/tags/<tag>`` document. Each
    platform's asset is matched by name; its URL, size and GitHub-computed
    ``sha256`` digest go into the field, so nothing is downloaded here. Raises
    ``ValueError`` when the release is a draft (its assets are not public), when
    a platform has no asset, when an asset has no digest, or when the assets
    disagree about the version.
    """
    tag = release.get("tag_name")
    if release.get("draft"):
        raise ValueError(f"release {tag} is a draft; its assets are not downloadable")
    assets: dict[str, dict[str, Any]] = {}
    versions: set[str] = set()
    for key, pattern in INSTALLER_ASSET_PATTERNS.items():
        matches = [
            (asset, match)
            for asset in release.get("assets", [])
            if (match := pattern.match(str(asset.get("name", "")))) is not None
        ]
        if len(matches) != 1:
            found = "no asset" if not matches else f"{len(matches)} assets"
            raise ValueError(f"release {tag}: {found} for {key} ({pattern.pattern})")
        asset, match = matches[0]
        versions.add(match.group("version"))
        digest = str(asset.get("digest") or "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"asset {asset['name']} has no sha256 digest")
        url = str(asset.get("browser_download_url") or "")
        if not url.startswith("https://"):
            raise ValueError(f"asset {asset['name']} has no https download URL")
        assets[key] = {"url": url, "sha256": digest.split(":", 1)[1], "size": int(asset["size"])}
    if len(versions) != 1:
        raise ValueError(f"release {tag}: installer assets disagree on the version: {sorted(versions)}")
    version = versions.pop()
    parse_version(version)
    installer: dict[str, Any] = {"version": version, "assets": assets}
    page = str(release.get("html_url") or "")
    if page.startswith("https://"):
        installer["release_page"] = page
    return installer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SPA_INDEX_ARCNAME = "src/scistudio/api/static/index.html"


def render_reinstall_notice(download_url: str, version_line: str) -> str:
    """Render the reinstall notice page (#2097, spec section 8.1).

    A client that cannot be hot-updated any further has to be told to reinstall.
    Doing that through the mandatory *incompatible* dialog puts the address in a
    native ``dialog.showMessageBox``, which renders plain text: not clickable and
    not selectable, so the user must retype it — and that dialog cannot be
    changed, because it is drawn by the one part a patch cannot replace.

    Publishing it as a mandatory *patch* instead delivers an ordinary web page,
    where the address selects and a button copies it. The manifest must keep
    ``min_base`` at or below the target clients' base so the decision is
    ``patch`` rather than ``incompatible``, with ``min_build`` set to make it
    mandatory.
    """
    if not REINSTALL_NOTICE_TEMPLATE.is_file():
        raise SystemExit(f"Missing template: {REINSTALL_NOTICE_TEMPLATE}")
    html = REINSTALL_NOTICE_TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__DOWNLOAD_URL__", download_url).replace("__VERSION_LINE__", version_line)


def notice_version_line(min_base: str | None, build_base: str, build: int) -> str:
    """The "Installed X · update N" line at the foot of the reinstall notice.

    #2206: it names what the *reader* is running, and the reader is the old-base
    population ``--min-base`` selects -- not this build's own base, which is the
    version they are being sent to download. Taking it from the publishing
    checkout put "Installed 0.3.4" in front of every 0.3.3 user.
    """
    return f"Installed {min_base or build_base} · update {build}"


def shell_sources(desktop_dir: Path = DESKTOP_DIR) -> list[Path]:
    """The Electron shell files a snapshot carries (#2097).

    Raises if one is missing rather than publishing a shell the loader would
    refuse: a ``shell/`` directory without ``main.js`` fails ``isShellDir`` on
    the client and silently falls back to the baseline for every user.
    """
    paths = [desktop_dir / name for name in SHELL_FILES]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"Missing desktop shell files in {desktop_dir}: {', '.join(missing)}")
    return paths


def make_snapshot(
    src_dir: Path,
    out_path: Path,
    desktop_dir: Path = DESKTOP_DIR,
    reinstall_notice: str | None = None,
) -> None:
    """Pack a snapshot of the backend tree and the Electron shell.

    The tarball is rooted at ``src/`` and ``shell/``: extracting it yields
    ``<dest>/src/scistudio/...`` so the client can point ``PYTHONPATH`` at
    ``<dest>/src``, and ``<dest>/shell/main.js`` for the bootstrap loader to
    require. ``__pycache__`` is skipped to keep the snapshot lean and
    interpreter-agnostic.

    Both halves share one build number on purpose (#2097): shell and backend are
    released together, so coupling them makes a build mean "all of this app's
    interpreted code" instead of creating a shell/backend compatibility matrix.
    """

    def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(info.name).parts
        if "__pycache__" in parts or info.name.endswith(".pyc"):
            return None
        if "scistudio.egg-info" in parts:
            return None
        # The notice replaces the SPA entry point in the ARCHIVE only; the
        # staged tree on disk is never touched, so a checkout cannot be left
        # quietly shipping the notice as its real frontend.
        if reinstall_notice is not None and info.name.replace("\\", "/") == SPA_INDEX_ARCNAME:
            return None
        return info

    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(src_dir, arcname="src", filter=_filter)
        if reinstall_notice is not None:
            payload = reinstall_notice.encode("utf-8")
            info = tarfile.TarInfo(SPA_INDEX_ARCNAME)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        for shell_file in shell_sources(desktop_dir):
            arcname = f"shell/{shell_file.relative_to(desktop_dir).as_posix()}"
            tar.add(shell_file, arcname=arcname)


# --------------------------------------------------------------------------- #
# #2307: every OTA build also publishes the open-source wheel to PyPI.
# --------------------------------------------------------------------------- #
PYPI_TRIGGER = "trigger"
PYPI_SKIP = "skip"
PYPI_REFUSE = "refuse"


class PypiDecision(NamedTuple):
    """What an OTA publish does about PyPI once its upload has succeeded.

    ``trigger`` dispatches the workflow and ``skip`` is a deliberate no.
    ``refuse`` means the build should reach PyPI but cannot from here; the
    reason says what to fix before running the workflow by hand.

    A NamedTuple rather than a dataclass: this script is also loaded by file
    path (the tests do), and a dataclass under postponed annotations needs its
    module registered in ``sys.modules``.
    """

    action: str
    reason: str


def pypi_version(base: str, channel: str, build: int) -> str:
    """The version the workflow publishes: OTA build 29 of 0.3.4 alpha is ``0.3.4a29``."""
    return format_pep440(base, channel, build)


def pypi_json_url(version: str) -> str:
    return f"https://pypi.org/pypi/{PYPI_PROJECT}/{version}/json"


def decide_pypi_publish(
    *,
    dry_run: bool,
    no_pypi: bool,
    reinstall_notice: bool,
    build: int,
    latest_published_build: int | None,
    baseline_build: int,
    version: str,
    on_pypi: Callable[[], bool | None],
    head_on_main: Callable[[], bool],
) -> PypiDecision:
    """Decide whether this OTA build goes on to PyPI (#2307).

    PyPI keeps every version forever -- it can be yanked, never replaced -- so
    every rule errs towards not publishing. The rules run cheapest first; the
    two that need the network or git are callables, consulted only when nothing
    earlier has decided.

    * ``--dry-run`` publishes nothing, and ``--no-pypi`` opts out outright.
    * A reinstall notice swaps the snapshot's SPA for a page telling old clients
      to reinstall. That build number does not stand for a product release.
    * A build at or below the channel's sequence (the number
      ``resolve_build_number`` guards) is a backfill: PyPI may already hold that
      version, and otherwise would list it out of order.
    * A version PyPI already has is skipped. ``None`` from ``on_pypi`` means PyPI
      could not be asked; the workflow checks again before it builds.
    * HEAD not on ``origin/main`` is refused. The workflow builds the commit
      from GitHub, which cannot build an unpushed commit and must not publish an
      unmerged one.
    """
    if dry_run:
        return PypiDecision(PYPI_SKIP, "--dry-run publishes nothing")
    if no_pypi:
        return PypiDecision(PYPI_SKIP, "--no-pypi was passed")
    if reinstall_notice:
        return PypiDecision(PYPI_SKIP, "this snapshot's SPA is the reinstall notice, not the product")
    sequence = max(baseline_build, latest_published_build or 0)
    if build <= sequence:
        return PypiDecision(
            PYPI_SKIP,
            f"build {build} is at or below the channel's latest build ({sequence}); a backfill must not "
            f"publish {version}, which PyPI may already hold or would list out of order",
        )
    exists = on_pypi()
    if exists:
        return PypiDecision(PYPI_SKIP, f"scistudio {version} is already on PyPI, and a PyPI version cannot be replaced")
    if not head_on_main():
        return PypiDecision(
            PYPI_REFUSE,
            "HEAD is not on origin/main; the workflow builds the commit from GitHub, so push and merge it first",
        )
    if exists is None:
        return PypiDecision(
            PYPI_TRIGGER, f"PyPI could not be asked about {version}; the workflow checks again before building"
        )
    return PypiDecision(PYPI_TRIGGER, f"scistudio {version} is not on PyPI yet")


def pypi_workflow_command(repo: str, sha: str, build: int, channel: str) -> list[str]:
    """The ``gh workflow run`` that publishes commit *sha* as this build (#2307).

    ``--ref`` only picks which branch's copy of the workflow runs. The commit it
    builds is the ``ref`` input, pinned to the SHA the snapshot was taken from.
    """
    return [
        "gh",
        "workflow",
        "run",
        PYPI_WORKFLOW,
        "--repo",
        repo,
        "--ref",
        PYPI_WORKFLOW_BRANCH,
        "-f",
        f"ref={sha}",
        "-f",
        f"build_number={build}",
        "-f",
        f"channel={channel}",
    ]


# --------------------------------------------------------------------------- #
# gh / IO side
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)


def fetch_latest_build(repo: str, tag: str) -> int | None:
    """Return the build number of the currently published manifest, or None."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "manifest.json"
        result = _run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                repo,
                "--pattern",
                "manifest.json",
                "--output",
                str(out),
                "--clobber",
            ]
        )
        if result.returncode != 0 or not out.exists():
            return None
        try:
            return int(json.loads(out.read_text())["build"])
        except (ValueError, KeyError, json.JSONDecodeError):
            return None


def ensure_release(repo: str, tag: str, channel: str) -> None:
    """Create the rolling per-channel pre-release if it does not exist yet."""
    exists = _run(["gh", "release", "view", tag, "--repo", repo]).returncode == 0
    if exists:
        return
    result = _run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--prerelease",
            "--title",
            f"SciStudio OTA ({channel})",
            "--notes",
            f"Rolling OTA channel for '{channel}'. Assets are managed by scripts/ota_publish.py; do not edit manually.",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create release {tag}: {result.stderr.strip()}")


def fetch_release(repo: str, tag: str) -> dict[str, Any]:
    """The GitHub release document for *tag* (#2396). Raises when it cannot be read."""
    result = _run(["gh", "api", f"repos/{repo}/releases/tags/{tag}"])
    if result.returncode != 0:
        raise RuntimeError(f"Could not read release {tag}: {result.stderr.strip()}")
    return dict(json.loads(result.stdout))


def upload_assets(repo: str, tag: str, files: list[Path]) -> None:
    result = _run(["gh", "release", "upload", tag, "--repo", repo, "--clobber", *map(str, files)])
    if result.returncode != 0:
        raise RuntimeError(f"Asset upload failed: {result.stderr.strip()}")


def version_on_pypi(version: str, timeout: float = 10.0) -> bool | None:
    """True when PyPI has *version*, False when it does not, None when PyPI could not be asked."""
    try:
        with urllib.request.urlopen(pypi_json_url(version), timeout=timeout) as response:
            return bool(response.status == 200)
    except urllib.error.HTTPError as error:
        return False if error.code == 404 else None
    except OSError:
        return None


def head_sha(repo_root: Path = REPO_ROOT) -> str | None:
    result = _run(["git", "-C", str(repo_root), "rev-parse", "HEAD"])
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def head_on_main(repo_root: Path = REPO_ROOT) -> bool:
    """Whether HEAD is on ``origin/main``, after refreshing that ref.

    The refresh is best effort. Offline, the check runs against the ref as it
    stands, which can only make it stricter: a commit merged since the last
    fetch reads as unmerged and is refused, never the other way round.
    """
    _run(["git", "-C", str(repo_root), "fetch", "--quiet", "origin", PYPI_WORKFLOW_BRANCH])
    result = _run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", "HEAD", f"origin/{PYPI_WORKFLOW_BRANCH}"]
    )
    return result.returncode == 0


def trigger_pypi_publish(
    *,
    repo: str,
    channel: str,
    base: str,
    build: int,
    latest_published_build: int | None,
    baseline_build: int,
    dry_run: bool = False,
    no_pypi: bool = False,
    reinstall_notice: bool = False,
) -> PypiDecision:
    """Dispatch the PyPI workflow for a build that has just been published (#2307).

    Never raises for a PyPI-side problem. By the time this runs the OTA build is
    live, and failing the command would suggest it was not. Every outcome prints
    what happened and, when the workflow did not run, the command to run it.
    """
    version = pypi_version(base, channel, build)
    decision = decide_pypi_publish(
        dry_run=dry_run,
        no_pypi=no_pypi,
        reinstall_notice=reinstall_notice,
        build=build,
        latest_published_build=latest_published_build,
        baseline_build=baseline_build,
        version=version,
        on_pypi=lambda: version_on_pypi(version),
        head_on_main=head_on_main,
    )
    if decision.action == PYPI_SKIP:
        print(f"\nPyPI: skipped -- {decision.reason}.")
        return decision

    sha = head_sha()
    command = pypi_workflow_command(repo, sha or "<full commit sha>", build, channel)
    if decision.action == PYPI_REFUSE or sha is None:
        reason = decision.reason if decision.action == PYPI_REFUSE else "HEAD could not be resolved"
        print(f"\nPyPI: NOT triggered for scistudio {version} -- {reason}.")
        print("The OTA build is published. Once the commit is on main, publish it with:")
        print(f"  {shlex.join(command)}")
        return PypiDecision(PYPI_REFUSE, reason)

    print(f"\nPyPI: publishing scistudio {version} ({decision.reason}).")
    print(f"  $ {shlex.join(command)}")
    result = _run(command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        print(f"PyPI: the workflow was NOT dispatched: {detail}")
        print("The OTA build is published. Fix the cause and run the command above.")
        return PypiDecision(PYPI_REFUSE, f"gh workflow run failed: {detail}")
    if result.stdout.strip():
        print(result.stdout.strip())
    print(f"  watch: gh run list --repo {repo} --workflow {PYPI_WORKFLOW} --limit 1")
    print(f"         gh run watch <run-id> --repo {repo}")
    return decision


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish a SciStudio desktop OTA patch.")
    parser.add_argument(
        "--channel",
        help="OTA channel (e.g. alpha, beta). Defaults to the channel in desktop/package.json.",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name of the GitHub repo.")
    parser.add_argument("--notes", default="", help="Human-readable patch notes for the manifest.")
    parser.add_argument(
        "--min-build",
        type=int,
        default=None,
        help=(
            "#1868: mark this patch mandatory. Clients whose effective build is below "
            "this value must apply the update before they can continue (the desktop "
            "shell blocks startup). Omit for an ordinary optional patch."
        ),
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=STAGED_SRC,
        help="Staged backend source tree to snapshot (default: the desktop build output).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the snapshot and manifest locally without creating/uploading a release.",
    )
    parser.add_argument(
        "--min-base",
        metavar="A.B.C",
        default=None,
        help=(
            "#2169: override requires.min_base, which otherwise derives from this build's "
            "own base. Needed whenever the base moved and older clients must still be "
            "reached: set it at or below their base so they evaluate the manifest as a "
            "patch rather than incompatible. Pair with --reinstall-notice."
        ),
    )
    parser.add_argument(
        "--build",
        type=int,
        default=None,
        help=(
            "#2206: publish this exact build number instead of the next one in the "
            "monotonic sequence. Needed to restore a migration notice after an "
            "ordinary patch has advanced the channel past the notice's build window: "
            "pick a number above the last build the old-base clients applied and at or "
            "below the new installer's baseline, so the new-base population still "
            "evaluates up-to-date. Requires --min-base when it goes backwards."
        ),
    )
    parser.add_argument(
        "--reinstall-notice",
        metavar="URL",
        default=None,
        help=(
            "#2097: replace the snapshot's SPA with the reinstall notice pointing at URL. "
            "Use for the migration patch that tells clients to download a build they cannot "
            "reach by OTA. Publish it as a mandatory PATCH (min_base at or below their base, "
            "min_build set), not as incompatible -- a native dialog cannot be copied from."
        ),
    )
    parser.add_argument(
        "--no-pypi",
        action="store_true",
        help=(
            "#2307: do not dispatch pypi-publish.yml after the upload. By default every OTA "
            "build is also published to PyPI as scistudio <base>a<build>, except dry runs, "
            "reinstall notices, backfilled builds, versions PyPI already has, and a HEAD "
            "that is not on origin/main."
        ),
    )
    parser.add_argument(
        "--installer-release",
        metavar="TAG",
        default=None,
        help=(
            "#2396: name the next installer in the manifest, from the GitHub release TAG "
            "(e.g. v0.3.5-beta). Shells that know the field offer to download and install it. "
            "The release must be published with a dmg for arm64 and x64, a Windows setup exe "
            "and an AppImage."
        ),
    )
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt before uploading.")
    args = parser.parse_args(argv)

    src_dir: Path = args.src
    if not (src_dir / "scistudio").is_dir():
        parser.error(
            f"No staged source at {src_dir} (expected a 'scistudio' package). Run the desktop build/stage step first."
        )

    baseline = parse_version(json.loads(DESKTOP_PACKAGE_JSON.read_text())["version"])
    channel = args.channel or baseline["channel"]
    if channel == "stable":
        parser.error("Refusing to publish an OTA patch on the 'stable' channel; pass --channel.")
    tag = channel_tag(channel)

    # A dry run normally skips the network and reports a meaningless build. With
    # an explicit --build the number is the thing under review, and the guard that
    # accepts it reads the latest published build -- so fetch it either way, or the
    # rehearsal would not exercise the check the real publish makes.
    latest = fetch_latest_build(args.repo, tag) if args.build is not None or not args.dry_run else None
    try:
        build = resolve_build_number(args.build, latest, baseline["build"], args.min_base)
    except ValueError as error:
        parser.error(str(error))
    name = asset_name(build)

    workdir = Path(tempfile.mkdtemp(prefix="scistudio-ota-"))
    tarball = workdir / name
    notice = None
    if args.reinstall_notice:
        notice = render_reinstall_notice(
            args.reinstall_notice, notice_version_line(args.min_base, baseline["base"], build)
        )
        print(f"Snapshot SPA replaced with the reinstall notice -> {args.reinstall_notice}")

    installer = None
    if args.installer_release:
        try:
            installer = installer_from_release(fetch_release(args.repo, args.installer_release))
        except (RuntimeError, ValueError) as error:
            parser.error(f"--installer-release: {error}")
        print(f"Manifest names installer {installer['version']} from {args.installer_release}")

    print(f"Packing snapshot of {src_dir} -> {tarball.name} ...")
    make_snapshot(src_dir, tarball, reinstall_notice=notice)

    digest = sha256_file(tarball)
    size = tarball.stat().st_size
    manifest = build_manifest(
        channel=channel,
        base=baseline["base"],
        build=build,
        url=asset_url(args.repo, tag, name),
        sha256=digest,
        size=size,
        notes=args.notes,
        published_at=_utc_now_iso(),
        min_build=args.min_build,
        min_base=args.min_base,
        installer=installer,
    )
    manifest_path = workdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"\nchannel={channel} base={baseline['base']} build={build} "
        f"(baseline build {baseline['build']}, latest published "
        f"{latest if latest is not None else 'none'})"
    )
    print(f"  asset : {name} ({size} bytes)")
    print(f"  sha256: {digest}")
    print(f"  url   : {manifest['url']}")

    pypi_args = {
        "repo": args.repo,
        "channel": channel,
        "base": baseline["base"],
        "build": build,
        "latest_published_build": latest,
        "baseline_build": baseline["build"],
        "no_pypi": args.no_pypi,
        "reinstall_notice": args.reinstall_notice is not None,
    }

    if args.dry_run:
        print(f"\n[dry-run] artifacts left in {workdir}")
        print(f"[dry-run] manifest:\n{manifest_path.read_text()}")
        trigger_pypi_publish(dry_run=True, **pypi_args)
        return 0

    if not args.yes:
        reply = input(f"\nUpload build {build} to {args.repo} ({tag})? [y/N] ").strip().lower()
        if reply not in {"y", "yes"}:
            print("Aborted.")
            return 1

    ensure_release(args.repo, tag, channel)
    upload_assets(args.repo, tag, [tarball, manifest_path])
    print(f"\nPublished OTA build {build} to {args.repo} release {tag}.")
    # #2307: only after the upload succeeded. The OTA build is live either way;
    # a PyPI problem is printed, never raised.
    trigger_pypi_publish(**pypi_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
