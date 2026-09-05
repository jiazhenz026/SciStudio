"""Representative data the harness feeds a scaffolded panel (FR-015).

A harness that hands the panel ``{}`` proves nothing: the agent looks at an
empty box and learns that its document did not crash. FR-015 asks for
*representative data for the declared target types*, so this module builds, for
each declared type name, the envelope the real backend would send — using
:class:`scistudio.panels.models.PreviewEnvelope` and its ``to_dict`` rather than
a hand-written JSON literal, so the wire shape the harness supplies is the wire
shape the host supplies.

The payload inside each envelope mirrors what the matching built-in provider in
:mod:`scistudio.panels.fallbacks` produces for that kind — the column/row pair
for a dataframe, the plane fields for an array, the points and table for a
series, and so on. It is small on purpose: three rows say as much about whether
a table renders as three hundred, and a harness that opens instantly is a
harness the agent will actually open.

A type name this module does not recognise gets the base-fallback envelope,
which is what the running application would resolve for it too when no panel
claims it. Nothing here refuses an unknown type: a panel is frequently written
*for* a type that does not exist yet.
"""

from __future__ import annotations

from typing import Any

from scistudio.panels.models import (
    EnvelopeKind,
    PreviewEnvelope,
    PreviewMetadata,
    PreviewTarget,
    TargetKind,
)

__all__ = ["STUB_TYPE_KINDS", "stub_envelope", "stub_envelopes"]


def _dataframe_payload() -> dict[str, Any]:
    return {
        "columns": ["wavelength", "intensity", "label"],
        "rows": [
            [400.0, 0.12, "blank"],
            [410.0, 0.48, "sample"],
            [420.0, 0.91, "sample"],
            [430.0, 0.35, "sample"],
        ],
        "total_rows": 4,
        "page": 1,
        "page_size": 4,
        "total_pages": 1,
        "sort_by": None,
        "sort_dir": "asc",
    }


def _array_payload() -> dict[str, Any]:
    matrix = [[0.0, 0.5, 1.0], [0.5, 1.0, 0.5], [1.0, 0.5, 0.0]]
    return {
        "shape": [3, 3],
        "dtype": "float64",
        "axes": ["y", "x"],
        "ndim": 2,
        "slice_axis_name": None,
        "slice_axis_size": 0,
        "slice_index": 0,
        "slice_axes": [],
        "matrix": matrix,
        "thumbnail": matrix,
    }


def _series_payload() -> dict[str, Any]:
    points = [[0, 0.12], [1, 0.48], [2, 0.91], [3, 0.35]]
    return {
        "points": points,
        "table": {"columns": ["index", "value"], "rows": points},
        "total": len(points),
    }


def _text_payload() -> dict[str, Any]:
    return {
        "content": "wavelength,intensity\n400,0.12\n410,0.48\n420,0.91\n",
        "language": "csv",
        "truncated": False,
        "editor_handoff": {"ref": "stub://harness/text", "total_bytes": 58, "shown_bytes": 58},
    }


def _artifact_payload() -> dict[str, Any]:
    return {"path": "stub://harness/report.pdf", "mime_type": "application/pdf", "size_bytes": 24_576}


def _plot_payload() -> dict[str, Any]:
    # A 1x1 transparent PNG. Inline so the harness needs no network at all: it
    # has to open from a ``file://`` URL with nothing serving it.
    return {
        "format": "png",
        "data_uri": (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        ),
        "width": 1,
        "height": 1,
    }


def _collection_payload() -> dict[str, Any]:
    return {
        "count": 3,
        "item_type": "DataFrame",
        "items": [
            {"index": 0, "label": "run-001", "resource_id": "item:0"},
            {"index": 1, "label": "run-002", "resource_id": "item:1"},
            {"index": 2, "label": "run-003", "resource_id": "item:2"},
        ],
    }


def _composite_payload() -> dict[str, Any]:
    return {
        "slots": [
            {"name": "spectrum", "type_name": "Series", "resource_id": "slot:spectrum"},
            {"name": "metadata", "type_name": "Text", "resource_id": "slot:metadata"},
        ]
    }


def _base_payload() -> dict[str, Any]:
    return {
        "type_name": "DataObject",
        "summary": "A stub object the harness supplies in place of the person's data.",
        "fields": {"id": "stub-0", "created": "2026-01-01T00:00:00Z"},
    }


#: Recorded type name -> the display kind the running application resolves for
#: it. The names are the ones the built-in panel declarations claim
#: (``src/scistudio/panels/builtin/*/panel.json``), so a panel scaffolded for a
#: core type gets the envelope its neighbours get.
STUB_TYPE_KINDS: dict[str, EnvelopeKind] = {
    "Array": EnvelopeKind.ARRAY,
    "Artifact": EnvelopeKind.ARTIFACT,
    "Collection": EnvelopeKind.COLLECTION,
    "CompositeData": EnvelopeKind.COMPOSITE,
    "DataFrame": EnvelopeKind.DATAFRAME,
    "DataObject": EnvelopeKind.TEXT,
    "Image": EnvelopeKind.ARRAY,
    "PlotArtifact": EnvelopeKind.PLOT,
    "Series": EnvelopeKind.SERIES,
    "Text": EnvelopeKind.TEXT,
}

_PAYLOAD_BUILDERS = {
    EnvelopeKind.ARRAY: _array_payload,
    EnvelopeKind.ARTIFACT: _artifact_payload,
    EnvelopeKind.COLLECTION: _collection_payload,
    EnvelopeKind.COMPOSITE: _composite_payload,
    EnvelopeKind.DATAFRAME: _dataframe_payload,
    EnvelopeKind.PLOT: _plot_payload,
    EnvelopeKind.SERIES: _series_payload,
    EnvelopeKind.TEXT: _text_payload,
}


def stub_envelope(type_name: str, *, panel_id: str) -> dict[str, Any]:
    """Return the wire-form envelope the harness supplies for *type_name*.

    Args:
        type_name: A recorded data type name the panel declares as a target.
        panel_id: The panel the envelope is addressed to, so the harness's
            ``init`` reads exactly as the host's would.

    Returns:
        The JSON-safe dict :meth:`scistudio.panels.models.PreviewEnvelope.to_dict`
        produces, with a payload shaped like the matching built-in provider's.

    Example:
        >>> env = stub_envelope("DataFrame", panel_id="demo.table")
        >>> env["kind"], env["payload"]["columns"][0]
        ('dataframe', 'wavelength')
        >>> stub_envelope("NotARealType", panel_id="demo.table")["kind"]
        'text'
    """
    kind = STUB_TYPE_KINDS.get(type_name, EnvelopeKind.TEXT)
    builder = _PAYLOAD_BUILDERS.get(kind, _base_payload)
    payload = builder() if type_name in STUB_TYPE_KINDS else _base_payload()
    envelope = PreviewEnvelope(
        previewer_id=panel_id,
        target=PreviewTarget(kind=TargetKind.DATA_REF, ref=f"stub://harness/{type_name}"),
        kind=kind,
        payload=payload,
        session_id=None,
        metadata=PreviewMetadata(extra={"stub": True, "type_name": type_name}),
        diagnostics=(f"Stub data supplied by the panel harness for {type_name}.",),
    )
    return envelope.to_dict()


def stub_envelopes(type_names: tuple[str, ...] | list[str], *, panel_id: str) -> dict[str, dict[str, Any]]:
    """Return one stub envelope per declared target type, keyed by type name.

    A panel declaring no target type — one a block opens by name (spec 1 FR-017)
    — still needs something to render, so it is given the base object under the
    key ``"DataObject"``.
    """
    names = [name for name in type_names if name] or ["DataObject"]
    return {name: stub_envelope(name, panel_id=panel_id) for name in names}
