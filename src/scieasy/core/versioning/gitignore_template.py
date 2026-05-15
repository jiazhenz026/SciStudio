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

    Purpose
    -------
    Called by :func:`GitEngine.init_repository` immediately after
    ``git init`` so the very first commit captures the ignore rules.
    Idempotent — running on a project that already has a ``.gitignore``
    is a no-op (preserves user customizations).

    Signature contract
    ------------------
    - Input: ``project_path`` — the project directory (must exist; we do
      NOT create it).
    - Output: ``bool`` — ``True`` if a file was written, ``False`` if a
      ``.gitignore`` was already present.
    - Errors: ``FileNotFoundError`` if ``project_path`` does not exist;
      ``OSError`` on disk failure.

    Implementation steps (for D39-2.2b)
    -----------------------------------
    1. Compute ``target = project_path / ".gitignore"``.
    2. If ``target.exists()``: return ``False``. (Do not raise; this is
       the common case for repos opened a second time.)
    3. Else: write :data:`DEFAULT_GITIGNORE` to ``target`` with
       ``encoding="utf-8"`` and a trailing newline if not present.
    4. Return ``True``.

    Edge cases
    ----------
    - ``.gitignore`` exists but is empty — still treat as "user has a
      file"; do not overwrite. (Empty file is a valid user choice.)
    - Permission denied — propagate ``PermissionError`` to caller; the
      REST layer surfaces this as a 500 with the project-path in the
      error envelope.
    - Race with another writer (rare) — if file appears between exist
      check and write, accept ``FileExistsError`` and return ``False``.

    Test plan (D39-2.2b → tests/core/test_git_engine.py)
    ----------------------------------------------------
    - ``test_write_default_gitignore_writes_template`` — tmpdir without
      ``.gitignore``; call returns ``True``; file content matches
      :data:`DEFAULT_GITIGNORE` exactly.
    - ``test_write_default_gitignore_preserves_existing`` — tmpdir with a
      user ``.gitignore`` containing ``"my_secrets.txt"``; call returns
      ``False``; file content unchanged.
    - ``test_write_default_gitignore_idempotent`` — call twice; second
      call returns ``False``.

    ADR references
    --------------
    - §3.3 lines 99-138 (default .gitignore template + lineage.db
      trade-off discussion)
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")
