"""IOBlock.supported_extensions is deprecated-but-importable (spec §6.1).

Spec §6.1 marks ``IOBlock.supported_extensions`` ⚠️ deprecated: legacy ext->format
scaffolding, superseded by ``format_capabilities`` (ADR-043), removal per the §5
deprecation policy. It must stay importable (back-compat) while carrying a
deprecation marker.

RECONCILED AT INTEGRATION (#1833): the implementation marks the member deprecated
with a reST ``.. deprecated:: 0.3.1`` directive in the source comment immediately
above the ``supported_extensions`` ClassVar (pointing to ``format_capabilities``,
citing ADR-052 §5/§6.1). There is no ``"deprecated"`` stability tier (Tier =
stable|provisional|internal) and a ClassVar cannot carry a runtime ``@stable`` /
``@provisional`` / ``__deprecated__`` marker, so the deprecation is documented in
source rather than via a runtime warning mechanism. This test therefore asserts:
(a) ``supported_extensions`` stays accessible (back-compat); (b)
``format_capabilities`` is the documented replacement (exists as a ClassVar); and
(c) a ``.. deprecated::`` marker for ``supported_extensions`` is present in
``inspect.getsource(IOBlock)``.
"""

from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from _spec_data import DEPRECATED_MEMBERS, import_root

_SENTINEL = object()


@pytest.mark.parametrize(("root", "cls_name", "attr"), DEPRECATED_MEMBERS)
def test_member_still_importable(root: str, cls_name: str, attr: str) -> None:
    """(a) The deprecated member stays accessible for back-compat (spec §6.1)."""
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    cls = getattr(module, cls_name, None)
    assert cls is not None, f"{cls_name} not importable from {root}"
    assert inspect.getattr_static(cls, attr, _SENTINEL) is not _SENTINEL, (
        f"{cls_name}.{attr} must stay importable for back-compat (spec §6.1)"
    )


@pytest.mark.parametrize(("root", "cls_name", "attr"), DEPRECATED_MEMBERS)
def test_member_marked_deprecated(root: str, cls_name: str, attr: str) -> None:
    """(b) format_capabilities replaces it; (c) a `.. deprecated::` marker exists."""
    module = import_root(root)
    assert module is not None, f"{root} failed to import"
    cls = getattr(module, cls_name, None)
    assert cls is not None, f"{cls_name} not importable from {root}"

    # (b) the documented replacement exists as a ClassVar on the class itself.
    assert "format_capabilities" in vars(cls), (
        f"{cls_name}.format_capabilities — the documented replacement for "
        f"{attr} (spec §6.1 / ADR-052 §5/§6.1) — must exist as a ClassVar"
    )

    # (c) a reST `.. deprecated::` directive for `attr` is present in the source.
    # A ClassVar cannot carry a runtime marker and there is no "deprecated"
    # stability tier, so the deprecation is documented in the class source above
    # the ClassVar and points to format_capabilities (spec §6.1).
    source = inspect.getsource(cls)
    assert ".. deprecated::" in source, (
        f"{cls_name} source must carry a `.. deprecated::` directive for {attr} (spec §6.1); none found"
    )
    assert attr in source, f"{cls_name} source must reference the deprecated member {attr!r}"
    assert "format_capabilities" in source, (
        f"the `.. deprecated::` note for {attr} must point to the format_capabilities replacement (spec §6.1)"
    )
