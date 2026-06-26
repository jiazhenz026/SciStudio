"""In-app Package Manager services (issue #1784).

This module is the IO side of the per-package OTA flow whose pure decision
logic lives in :mod:`scistudio.desktop.package_ota`. It backs the desktop
Package Manager UI: checking each installed package's self-declared OTA source
for newer releases. Download/stage/rollback/delete are layered on top in later
commits.

Packages self-declare their update source via :class:`PackageInfo.ota`
(``manifest_url`` + ``channel``); core never maintains a package list. The
check iterates the *loaded* registry packages, fetches each manifest, and
compares by semver against the running core base.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from scistudio.blocks.base.package_info import PackageInfo
from scistudio.desktop.package_ota import PackageManifest, evaluate_update

logger = logging.getLogger(__name__)

# Short timeout: the check runs on a background path and must never block the
# UI. Offline or slow networks degrade to "no update found", never an error.
_FETCH_TIMEOUT_SECONDS = 8.0

# A manifest fetcher maps a manifest URL to the parsed JSON document (or raises).
ManifestFetcher = Callable[[str], object]


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
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked above
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


__all__ = [
    "ManifestFetcher",
    "PackageUpdateStatus",
    "check_package_updates",
    "fetch_manifest_json",
]
