"""Default ``.gitignore`` template for SciStudio projects.

Written when a project repository is first initialised (see
:meth:`scistudio.core.versioning.git_engine.GitEngine.init_repository`). Users
may edit the file freely afterwards; SciStudio never overwrites an existing
``.gitignore`` — :func:`write_default_gitignore` is a no-op when the file is
already present.

What is ignored, and why:

- ``data/`` — large data files are not versioned; the lineage layer tracks data
  by reference (digest + manifest) instead of by file content.
- ``.scistudio/`` — per-project, per-machine runtime state (lineage database,
  pause checkpoints, sockets, caches); conceptually local, not portable.
- Python caches, OS noise, plugin virtualenvs, and editor caches — standard
  exclusions.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_GITIGNORE = """# SciStudio auto-generated .gitignore.
# Edit freely — SciStudio will not overwrite this file.

# Data files (not versioned — lineage tracks data by reference instead)
data/

# SciStudio runtime state (per-project, per-machine; not portable)
.scistudio/

# Python caches
__pycache__/
*.py[cod]
*$py.class

# OS noise
.DS_Store
Thumbs.db

# Plugin venvs (per-project plugin virtual environments)
*-venv/
*.venv/

# Editor caches
.idea/
.vscode/
*.swp
"""
"""The exact ``.gitignore`` contents written into a newly initialised project."""


def write_default_gitignore(project_path: Path) -> bool:
    """Write the default ``.gitignore`` when the project has none.

    Never overwrites an existing ``.gitignore``, so user customisations are
    preserved.

    Args:
        project_path: The project directory to write into.

    Returns:
        ``True`` if a file was written, ``False`` if one already existed.

    Raises:
        FileNotFoundError: When *project_path* does not exist.
    """
    if not project_path.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_path}")
    target = project_path / ".gitignore"
    if target.exists():
        return False
    try:
        target.write_text(DEFAULT_GITIGNORE, encoding="utf-8")
    except FileExistsError:
        # Race with another writer.
        return False
    return True
