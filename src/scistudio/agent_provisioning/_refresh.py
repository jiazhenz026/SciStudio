"""Content-aware refresh for managed agent assets (#1860, PR #2144 review).

Before this module, provisioning was existence-only: with ``force=False``
every writer skipped any file that already existed, so a project created by
an older SciStudio kept its stale ``CLAUDE.md`` / ``AGENTS.md`` / skill
files forever — a rebrand or contract fix shipped in a new release never
reached existing projects.

The refresh rule is *unchanged-since-we-wrote-it*:

- A per-project hash manifest at
  ``<project>/.claude/.scistudio-provision-hashes.json`` records the sha256
  of every managed file the last provisioning run wrote. On the next run, a
  file whose content still matches its manifest entry was not touched by the
  user and is refreshed to the current canonical content; a mismatch means
  the user edited it and the file is preserved verbatim.
- Projects provisioned before the manifest existed have no entries. For
  one-time adoption, ``templates/legacy_content_hashes.json`` (generated
  from git history at introduction time and frozen) carries the sha256 of
  every content SciStudio ever shipped at each managed path. A file matching
  any of those is by construction unmodified canonical content and is
  refreshed; anything else is preserved.

Both hashes are computed on LF-normalised UTF-8 content so a developer
checkout with ``core.autocrlf`` (CRLF working-tree files) and a wheel install
(LF package data) produce the same digest.

The manifest only ever *permits* a rewrite; a stale or missing manifest entry
falls back to preserve, never to clobber.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Project-relative path of the per-project managed-content manifest.
MANIFEST_REL_PATH = ".claude/.scistudio-provision-hashes.json"

_LEGACY_RESOURCE = "legacy_content_hashes.json"


def _digest(content: str) -> str:
    """sha256 of LF-normalised UTF-8 content."""
    return hashlib.sha256(content.replace("\r\n", "\n").encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _legacy_hashes() -> dict[str, frozenset[str]]:
    """Load the frozen historical-content hash table (packaged resource)."""
    try:
        raw = (
            importlib.resources.files("scistudio.agent_provisioning.templates")
            .joinpath(_LEGACY_RESOURCE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError):
        here = Path(__file__).resolve()
        candidate = here.parent / "templates" / _LEGACY_RESOURCE
        raw = candidate.read_text(encoding="utf-8")
    table = json.loads(raw)
    return {path: frozenset(hashes) for path, hashes in table.items()}


def load_manifest(project_dir: Path) -> dict[str, str]:
    """Read the managed-content manifest, returning ``{}`` when absent/corrupt."""
    manifest_path = project_dir / MANIFEST_REL_PATH
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        return {}
    return {str(k): str(v) for k, v in files.items()}


def save_manifest(project_dir: Path, manifest: dict[str, str]) -> None:
    """Persist the managed-content manifest (best-effort by the caller)."""
    manifest_path = project_dir / MANIFEST_REL_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "files": dict(sorted(manifest.items()))}
    manifest_path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_managed_file(
    project_dir: Path,
    rel_path: str,
    content: str,
    manifest: dict[str, str],
    *,
    force: bool = False,
) -> bool:
    """Write ``content`` to ``<project_dir>/<rel_path>`` when it is managed.

    Returns True when the file was written. A file is written when it is
    missing, when ``force`` is set, when its content still matches the
    manifest entry from the last provisioning run, or when it matches a
    known historical canonical content (pre-manifest adoption). Otherwise
    the file is user-edited and preserved verbatim.
    """
    dest = project_dir / rel_path
    if dest.exists() and not force:
        try:
            current = _digest(dest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            logger.debug("write_managed_file: %s unreadable; preserving", rel_path)
            return False
        known = manifest.get(rel_path)
        if known is not None and current != known:
            return False  # user edited since our last write
        if known is None and current not in _legacy_hashes().get(rel_path, frozenset()):
            return False  # no manifest entry and not a known canonical version
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8", newline="\n")
    manifest[rel_path] = _digest(content)
    return True
