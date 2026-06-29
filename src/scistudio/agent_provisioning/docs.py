"""Provision the in-project documentation set (#1850, ADR-052 §7).

Copies two packaged doc trees into a project so the in-project human and the
embedded agent read the authoritative public-API docs instead of reaching into
internals:

  - ``<project>/user-guide/**``                 <- ``scistudio/_user_guide/**``
    (the human user guide *and* the self-contained API reference under
    ``user-guide/api-reference/``)
  - ``<project>/.scistudio/agent-reference/**`` <- ``scistudio/_agent_reference/**``
    (terse, agent-facing contract reference the skills point at)

Filesystem-only and wheel-safe (reads through ``importlib.resources`` exactly
like ``skills.py``), idempotent (skips existing files unless ``force=True``), and
run as a non-fatal sub-step by the orchestrator.
"""

from __future__ import annotations

import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path

#: (source package, project-relative destination root).
_DOC_TREES: tuple[tuple[str, str], ...] = (
    ("scistudio._user_guide", "user-guide"),
    ("scistudio._agent_reference", ".scistudio/agent-reference"),
)


def _copy_tree(
    src: Traversable, dest: Path, *, force: bool, rel: str, written: list[str]
) -> None:
    """Recursively copy a ``importlib.resources`` traversable into ``dest``."""
    for child in src.iterdir():
        name = child.name
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            continue
        child_rel = f"{rel}/{name}"
        if child.is_dir():
            _copy_tree(child, dest / name, force=force, rel=child_rel, written=written)
            continue
        target = dest / name
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(child.read_bytes())
        written.append(child_rel)


def write_docs(project_dir: Path, *, force: bool = False) -> list[str]:
    """Copy the user guide + API reference + agent reference into ``project_dir``.

    Returns the list of project-relative paths actually written (idempotent: an
    existing file is skipped unless ``force``).
    """
    project_dir = Path(project_dir)
    written: list[str] = []
    for package, dest_root in _DOC_TREES:
        try:
            root = importlib.resources.files(package)
        except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
            continue
        if not root.is_dir():
            continue
        _copy_tree(root, project_dir / dest_root, force=force, rel=dest_root, written=written)
    return written
