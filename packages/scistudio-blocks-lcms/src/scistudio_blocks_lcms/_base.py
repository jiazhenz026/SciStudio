"""Shared mixin for all LC-MS plugin blocks (Phase 11 skeleton).

Per ``docs/specs/phase11-lcms-block-spec.md`` §9, every LC-MS block
mixes in :class:`_LCMSBlockMixin` ahead of its concrete base class
(``IOBlock`` / ``ProcessBlock`` / ``AppBlock`` / ``CodeBlock``). The
mixin is the single place that pins plugin-wide ClassVars (currently
just ``category``) so the GUI palette groups every LC-MS block under
the same node-tree branch and the registry can identify which plugin
contributed a given block at scan time.

Body is intentionally tiny — this file is part of the T-LCMS-002
skeleton drop and is finalised by the implementation cascade
(skeleton @ c08a885).
"""

from __future__ import annotations

from typing import ClassVar


class _LCMSBlockMixin:
    """Base mixin shared by every block in ``scistudio-blocks-lcms``.

    The mixin sits *before* the concrete block base in the MRO so that
    plugin-wide ClassVar overrides survive the diamond. It is private
    (leading underscore) because it is an implementation detail of the
    plugin and not part of any public API.
    """

    #: Plugin identifier surfaced to the BlockRegistry palette grouping
    #: logic. Individual blocks may set a more specific ``category``
    #: (e.g. ``"io"``, ``"process"``, ``"app"``) which takes precedence
    #: per the resolution rule in ``Block`` ABC.
    plugin: ClassVar[str] = "scistudio-blocks-lcms"
