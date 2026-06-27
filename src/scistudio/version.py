"""Version deriver: ``base + channel + build`` -> PEP 440 / SemVer / display.

#1742. The single source of truth is :mod:`scistudio._version` (``BASE_VERSION``
and ``CHANNEL``). The build number comes from the ``SCISTUDIO_BUILD_NUMBER``
environment override, or a local gitignored counter file
(``.build-counter.json`` at the repo root), defaulting to ``0``.

Three formats are derived from ``base + channel + build`` so each consumer gets
a valid string for its ecosystem:

* **PEP 440** (Python packaging — ``pyproject``, ``importlib.metadata``)::

      0.2.1a7   (alpha)    0.2.1b7   (beta)    0.2.1   (stable)

* **display / SemVer** (npm, electron, UI, bug reports)::

      0.2.1-alpha-build0007   0.2.1-beta-build0007   0.2.1   (stable)

The display form ``a.b.c-<channel>-build<NNNN>`` is what the owner asked for; it
is intentionally NOT PEP 440 (hyphens in the core are invalid), which is why the
Python track uses the compact ``a<N>``/``b<N>`` prerelease form instead.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from scistudio._version import BASE_VERSION, CHANNEL

CHANNELS = ("alpha", "beta", "stable")
"""Valid release channels."""

_PEP440_SUFFIX = {"alpha": "a", "beta": "b"}
_COUNTER_FILENAME = ".build-counter.json"
_BUILD_ENV = "SCISTUDIO_BUILD_NUMBER"


@dataclass(frozen=True)
class VersionInfo:
    """A fully-resolved version across all three tracks."""

    base: str
    channel: str
    build: int
    pep440: str
    semver: str
    display: str

    def as_dict(self) -> dict[str, object]:
        return {
            "base": self.base,
            "channel": self.channel,
            "build": self.build,
            "pep440": self.pep440,
            "semver": self.semver,
            "display": self.display,
        }


def validate_channel(channel: str) -> str:
    """Return *channel* if valid, else raise ``ValueError``."""
    if channel not in CHANNELS:
        raise ValueError(f"Unknown channel {channel!r}; expected one of {CHANNELS}")
    return channel


def repo_root() -> Path | None:
    """Return the repo root (nearest ancestor with ``pyproject.toml``)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def counter_path() -> Path | None:
    """Return the local build-counter file path, or ``None`` outside a source tree.

    Codex P2: never fall back to the launch CWD. An installed/bundled app has no
    ancestor ``pyproject.toml``, and reading a stray ``.build-counter.json`` from
    the user's working directory would report an unrelated build number. Installed
    builds derive the build from packaged metadata instead (see
    :func:`read_build_number`).
    """
    root = repo_root()
    return (root / _COUNTER_FILENAME) if root is not None else None


def _read_counter_file() -> dict[str, int]:
    path = counter_path()
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in data.items():
        try:
            out[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return out


def _build_from_metadata(channel: str) -> int:
    """Derive *channel*'s build from the installed package metadata.

    ``scripts/version.py sync`` bakes the PEP 440 version (e.g. ``0.2.1a7``) into
    the wheel/desktop package metadata, so an installed app parses the prerelease
    number back out instead of reading a (gitignored, source-only) counter file.
    """
    suffix = _PEP440_SUFFIX.get(channel)
    if suffix is None:
        return 0
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _dist_version

        try:
            distribution = _dist_version("scistudio")
        except PackageNotFoundError:
            return 0
    except Exception:
        return 0
    import re

    match = re.search(rf"{re.escape(suffix)}(\d+)$", distribution)
    return int(match.group(1)) if match else 0


def read_build_number(channel: str = CHANNEL) -> int:
    """Return the build number for *channel*.

    Priority: ``SCISTUDIO_BUILD_NUMBER`` env override -> local counter file (only
    inside a source tree) -> installed package metadata -> ``0``. Never raises.
    """
    env = os.environ.get(_BUILD_ENV)
    if env is not None and env.strip():
        try:
            return max(0, int(env.strip()))
        except ValueError:
            pass
    if counter_path() is not None:
        return _read_counter_file().get(channel, 0)
    return _build_from_metadata(channel)


def write_build_number(channel: str, build: int) -> int:
    """Persist *build* for *channel* in the local counter file; return it.

    Only valid inside a source checkout (the counter is gitignored and
    source-only); raises ``RuntimeError`` for an installed/bundled app.
    """
    validate_channel(channel)
    path = counter_path()
    if path is None:
        raise RuntimeError("build counter is only writable inside a source checkout")
    counters = _read_counter_file()
    counters[channel] = max(0, int(build))
    path.write_text(json.dumps(counters, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return counters[channel]


def bump_build_number(channel: str = CHANNEL) -> int:
    """Increment and persist the counter for *channel*; return the new value."""
    return write_build_number(channel, read_build_number(channel) + 1)


def format_pep440(base: str, channel: str, build: int) -> str:
    """Return the PEP 440 string for *base*/*channel*/*build*."""
    validate_channel(channel)
    if channel == "stable":
        return base
    return f"{base}{_PEP440_SUFFIX[channel]}{int(build)}"


def format_display(base: str, channel: str, build: int) -> str:
    """Return the human display / SemVer string for *base*/*channel*/*build*."""
    validate_channel(channel)
    if channel == "stable":
        return base
    return f"{base}-{channel}-build{int(build):04d}"


def get_version(channel: str | None = None, build: int | None = None) -> VersionInfo:
    """Resolve the full version.

    *channel* defaults to :data:`scistudio._version.CHANNEL`; *build* defaults to
    :func:`read_build_number` for that channel.
    """
    resolved_channel = validate_channel(channel or CHANNEL)
    resolved_build = read_build_number(resolved_channel) if build is None else max(0, int(build))
    pep440 = format_pep440(BASE_VERSION, resolved_channel, resolved_build)
    display = format_display(BASE_VERSION, resolved_channel, resolved_build)
    return VersionInfo(
        base=BASE_VERSION,
        channel=resolved_channel,
        build=resolved_build,
        pep440=pep440,
        semver=display,
        display=display,
    )


#: PEP 440 version string for the current source tree (build from env/counter).
__version__ = get_version().pep440

__all__ = [
    "CHANNELS",
    "VersionInfo",
    "__version__",
    "bump_build_number",
    "counter_path",
    "format_display",
    "format_pep440",
    "get_version",
    "read_build_number",
    "repo_root",
    "validate_channel",
    "write_build_number",
]
