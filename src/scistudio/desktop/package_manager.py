"""In-app Package Manager services (issue #1784).

This module is the IO side of the per-package OTA flow whose pure decision
logic lives in :mod:`scistudio.desktop.package_ota`. It backs the desktop
Package Manager UI: listing installed packages, checking each one's
self-declared OTA source for newer releases, and downloading/verifying/staging,
rolling back, or deleting a package.

Packages self-declare their update source via :class:`PackageInfo.ota`
(``manifest_url`` + ``channel``); core never maintains a package list. The
check iterates the *loaded* registry packages, fetches each manifest, and
compares by semver against the running core base.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from scistudio.blocks.base.package_info import PackageInfo
from scistudio.desktop import paths
from scistudio.desktop.package_installer import install_local_package
from scistudio.desktop.package_ota import PackageManifest, compare_semver, evaluate_update

logger = logging.getLogger(__name__)

# Short timeout: the check runs on a background path and must never block the
# UI. Offline or slow networks degrade to "no update found", never an error.
_FETCH_TIMEOUT_SECONDS = 8.0
# Download timeout is more generous — package snapshots can be tens of MB.
_DOWNLOAD_TIMEOUT_SECONDS = 120.0
# Mirrors package_installer._MANIFEST_NAME (the per-install record written at
# install time). Kept as a local constant to avoid importing a private symbol.
_INSTALL_MANIFEST_NAME = "scistudio-local-package.json"

# A manifest fetcher maps a manifest URL to the parsed JSON document (or raises).
ManifestFetcher = Callable[[str], object]
# A downloader fetches a URL to a local path (used for the snapshot tarball).
Downloader = Callable[[str, "Path"], None]


class PackageUpdateError(RuntimeError):
    """Raised when a package update/rollback/delete cannot be completed."""


@dataclass(frozen=True)
class PackageUpdateStatus:
    """Per-package result of an update check, shaped for the Package Manager UI."""

    package_name: str
    current_version: str
    channel: str
    manifest_url: str
    # One of package_ota.EvaluatedUpdate.kind:
    # "update" | "incompatible" | "none" | "invalid" | "error".
    status: str
    available_version: str = ""
    min_core_base: str = ""
    notes: str = ""
    reason: str = ""

    @property
    def update_available(self) -> bool:
        return self.status == "update"


def fetch_manifest_json(url: str, *, timeout: float = _FETCH_TIMEOUT_SECONDS) -> object:
    """Fetch and JSON-decode a package manifest over HTTP(S).

    Only ``http``/``https`` URLs are honored; anything else raises ``ValueError``
    so a malformed declaration cannot read local files.
    """
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError(f"Unsupported manifest URL scheme: {url!r}")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def check_package_updates(
    packages: Mapping[str, PackageInfo],
    *,
    core_base: str,
    fetch: ManifestFetcher | None = None,
) -> list[PackageUpdateStatus]:
    """Check each package that declares an OTA source for a newer release.

    ``packages`` is the loaded registry's ``name -> PackageInfo`` map
    (``runtime.block_registry.packages()``). Packages without an ``ota``
    declaration are skipped entirely — they are not returned. Network or parse
    failures degrade to a ``status="error"`` row rather than raising, so one bad
    source never breaks the whole check.
    """
    fetcher = fetch or fetch_manifest_json
    results: list[PackageUpdateStatus] = []
    for info in packages.values():
        source = info.ota
        if source is None:
            continue
        try:
            raw = fetcher(source.manifest_url)
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            logger.info("Package OTA check failed for %s: %s", info.name, exc)
            results.append(
                PackageUpdateStatus(
                    package_name=info.name,
                    current_version=info.version,
                    channel=source.channel,
                    manifest_url=source.manifest_url,
                    status="error",
                    reason=str(exc),
                )
            )
            continue

        manifest = PackageManifest.from_dict(raw)
        evaluated = evaluate_update(manifest, installed_version=info.version, core_base=core_base)
        results.append(
            PackageUpdateStatus(
                package_name=info.name,
                current_version=info.version,
                channel=source.channel,
                manifest_url=source.manifest_url,
                status=evaluated.kind,
                available_version=evaluated.available_version,
                min_core_base=evaluated.min_core_base,
                notes=manifest.notes if manifest is not None else "",
                reason=evaluated.reason,
            )
        )
    return results


@dataclass(frozen=True)
class InstalledPackage:
    """One package shown in the Package Manager list.

    ``bundled`` marks a package that is present only via the live registry
    (shipped in the desktop bundle / installed as an entry point) and not yet
    user-installed on disk. Such a package has no on-disk install dir and cannot
    be deleted, but it can still be updated — the update installs a shadowing
    copy into the scanned user packages dir.
    """

    package_name: str
    version: str
    install_path: Path
    modules: tuple[str, ...]
    has_backup: bool = False
    backup_version: str = ""
    bundled: bool = False


@dataclass(frozen=True)
class PackageActionResult:
    """Outcome of an update/rollback/delete action."""

    package_name: str
    version: str
    action: str  # "update" | "rollback" | "delete"
    # Applying new package code needs a fresh interpreter (already-imported
    # modules are not re-imported in-process), so the UI prompts a relaunch.
    needs_relaunch: bool = True
    previous_version: str = ""


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("._-")
    return cleaned.lower() or "package"


def _read_install_manifest(package_dir: Path) -> dict | None:
    manifest_path = package_dir / _INSTALL_MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _iter_install_dirs(install_root: Path) -> list[tuple[Path, dict]]:
    if not install_root.is_dir():
        return []
    found: list[tuple[Path, dict]] = []
    for child in sorted(install_root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest = _read_install_manifest(child)
        if manifest is not None:
            found.append((child, manifest))
    return found


def _backup_dir_for(backups_root: Path, package_name: str) -> Path:
    return backups_root / _safe_name(package_name)


def _existing_backup(backups_root: Path, package_name: str) -> Path | None:
    backup_root = _backup_dir_for(backups_root, package_name)
    if not backup_root.is_dir():
        return None
    children = [c for c in sorted(backup_root.iterdir()) if c.is_dir()]
    return children[0] if children else None


def list_installed_packages(
    *,
    install_root: str | Path | None = None,
    backups_root: str | Path | None = None,
    registry_packages: Mapping[str, PackageInfo] | None = None,
) -> list[InstalledPackage]:
    """List packages for the Package Manager.

    On-disk user installs come first (from their install manifests). When
    ``registry_packages`` is provided, any loaded package not present on disk —
    i.e. shipped in the bundle / installed as an entry point — is appended as a
    ``bundled`` row so its OTA update is actually visible and applyable, not just
    counted by the toolbar badge.
    """
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    backups = Path(backups_root).expanduser() if backups_root is not None else paths.package_backups_dir()
    packages: list[InstalledPackage] = []
    seen: set[str] = set()

    def _backup_version(name: str) -> tuple[bool, str]:
        backup = _existing_backup(backups, name)
        if backup is None:
            return False, ""
        return True, str((_read_install_manifest(backup) or {}).get("version") or "")

    for install_dir, manifest in _iter_install_dirs(root):
        name = str(manifest.get("package_name") or install_dir.name)
        seen.add(name)
        has_backup, backup_version = _backup_version(name)
        modules = manifest.get("modules")
        packages.append(
            InstalledPackage(
                package_name=name,
                version=str(manifest.get("version") or ""),
                install_path=install_dir,
                modules=tuple(m for m in modules if isinstance(m, str)) if isinstance(modules, list) else (),
                has_backup=has_backup,
                backup_version=backup_version,
            )
        )

    for name, info in (registry_packages or {}).items():
        if name in seen:
            continue
        seen.add(name)
        has_backup, backup_version = _backup_version(name)
        packages.append(
            InstalledPackage(
                package_name=name,
                version=info.version,
                install_path=Path(""),
                modules=(),
                has_backup=has_backup,
                backup_version=backup_version,
                bundled=True,
            )
        )
    return packages


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_release_asset(url: str, dest: Path, *, timeout: float = _DOWNLOAD_TIMEOUT_SECONDS) -> None:
    """Stream an HTTPS asset to ``dest``. Rejects non-HTTPS URLs."""
    if not url.startswith("https://"):
        raise PackageUpdateError(f"Refusing to download package over a non-HTTPS URL: {url!r}")
    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, dest.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except (urllib.error.URLError, OSError) as exc:
        raise PackageUpdateError(f"Failed to download package snapshot: {exc}") from exc


def _move_old_active_to_backup(
    *,
    install_root: Path,
    backups_root: Path,
    package_name: str,
    new_install_dir: Path,
) -> str:
    """Move the prior active version of *package_name* into the backups root.

    Returns the backed-up version string. Any *other* stale version dirs of the
    same package (a pre-existing artifact of version bumps leaving old dirs on
    the scan path) are removed so exactly one version stays discoverable.
    """
    new_resolved = new_install_dir.resolve()
    siblings: list[tuple[Path, str]] = []
    for install_dir, manifest in _iter_install_dirs(install_root):
        if install_dir.resolve() == new_resolved:
            continue
        if str(manifest.get("package_name") or "") == package_name:
            siblings.append((install_dir, str(manifest.get("version") or "")))
    if not siblings:
        return ""

    # Highest-version sibling becomes the rollback backup; older ones are dropped.
    def _by_version(a: tuple[Path, str], b: tuple[Path, str]) -> int:
        return compare_semver(a[1], b[1])

    siblings.sort(key=functools.cmp_to_key(_by_version))
    backup_source, backup_version = siblings[-1]
    for stale_dir, _version in siblings[:-1]:
        shutil.rmtree(stale_dir, ignore_errors=True)

    backup_root = _backup_dir_for(backups_root, package_name)
    if backup_root.exists():
        shutil.rmtree(backup_root, ignore_errors=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(backup_source), str(backup_root / backup_source.name))
    return backup_version


def update_package(
    package_name: str,
    *,
    packages: Mapping[str, PackageInfo],
    core_base: str,
    fetch: ManifestFetcher | None = None,
    download: Downloader | None = None,
    install_root: str | Path | None = None,
    backups_root: str | Path | None = None,
    install_dependencies: bool = True,
    python_executable: str | Path | None = None,
) -> PackageActionResult:
    """Download, verify, and stage the latest release for one package.

    The new version is installed into the scanned install root; the prior
    version is moved aside as a rollback backup. The caller relaunches the app
    so a fresh interpreter imports the new code.
    """
    info = packages.get(package_name)
    if info is None or info.ota is None:
        raise PackageUpdateError(f"Package {package_name!r} has no OTA update source.")
    fetcher = fetch or fetch_manifest_json
    downloader = download or download_release_asset
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    backups = Path(backups_root).expanduser() if backups_root is not None else paths.package_backups_dir()

    try:
        raw = fetcher(info.ota.manifest_url)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise PackageUpdateError(f"Failed to fetch manifest for {package_name!r}: {exc}") from exc
    manifest = PackageManifest.from_dict(raw)
    evaluated = evaluate_update(manifest, installed_version=info.version, core_base=core_base)
    if evaluated.kind != "update" or manifest is None:
        raise PackageUpdateError(
            f"No applicable update for {package_name!r} (status={evaluated.kind}, reason={evaluated.reason})."
        )
    # The manifest must describe the package we were asked to update; a
    # misconfigured/compromised source pointing at another package is rejected
    # before anything is downloaded.
    if manifest.package and manifest.package != package_name:
        raise PackageUpdateError(f"Manifest package {manifest.package!r} does not match requested {package_name!r}.")

    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".scistudio-pkg-ota-") as tmp:
        tarball = Path(tmp) / f"{_safe_name(package_name)}-{manifest.version}.tar.gz"
        downloader(manifest.url, tarball)
        actual = _sha256_file(tarball)
        if actual.lower() != manifest.sha256.lower():
            raise PackageUpdateError(
                f"Checksum mismatch for {package_name!r}: expected {manifest.sha256}, got {actual}."
            )
        result = install_local_package(
            tarball,
            install_root=root,
            install_dependencies=install_dependencies,
            python_executable=python_executable,
        )

    # A valid checksum only proves the bytes match the manifest; it does not
    # prove the manifest points at the right package/version. Verify the
    # installed archive's identity before disturbing the current active install,
    # and roll the bad install back out if it does not match.
    if result.package_name != package_name or result.version != manifest.version:
        shutil.rmtree(result.install_path, ignore_errors=True)
        raise PackageUpdateError(
            f"Downloaded archive identity {result.package_name!r} {result.version!r} does not match "
            f"requested {package_name!r} {manifest.version!r}; update rejected."
        )

    previous = _move_old_active_to_backup(
        install_root=root,
        backups_root=backups,
        package_name=result.package_name,
        new_install_dir=result.install_path,
    )
    return PackageActionResult(
        package_name=result.package_name,
        version=result.version,
        action="update",
        previous_version=previous,
    )


def rollback_package(
    package_name: str,
    *,
    install_root: str | Path | None = None,
    backups_root: str | Path | None = None,
) -> PackageActionResult:
    """Restore the backed-up previous version and discard the current one."""
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    backups = Path(backups_root).expanduser() if backups_root is not None else paths.package_backups_dir()

    backup = _existing_backup(backups, package_name)
    if backup is None:
        raise PackageUpdateError(f"No rollback backup available for {package_name!r}.")
    backup_manifest = _read_install_manifest(backup) or {}
    restored_version = str(backup_manifest.get("version") or "")

    superseded_version = ""
    for install_dir, manifest in _iter_install_dirs(root):
        if str(manifest.get("package_name") or "") == package_name:
            superseded_version = str(manifest.get("version") or "")
            shutil.rmtree(install_dir, ignore_errors=True)

    shutil.move(str(backup), str(root / backup.name))
    backup_root = _backup_dir_for(backups, package_name)
    if backup_root.is_dir() and not any(backup_root.iterdir()):
        backup_root.rmdir()
    return PackageActionResult(
        package_name=package_name,
        version=restored_version,
        action="rollback",
        previous_version=superseded_version,
    )


def delete_package(
    package_name: str,
    *,
    install_root: str | Path | None = None,
    backups_root: str | Path | None = None,
) -> PackageActionResult:
    """Remove a package's active install and any rollback backup."""
    root = Path(install_root).expanduser() if install_root is not None else paths.installed_packages_dir()
    backups = Path(backups_root).expanduser() if backups_root is not None else paths.package_backups_dir()

    removed_version = ""
    matched = False
    for install_dir, manifest in _iter_install_dirs(root):
        if str(manifest.get("package_name") or "") == package_name:
            matched = True
            removed_version = str(manifest.get("version") or "")
            shutil.rmtree(install_dir, ignore_errors=True)
    if not matched:
        raise PackageUpdateError(f"Package {package_name!r} is not installed.")

    backup_root = _backup_dir_for(backups, package_name)
    if backup_root.exists():
        shutil.rmtree(backup_root, ignore_errors=True)
    return PackageActionResult(
        package_name=package_name,
        version=removed_version,
        action="delete",
        needs_relaunch=True,
    )


__all__ = [
    "Downloader",
    "InstalledPackage",
    "ManifestFetcher",
    "PackageActionResult",
    "PackageUpdateError",
    "PackageUpdateStatus",
    "check_package_updates",
    "delete_package",
    "download_release_asset",
    "fetch_manifest_json",
    "list_installed_packages",
    "rollback_package",
    "update_package",
]
