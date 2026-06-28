"""IOBlock.supported_extensions is deprecated-but-importable (spec §6.1).

Spec §6.1 marks ``IOBlock.supported_extensions`` ⚠️ deprecated: legacy ext->format
scaffolding, superseded by ``format_capabilities``, removal per the §5 deprecation
policy. It must stay importable (back-compat) while carrying a deprecation marker.

INTERPRETED AMBIGUITY: ``scistudio.stability`` currently defines only
``Tier = stable|provisional|internal`` -- there is no ``"deprecated"`` tier, and
the spec does not pin the exact marker mechanism (#1817 decides it). This test
therefore (a) asserts the member stays accessible, and (b) accepts ANY of the
plausible #1817 deprecation conventions: a ``"deprecated"`` stability tier, a
``DeprecationWarning`` on access, or a ``__deprecated__``-style registry/marker.

EXPECTED TO FAIL on part (b) in the pre-implementation tree (no marker yet);
part (a) accessibility may already pass. Written correct-by-spec.
"""

from __future__ import annotations

import inspect
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from _spec_data import DEPRECATED_MEMBERS
from conftest import import_root

from scistudio.stability import get_stability

_DEPRECATION_TIERS = {"deprecated"}
_REGISTRY_ATTRS = ("__deprecated__", "__deprecated_members__", "_deprecated", "_deprecated_members")
_MARKER_ATTRS = ("__deprecated__", "__scistudio_deprecated__")


def _deprecation_signal(cls, attr: str) -> str | None:
    """Return a human description of a deprecation signal on ``cls.attr``, else None."""
    static = inspect.getattr_static(cls, attr, None)

    # (1) a stability tier extended to mark deprecation.
    info = get_stability(static) or get_stability(getattr(cls, attr, None))
    if info is not None and info.tier in _DEPRECATION_TIERS:
        return f"stability tier={info.tier!r}"

    # (2) an explicit per-attribute or class-level deprecation registry.
    for reg in _REGISTRY_ATTRS:
        members = getattr(cls, reg, None)
        if members and attr in members:
            return f"registry {reg}={members!r}"

    # (3) a marker attribute on the descriptor/value object.
    for marker in _MARKER_ATTRS:
        if getattr(static, marker, None) or getattr(getattr(cls, attr, None), marker, None):
            return f"marker attribute {marker!r}"

    # (4) a DeprecationWarning emitted on access (property-backed deprecation).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            _ = getattr(cls, attr)
        except Exception:  # noqa: BLE001
            pass
    if any(issubclass(w.category, DeprecationWarning) for w in caught):
        return "DeprecationWarning on access"

    return None


@pytest.mark.parametrize(("root", "cls_name", "attr"), DEPRECATED_MEMBERS)
def test_member_still_importable(root: str, cls_name: str, attr: str) -> None:
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    cls = getattr(module, cls_name, None)
    assert cls is not None, f"{cls_name} not importable from {root}"
    assert inspect.getattr_static(cls, attr, _SENTINEL := object()) is not _SENTINEL, (
        f"{cls_name}.{attr} must stay importable for back-compat (spec §6.1)"
    )


@pytest.mark.parametrize(("root", "cls_name", "attr"), DEPRECATED_MEMBERS)
def test_member_marked_deprecated(root: str, cls_name: str, attr: str) -> None:
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    cls = getattr(module, cls_name, None)
    assert cls is not None, f"{cls_name} not importable from {root}"
    signal = _deprecation_signal(cls, attr)
    assert signal is not None, (
        f"{cls_name}.{attr} must carry a deprecation marker (spec §6.1); checked a "
        f"'deprecated' stability tier, a deprecation registry/marker, and a "
        f"DeprecationWarning on access -- none present"
    )
