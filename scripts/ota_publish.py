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
  strictly greater than what any shipped installer reports.
* ``base`` (the ``a.b.c`` from ``desktop/package.json``) is the installer
  baseline. The patch records ``requires.min_base = base``; a client whose
  installer base is older must reinstall instead of hot-patching.

Publishing is intentionally decoupled from local/dev builds: a developer builds
and tests locally (OTA disabled, see ``stage-resources`` ``ota-config.json``),
then runs this script from the *same checkout* to publish what was tested.

Usage::

    python scripts/ota_publish.py --channel alpha
    python scripts/ota_publish.py --channel alpha --dry-run
    python scripts/ota_publish.py --channel alpha --notes "Fix Export logs dialog"

Requires the GitHub CLI (``gh``) authenticated with write access to the repo,
except under ``--dry-run`` which only builds the snapshot and manifest locally.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

DEFAULT_REPO = "jiazhenz026/SciStudio"
REPO_ROOT = Path(__file__).resolve().parent.parent
STAGED_SRC = REPO_ROOT / "desktop" / "resources" / "backend" / "src"
DESKTOP_PACKAGE_JSON = REPO_ROOT / "desktop" / "package.json"

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)-build(\d+))?$")


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
) -> dict:
    """Assemble the manifest document the desktop client compares against.

    #1868: pass ``min_build`` to mark the patch mandatory — clients whose
    effective build is below it must take the update before they can continue
    (the desktop shell blocks startup). Omit it for an ordinary optional patch.
    """
    requires: dict[str, object] = {"min_base": base}
    if min_build is not None:
        requires["min_build"] = min_build
    return {
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_snapshot(src_dir: Path, out_path: Path) -> None:
    """Pack ``src_dir`` into ``out_path`` as a gzip tarball rooted at ``src/``.

    Extracting the archive yields ``<dest>/src/scistudio/...`` so the client can
    point ``PYTHONPATH`` at ``<dest>/src``. ``__pycache__`` is skipped to keep
    the snapshot lean and interpreter-agnostic.
    """

    def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(info.name).parts
        if "__pycache__" in parts or info.name.endswith(".pyc"):
            return None
        if "scistudio.egg-info" in parts:
            return None
        return info

    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(src_dir, arcname="src", filter=_filter)


# --------------------------------------------------------------------------- #
# gh / IO side
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
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


def upload_assets(repo: str, tag: str, files: list[Path]) -> None:
    result = _run(["gh", "release", "upload", tag, "--repo", repo, "--clobber", *map(str, files)])
    if result.returncode != 0:
        raise RuntimeError(f"Asset upload failed: {result.stderr.strip()}")


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

    latest = None if args.dry_run else fetch_latest_build(args.repo, tag)
    build = next_build_number(latest, baseline["build"])
    name = asset_name(build)

    workdir = Path(tempfile.mkdtemp(prefix="scistudio-ota-"))
    tarball = workdir / name
    print(f"Packing snapshot of {src_dir} -> {tarball.name} ...")
    make_snapshot(src_dir, tarball)

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

    if args.dry_run:
        print(f"\n[dry-run] artifacts left in {workdir}")
        print(f"[dry-run] manifest:\n{manifest_path.read_text()}")
        return 0

    if not args.yes:
        reply = input(f"\nUpload build {build} to {args.repo} ({tag})? [y/N] ").strip().lower()
        if reply not in {"y", "yes"}:
            print("Aborted.")
            return 1

    ensure_release(args.repo, tag, channel)
    upload_assets(args.repo, tag, [tarball, manifest_path])
    print(f"\nPublished OTA build {build} to {args.repo} release {tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
