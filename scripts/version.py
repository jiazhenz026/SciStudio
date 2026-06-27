#!/usr/bin/env python3
"""SciStudio version management CLI (#1742).

Single source of truth: ``src/scistudio/_version.py`` (``BASE_VERSION`` +
``CHANNEL``). Build number: a local gitignored counter (``.build-counter.json``)
or the ``SCISTUDIO_BUILD_NUMBER`` environment override. This CLI shows / bumps /
switches channel / syncs every manifest from the single derived version, which
is what eliminates the historical drift between pyproject, ``__init__``, and the
two ``package.json`` files.

Usage::

    python scripts/version.py show
    python scripts/version.py bump
    python scripts/version.py set-channel {alpha|beta|stable}
    python scripts/version.py sync

Typical local build flow: ``bump`` then ``sync`` then build. Switching channels
(``set-channel beta``) resets that channel's build counter to 0.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scistudio import version as _v  # noqa: E402


def _sync_pyproject(pep440: str) -> list[str]:
    """Rewrite the ``[project]`` and ``[tool.commitizen]`` versions (PEP 440)."""
    path = _REPO_ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    # Both `version = "..."` lines (project @ top, commitizen) take the PEP 440
    # form; commitizen accepts PEP 440. These are the only `version = ` lines.
    new = re.sub(r'(?m)^version = ".*"$', f'version = "{pep440}"', text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return ["pyproject.toml"]
    return []


def _sync_package_json(rel: str, semver: str) -> list[str]:
    """Rewrite the top-level ``"version"`` field of a package.json (SemVer)."""
    path = _REPO_ROOT / rel
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'("version"\s*:\s*)"[^"]*"', rf'\1"{semver}"', text, count=1)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return [rel]
    return []


def _sync_package_lock(rel: str, semver: str) -> list[str]:
    """Rewrite a package-lock.json's own version (root + packages[""]).

    The package's own version is the first two ``"version"`` fields (root then
    ``packages[""]``); dependency versions come later, so ``count=2`` keeps them
    untouched. Keeping the lock in sync avoids ``npm ci`` consistency failures.
    """
    path = _REPO_ROOT / rel
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    new = re.sub(r'("version"\s*:\s*)"[^"]*"', rf'\1"{semver}"', text, count=2)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return [rel]
    return []


def cmd_show(_args: argparse.Namespace) -> int:
    for key, value in _v.get_version().as_dict().items():
        print(f"{key:>8}: {value}")
    return 0


def cmd_bump(_args: argparse.Namespace) -> int:
    new_build = _v.bump_build_number(_v.CHANNEL)
    info = _v.get_version()
    print(f"bumped {info.channel} build -> {new_build}")
    print(f"version: {info.display}  (pep440 {info.pep440})")
    return 0


def cmd_set_channel(args: argparse.Namespace) -> int:
    channel = _v.validate_channel(args.channel)
    vpath = _REPO_ROOT / "src" / "scistudio" / "_version.py"
    text = vpath.read_text(encoding="utf-8")
    new = re.sub(r'(?m)^CHANNEL = ".*"$', f'CHANNEL = "{channel}"', text)
    if new == text and f'CHANNEL = "{channel}"' not in text:
        print(f"error: could not find CHANNEL assignment in {vpath}", file=sys.stderr)
        return 1
    vpath.write_text(new, encoding="utf-8")
    # Reset the new channel's build counter to 0 (owner: build resets on channel
    # change). Absent counters already default to 0, but write it explicitly so
    # switching back to a previously-used channel also restarts at 0.
    _v.write_build_number(channel, 0)
    print(f"channel set to {channel}; build counter reset to 0")
    return 0


def cmd_sync(_args: argparse.Namespace) -> int:
    info = _v.get_version()
    changed: list[str] = []
    changed += _sync_pyproject(info.pep440)
    changed += _sync_package_json("desktop/package.json", info.semver)
    changed += _sync_package_json("frontend/package.json", info.semver)
    changed += _sync_package_lock("desktop/package-lock.json", info.semver)
    changed += _sync_package_lock("frontend/package-lock.json", info.semver)
    print(f"synced to {info.display} (pep440 {info.pep440}, semver {info.semver})")
    for path in changed:
        print(f"  updated {path}")
    if not changed:
        print("  (all manifests already in sync)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="version.py", description="SciStudio version management")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print the current derived version (all formats)")
    sub.add_parser("bump", help="increment the current channel's build counter")
    set_channel = sub.add_parser("set-channel", help="switch channel and reset its build counter")
    set_channel.add_argument("channel", choices=_v.CHANNELS)
    sub.add_parser("sync", help="rewrite all manifests from the derived version")
    args = parser.parse_args(argv)
    handlers = {
        "show": cmd_show,
        "bump": cmd_bump,
        "set-channel": cmd_set_channel,
        "sync": cmd_sync,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
