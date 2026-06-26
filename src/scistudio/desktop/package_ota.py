"""Pure decision logic for per-package OTA hot-update (issue #1784).

This module mirrors the role of the desktop core's ``desktop/ota.js``: it
decides *whether* a package update applies, with no network or filesystem
dependencies, so the rules are directly unit-testable. The IO side — fetching
each package's manifest, downloading/verifying the snapshot, staging it, and
relaunching — lives in :mod:`scistudio.desktop.package_manager`.

Unlike core OTA, packages compare by **semver** rather than a monotonic build
number: a package update is a full replace of the installed package directory
that shadows any bundled copy, so there is no "installer baseline build" to
sequence against. The manifest records the new ``version`` and the minimum core
base it requires (``requires.min_core_base``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Accepts "a.b.c" or "a.b.c-<prerelease>" / "a.b.c+<build>". Only the numeric
# a.b.c triple participates in ordering; a bare release outranks an otherwise
# equal prerelease (standard semver precedence, simplified for our needs). The
# separator ("-" or "+") is captured so a "-prerelease" can be told apart from
# a "+build" (a build-metadata suffix does not lower precedence).
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:([-+])([0-9A-Za-z.\-]+))?$")


@dataclass(frozen=True)
class PackageManifest:
    """A package's published OTA manifest document."""

    package: str
    version: str
    url: str
    sha256: str
    size: int = 0
    min_core_base: str = ""
    notes: str = ""
    published_at: str = ""

    @classmethod
    def from_dict(cls, data: object) -> PackageManifest | None:
        """Parse a manifest dict, returning ``None`` when malformed.

        Required fields are ``package``, ``version``, ``url``, and ``sha256``;
        anything else is optional. ``requires.min_core_base`` is lifted to the
        flat ``min_core_base`` attribute.
        """
        if not isinstance(data, dict):
            return None
        package = data.get("package")
        version = data.get("version")
        url = data.get("url")
        sha256 = data.get("sha256")
        if not all(isinstance(v, str) and v for v in (package, version, url, sha256)):
            return None
        requires = data.get("requires")
        min_core_base = ""
        if isinstance(requires, dict):
            raw = requires.get("min_core_base")
            if isinstance(raw, str):
                min_core_base = raw
        size = data.get("size")
        return cls(
            package=str(package),
            version=str(version),
            url=str(url),
            sha256=str(sha256),
            size=int(size) if isinstance(size, int) else 0,
            min_core_base=min_core_base,
            notes=str(data.get("notes") or ""),
            published_at=str(data.get("published_at") or ""),
        )


@dataclass(frozen=True)
class EvaluatedUpdate:
    """The outcome of comparing an installed package against its manifest.

    ``kind`` is one of:

    - ``"none"``         — nothing to do (no source, up-to-date, or unparsable
      installed version); ``reason`` explains which.
    - ``"invalid"``      — the manifest is malformed and was ignored.
    - ``"incompatible"`` — a newer version exists but it needs a newer core
      (``min_core_base`` exceeds the running core base).
    - ``"update"``       — a newer, core-compatible version is available.
    """

    kind: str
    reason: str = ""
    available_version: str = ""
    min_core_base: str = ""


def parse_semver(version: str | None) -> tuple[int, int, int, bool] | None:
    """Parse ``a.b.c`` (optionally with a pre-release/build suffix).

    Returns ``(major, minor, patch, is_release)`` where ``is_release`` is
    ``False`` when a ``-prerelease`` suffix is present, or ``None`` when the
    string is not a recognized version.
    """
    match = _SEMVER_RE.match(str(version or "").strip())
    if not match:
        return None
    major, minor, patch, separator, _suffix = match.groups()
    # A "+build" suffix is still a release; only a "-prerelease" suffix lowers
    # precedence.
    is_release = separator != "-"
    return int(major), int(minor), int(patch), is_release


def compare_semver(a: str, b: str) -> int:
    """Compare two semver strings. Returns -1, 0, or 1.

    Unparsable versions sort below parsable ones; two unparsable versions are
    treated as equal. The numeric ``a.b.c`` triple dominates; a release outranks
    an equal-triple pre-release.
    """
    pa = parse_semver(a)
    pb = parse_semver(b)
    if pa is None and pb is None:
        return 0
    if pa is None:
        return -1
    if pb is None:
        return 1
    triple_a = pa[:3]
    triple_b = pb[:3]
    if triple_a != triple_b:
        return -1 if triple_a < triple_b else 1
    if pa[3] != pb[3]:
        # release (True) beats prerelease (False)
        return 1 if pa[3] else -1
    return 0


def evaluate_update(
    manifest: PackageManifest | None,
    *,
    installed_version: str,
    core_base: str,
) -> EvaluatedUpdate:
    """Decide whether ``manifest`` offers a usable update over the installed copy.

    ``core_base`` is the running core's ``a.b.c`` base (see
    :func:`scistudio.version.get_version`). ``installed_version`` is the
    currently installed package version (from its ``PackageInfo``/manifest).
    """
    if manifest is None:
        return EvaluatedUpdate(kind="invalid", reason="bad-manifest")
    if parse_semver(installed_version) is None:
        return EvaluatedUpdate(kind="none", reason="installed-version-unparsable")
    if compare_semver(manifest.version, installed_version) <= 0:
        return EvaluatedUpdate(kind="none", reason="up-to-date")
    if manifest.min_core_base and compare_semver(core_base, manifest.min_core_base) < 0:
        return EvaluatedUpdate(
            kind="incompatible",
            reason="core-too-old",
            available_version=manifest.version,
            min_core_base=manifest.min_core_base,
        )
    return EvaluatedUpdate(
        kind="update",
        available_version=manifest.version,
        min_core_base=manifest.min_core_base,
    )


__all__ = [
    "EvaluatedUpdate",
    "PackageManifest",
    "compare_semver",
    "evaluate_update",
    "parse_semver",
]
