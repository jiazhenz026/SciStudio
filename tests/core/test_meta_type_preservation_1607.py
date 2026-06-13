"""Regression tests for #1607 — return-type preservation in the core meta helpers.

The #1607 fix wrapped two pydantic ``model_copy`` calls in ``typing.cast`` so the
type checker sees the correct (non-``Any``) return types
(``with_meta_changes(meta: T) -> T`` and ``FrameworkMeta.with_lineage_id ->
FrameworkMeta``) and re-bound ``meta`` as ``type[BaseModel]`` before
``model_validate`` in the registry. The casts are type-only, but these tests pin
the *runtime* contract they assert: each helper returns an instance of the
original concrete type (not a bare ``BaseModel``), with immutability preserved —
so a future change that actually broke the return type would fail here, not just
in mypy.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scistudio.core.meta._with_meta import with_meta_changes
from scistudio.core.meta.framework import FrameworkMeta


class _SampleMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    a: int = 1
    b: str = "x"


def test_with_meta_changes_preserves_concrete_subclass_type() -> None:
    original = _SampleMeta(a=1, b="x")
    updated = with_meta_changes(original, a=2)

    # The cast(T, ...) must hold at runtime: same concrete subclass, not BaseModel.
    assert type(updated) is _SampleMeta
    assert updated.a == 2
    assert updated.b == "x"
    # Original is unchanged (immutable update).
    assert original.a == 1


def test_framework_meta_with_lineage_id_returns_frameworkmeta() -> None:
    fm = FrameworkMeta(source="raw.tif")
    stamped = fm.with_lineage_id("be-abc123")

    assert type(stamped) is FrameworkMeta
    assert stamped.lineage_id == "be-abc123"
    # Every other field is preserved by the immutable copy.
    assert stamped.object_id == fm.object_id
    assert stamped.source == fm.source
    # The original is untouched.
    assert fm.lineage_id != "be-abc123"
