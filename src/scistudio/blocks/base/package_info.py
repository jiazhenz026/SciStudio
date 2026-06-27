"""PackageInfo — metadata for external block packages.

Kept in a separate file to avoid circular imports when external packages
import it for registration.  See ADR-025.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PackageOtaSource:
    """Where a package publishes its OTA hot-update manifest.

    A package self-declares its update source (issue #1784) so core never has
    to maintain a list of packages. ``manifest_url`` points at a per-package,
    public ``manifest.json`` (see ``scistudio.desktop.package_ota``); ``channel``
    selects which rolling release line to track (e.g. ``alpha``, ``stable``).
    """

    manifest_url: str
    channel: str = "stable"


@dataclass(frozen=True)
class PackageInfo:
    """Metadata about a block package.

    External block packages return a ``PackageInfo`` instance alongside
    their block list in the ``scistudio.blocks`` entry-point callable.
    The registry uses this to populate the two-level palette hierarchy
    (package -> category -> block).
    """

    name: str
    description: str = ""
    author: str = ""
    version: str = "0.1.0"
    # OTA hot-update source (#1784). Optional so packages that never publish
    # updates — and older packages built before this field existed — keep
    # working unchanged. When set, the in-app Package Manager checks this
    # source for newer releases.
    ota: PackageOtaSource | None = None
