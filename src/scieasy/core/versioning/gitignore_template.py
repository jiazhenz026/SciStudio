"""Default ``.gitignore`` template for SciEasy projects (ADR-039 §3.3).

Written on auto-init (see :func:`scieasy.core.versioning.git_engine.GitEngine.init_repository`).
The exact content is fixed by ADR-039 §3.3 lines 103-130. Users may edit
the file freely after init; SciEasy never overwrites an existing
``.gitignore`` — :func:`write_default_gitignore` is a no-op when the
file already exists.

Rationale for what is ignored
-----------------------------

- ``data/`` — large data files are not versioned; the lineage layer
  (ADR-038) tracks data-object references via SHA + manifest, not file
  content. Git LFS is explicitly out of scope per ADR-039 §3.10.
- ``.scieasy/`` — per-project, per-machine runtime state (lineage.db,
  pause checkpoints, mcp socket port, git author cache). Conceptually
  local — see §3.3 lines 132-138 for the trade-off discussion.
- Python caches, OS noise, plugin venvs (per ADR-037), editor caches —
  standard exclusions.
"""

from __future__ import annotations

from pathlib import Path

# Per ADR-039 §3.3 — exact content must match the ADR. If you edit this,
# update the ADR's code block first.
DEFAULT_GITIGNORE = """# SciEasy auto-generated .gitignore.
# Edit freely — SciEasy will not overwrite this file.

# Data files (not versioned — see ADR-038 for run lineage)
data/

# SciEasy runtime state (per-project, per-machine; not portable)
.scieasy/

# Python caches
__pycache__/
*.py[cod]
*$py.class

# OS noise
.DS_Store
Thumbs.db

# Plugin venvs (per ADR-037)
*-venv/
*.venv/

# Editor caches
.idea/
.vscode/
*.swp
"""


def write_default_gitignore(project_path: Path) -> bool:
    """Write the default ``.gitignore`` if one does not already exist.

    See module docstring + ADR-039 §3.3 lines 99-138.

    Returns ``True`` if a file was written, ``False`` if a
    ``.gitignore`` was already present (preserves user customizations).
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
