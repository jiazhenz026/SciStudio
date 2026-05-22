"""Module-level helpers for :mod:`scistudio.engine.scheduler`.

ADR-046 §3 keeps these three helpers visible at the
``scistudio.engine.scheduler.<name>`` import path (audit tooling and
existing callers expect that surface). They live in this private
sibling so :mod:`_lineage` can import them without a circular load
with the package ``__init__``; the canonical names are re-exported
from ``scheduler/__init__.py``.

Pure structural relocation per umbrella #1427 Phase 3 — semantics are
byte-identical to the pre-decomposition definitions.
"""

from __future__ import annotations

from typing import Any

_MAX_ERROR_SUMMARY_LEN = 120


def _extract_error_summary(error_text: str) -> str:
    """Return a short summary from an error/traceback string.

    Uses the last non-empty line (typically the actual exception message),
    truncated to ``_MAX_ERROR_SUMMARY_LEN`` characters.
    """
    lines = [ln.strip() for ln in error_text.splitlines() if ln.strip()]
    summary = lines[-1] if lines else error_text
    if len(summary) > _MAX_ERROR_SUMMARY_LEN:
        summary = summary[: _MAX_ERROR_SUMMARY_LEN - 1] + "…"
    return summary


def _collect_object_ids(payload: Any) -> dict[str, list[str]]:
    """Extract ``{port_name: [object_id, ...]}`` from a wire-format dict.

    ADR-038 §3.2 expects the scheduler to feed the LineageRecorder a
    pre-computed object-id map so it can write ``block_io`` rows without
    re-parsing the wire format. Scalars and Collection items are both
    flattened to a list per port. Ports whose values are not DataObject
    wire payloads (e.g. plain ints) are skipped silently.
    """
    if not isinstance(payload, dict):
        return {}

    result: dict[str, list[str]] = {}
    for port_name, value in payload.items():
        if port_name == "__scistudio_env__":
            continue
        ids = _object_ids_for_value(value)
        if ids:
            result[str(port_name)] = ids
    return result


def _object_ids_for_value(value: Any) -> list[str]:
    """Recursively extract object_ids from a single wire-format port value."""
    if isinstance(value, dict):
        if value.get("_collection"):
            ids: list[str] = []
            for item in value.get("items", []) or []:
                ids.extend(_object_ids_for_value(item))
            return ids
        framework = (value.get("metadata") or {}).get("framework") or {}
        candidate = framework.get("object_id")
        if isinstance(candidate, str) and candidate:
            return [candidate]
    return []
