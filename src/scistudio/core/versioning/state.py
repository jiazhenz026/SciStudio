"""Public value types for ``scistudio.core.versioning`` (ADR-039).

Holds :class:`HeadState`, the ``GitEngine.head_state()`` result consumed by
the ADR-038 lineage join. It lived in :mod:`scistudio.core.versioning.git_engine`,
but ``_status_ops._head_state`` constructs it at runtime, so that sibling had
to lazy-import ``git_engine`` — a child -> parent edge that closed an import
cycle (round-4 no-cycles, mirroring the #1337 / PR #1344 ``errors`` extraction).

This module MUST NOT import from any other ``scistudio.core.versioning``
sibling — that constraint is what makes it a safe cycle-breaking leaf.
``HeadState`` is re-exported from ``git_engine`` for backward compatibility
with importers; the canonical ADR-039 governed contract is
``scistudio.core.versioning.state.HeadState``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeadState:
    """Result of :meth:`GitEngine.head_state` — used by ADR-038 join."""

    commit_sha: str
    dirty: bool
