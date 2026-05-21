"""Exit-info dataclass for ``scistudio.engine.runners`` (ADR-019).

Holds the :class:`ProcessExitInfo` dataclass shared by
:mod:`scistudio.engine.runners.platform` and
:mod:`scistudio.engine.runners.process_handle`. Extracting it here breaks
the former pair-cycle between those modules (#1337 / PR #1344) so neither
has to use ``TYPE_CHECKING`` shims or in-function lazy imports to
reference the other.

This module MUST NOT import from any other ``scistudio.engine.runners``
sibling — that constraint is what makes it a safe cycle-breaking shim.
``ProcessExitInfo`` is still re-exported from ``process_handle`` for
backward compatibility with the public ADR-019 governs surface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProcessExitInfo:
    """Exit state of a terminated subprocess.

    Populated by :class:`scistudio.engine.runners.platform.PlatformOps`
    implementations when a process exits (ADR-019).
    """

    exit_code: int | None = None
    signal_number: int | None = None  # Unix only, None on Windows
    was_killed_by_framework: bool = False
    platform_detail: str = ""
