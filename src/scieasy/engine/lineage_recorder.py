"""Compatibility re-export shim — moved to ``scieasy.core.lineage.recorder``.

ADR-038 §5.2 relocated :class:`LineageRecorder` from the engine layer into the
``scieasy.core.lineage`` package so the lineage system is a peer of
``LineageStore`` rather than a thin EventBus subscriber. The class lives at
``scieasy.core.lineage.recorder`` and is exported via
``scieasy.core.lineage.LineageRecorder``.

This shim keeps the legacy import path working through the ADR-038
6-month deprecation window (synchronised with the ``MetadataStore``
shim's removal schedule). **Scheduled removal: 2026-11-15** — see
the tracker filed by D38-3.2 (audit D38-3.1a P2: "engine/lineage_recorder.py
compat shim has no scheduled removal"). Audit log: no in-tree callers
remain at D38-3.2 land time; this file exists purely for out-of-tree
plugins / agents that may still import from the legacy path.
"""

from __future__ import annotations

from scieasy.core.lineage.recorder import LineageRecorder

__all__ = ["LineageRecorder"]
