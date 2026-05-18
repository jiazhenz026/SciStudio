"""SciEasy custom Sphinx directives — shell module.

Per ADR-044 §10.2, this module hosts three directive classes:

- ``ScieasyBlockCatalog`` — per-block autosummary pages
- ``ScieasyRunnerCatalog`` — per-runner (Python / R / Julia) pages
- ``ScieasyAIBlockCatalog`` — per-ADR-035 AI-block registry entry

Phase 1D sub-PR 2 ships only the ``setup()`` shell so ``conf.py`` can
list ``scieasy_directives`` in ``extensions`` without breaking the build.
Directive bodies follow in 1D sub-PR 3+.

TODO(#1169-followup): implement directive bodies per ADR-044 §10.2.
  Out of scope per ADR-044 §11.5 (Phase 1D deliverable, split across
  multiple sub-PRs for review tractability).
  Followup: open after 1D sub-PR 2 merges.
"""

from __future__ import annotations

from typing import Any


def setup(app: Any) -> dict[str, Any]:
    """Sphinx extension entry point — shell.

    Returns the standard metadata dict so Sphinx accepts this as a valid
    extension. Directive registration is intentionally omitted in 1D
    sub-PR 2; subsequent sub-PRs will register the three catalogs.
    """
    # TODO(#1169-followup): register ScieasyBlockCatalog,
    #   ScieasyRunnerCatalog, ScieasyAIBlockCatalog via
    #   app.add_directive(...). Out of scope per ADR-044 §10.2.
    #   Followup: open after 1D sub-PR 2 merges.
    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
