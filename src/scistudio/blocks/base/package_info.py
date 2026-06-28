"""PackageInfo — metadata for external block packages.

Kept in its own file so external packages can import it for registration without
triggering circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from scistudio.stability import provisional, stable


@provisional(since="0.3.1")
@dataclass(frozen=True)
class PackageOtaSource:
    """Where a block package publishes its over-the-air (OTA) update manifest.

    A package declares its own update source so the core runtime never has to
    keep a list of packages. When this is set on a :class:`PackageInfo`, the
    in-app Package Manager checks the source for newer releases.

    Example:
        >>> source = PackageOtaSource(
        ...     manifest_url="https://example.org/pkg/manifest.json",
        ...     channel="stable",
        ... )
    """

    manifest_url: str
    """Public URL of the package's ``manifest.json`` listing its releases."""

    channel: str = "stable"
    """Which rolling release line to follow (e.g. ``"alpha"`` or ``"stable"``)."""


@stable(since="0.3.1")
@dataclass(frozen=True)
class PackageInfo:
    """Metadata describing an external block package.

    An external block package returns a ``PackageInfo`` alongside its block list
    from its ``scistudio.blocks`` entry-point callable. The registry uses it to
    place the package in the palette as a two-level grouping
    (package -> category -> block).

    Example:
        >>> info = PackageInfo(
        ...     name="My Imaging Blocks",
        ...     description="Microscopy helpers",
        ...     author="Lab X",
        ...     version="1.2.0",
        ... )
    """

    name: str
    """Display name of the package shown in the palette."""

    description: str = ""
    """Short human-readable summary of what the package provides."""

    author: str = ""
    """Package author or maintaining group."""

    version: str = "0.1.0"
    """Package version string (e.g. ``"1.2.0"``)."""

    ota: PackageOtaSource | None = None
    """Optional OTA update source; ``None`` for packages that never publish updates.

    When set, the in-app Package Manager checks this source for newer releases.
    Optional so older packages built before this field existed keep working.
    """
