"""Compatibility re-export shim — moved to ``scieasy.core.lineage.recorder``.

ADR-038 §5.2 relocated :class:`LineageRecorder` from the engine layer into the
``scieasy.core.lineage`` package so the lineage system is a peer of
``LineageStore`` rather than a thin EventBus subscriber. The class lives at
``scieasy.core.lineage.recorder`` and is exported via
``scieasy.core.lineage.LineageRecorder``.

This shim keeps the legacy import path working through Phase D38-2.3
(the 6-month deprecation window also tracked for the ``MetadataStore``
shim). Remove this file once external callers have migrated.
"""

from __future__ import annotations

from scieasy.core.lineage.recorder import LineageRecorder

__all__ = ["LineageRecorder"]
