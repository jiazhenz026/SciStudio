"""The directory layout a new project workspace is created with (#2095).

Two entry points create projects — ``ApiRuntime.create_project`` (the GUI's
"New project") and ``scistudio init`` (the CLI) — and until this module existed
they each carried their own hand-written list. They had already drifted: the
CLI omitted ``data/processed`` while claiming in a comment to be "Symmetric
with ``api/runtime.py::create_project``", and neither created the drop-in
directories for previewers or tutorials even though both tiers are discovered
from a project (:mod:`scistudio.core.dropins`).

The drop-in directory names are imported from :mod:`scistudio.core.dropins`
rather than respelled here, so the folder a project offers and the folder the
registry scans cannot disagree. Adding a fifth drop-in kind means adding one
name to that module and one entry here, not finding every scaffold.

Kept as a leaf module with no heavyweight imports: ``scistudio init`` is a
fast mkdir command and must not pay for the API runtime to learn what a
project looks like.
"""

from __future__ import annotations

from scistudio.core.dropins import (
    BLOCKS_DIR_NAME,
    PREVIEWERS_DIR_NAME,
    TUTORIALS_DIR_NAME,
    TYPES_DIR_NAME,
)

__all__ = ["DATA_SUBDIRS", "DROPIN_SUBDIRS", "PROJECT_SUBDIRS"]

#: Where data lives inside a project.
#:
#: ``data/raw`` and ``data/processed`` are the two the user is meant to think
#: in: what came in, and what came out. The remaining three are runtime-managed
#: stores — the engine writes block outputs under ``data/zarr`` (see
#: ``scistudio.engine.runners.local._derive_output_dir``), ``data/parquet``
#: holds explicitly saved tables, ``data/artifacts`` holds opaque files, and
#: ``data/exchange`` is the hand-off area for external applications (ADR-041).
#:
#: The split is deliberate and documented in ``docs/architecture/ARCHITECTURE.md``:
#: ``data/processed`` is a save/export target a person chooses, not a mirror of
#: the runtime stores.
DATA_SUBDIRS: tuple[str, ...] = (
    "data/raw",
    "data/processed",
    "data/zarr",
    "data/parquet",
    "data/artifacts",
    "data/exchange",
)

#: Project-tier drop-in directories, named by :mod:`scistudio.core.dropins` so
#: the scaffold and the scanners share one spelling.
DROPIN_SUBDIRS: tuple[str, ...] = (
    BLOCKS_DIR_NAME,
    TYPES_DIR_NAME,
    PREVIEWERS_DIR_NAME,
    TUTORIALS_DIR_NAME,
)

#: Every directory created for a new project workspace, in creation order.
#:
#: ADR-038 §3.5 / §5.2: lineage history lives at ``.scistudio/lineage.db``; the
#: legacy top-level ``lineage/`` and ``checkpoints/`` directories are retired.
PROJECT_SUBDIRS: tuple[str, ...] = (
    "workflows",
    *DATA_SUBDIRS,
    *DROPIN_SUBDIRS,
    ".scistudio",
    "logs",
)
