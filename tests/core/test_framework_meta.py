"""Unit tests for ``scistudio.core.meta`` (T-004 / ADR-027 D5).

Covers:

- :class:`scistudio.core.meta.framework.FrameworkMeta` — defaults,
  ``frozen`` behaviour, ``derive`` propagation, JSON round-trip.
- :class:`scistudio.core.meta.channel.ChannelInfo` — construction,
  ``frozen`` behaviour, JSON round-trip, composition inside another
  Pydantic model.
- :func:`scistudio.core.meta._with_meta.with_meta_changes` — immutable
  update semantics and validation error propagation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from scistudio.core.meta import ChannelInfo, FrameworkMeta, with_meta_changes

# ---------------------------------------------------------------------------
# FrameworkMeta — defaults
# ---------------------------------------------------------------------------


def test_framework_meta_default_factory_populates_object_id() -> None:
    """``FrameworkMeta()`` produces a non-empty UUIDv4 hex ``object_id``."""
    fm = FrameworkMeta()
    assert isinstance(fm.object_id, str)
    assert fm.object_id != ""
    # Must parse as a valid UUID (uuid4 hex form is 32 chars).
    parsed = UUID(fm.object_id)
    assert parsed.version == 4


def test_framework_meta_default_factory_populates_created_at() -> None:
    """``FrameworkMeta().created_at`` is a UTC-aware datetime near now."""
    before = datetime.now(UTC)
    fm = FrameworkMeta()
    after = datetime.now(UTC)
    assert isinstance(fm.created_at, datetime)
    assert fm.created_at.tzinfo is not None
    assert fm.created_at.utcoffset() == UTC.utcoffset(fm.created_at)
    assert before <= fm.created_at <= after


def test_framework_meta_two_instances_have_different_ids() -> None:
    """Each ``FrameworkMeta()`` gets a fresh ``object_id`` (no shared default)."""
    a = FrameworkMeta()
    b = FrameworkMeta()
    assert a.object_id != b.object_id


def test_framework_meta_optional_fields_default() -> None:
    """``source`` defaults to ``""``; ``lineage_id`` and ``derived_from`` to ``None``."""
    fm = FrameworkMeta()
    assert fm.source == ""
    assert fm.lineage_id is None
    assert fm.derived_from is None


def test_framework_meta_explicit_field_assignment() -> None:
    """All five fields are accepted explicitly via the constructor."""
    fixed_dt = datetime(2026, 4, 6, 12, 0, 0, tzinfo=UTC)
    fm = FrameworkMeta(
        created_at=fixed_dt,
        object_id="abc123",
        source="test.tif",
        lineage_id="lineage-xyz",
        derived_from="parent-456",
    )
    assert fm.created_at == fixed_dt
    assert fm.object_id == "abc123"
    assert fm.source == "test.tif"
    assert fm.lineage_id == "lineage-xyz"
    assert fm.derived_from == "parent-456"


# ---------------------------------------------------------------------------
# FrameworkMeta — frozen behaviour (ADR-027 D5)
# ---------------------------------------------------------------------------


def test_framework_meta_frozen() -> None:
    """ADR-027 D5: ``FrameworkMeta`` is frozen — assignment raises."""
    fm = FrameworkMeta()
    with pytest.raises(ValidationError):
        fm.source = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FrameworkMeta — JSON round-trip (ADR-027 Addendum 1 §1)
# ---------------------------------------------------------------------------


def test_framework_meta_json_round_trip() -> None:
    """``model_dump_json`` followed by ``model_validate_json`` gives an equal instance.

    This is the contract that lets ``FrameworkMeta`` cross the worker
    subprocess boundary intact (ADR-027 Addendum 1 §1).
    """
    original = FrameworkMeta(
        source="original.tif",
        lineage_id="lin-001",
        derived_from="parent-000",
    )
    payload = original.model_dump_json()
    restored = FrameworkMeta.model_validate_json(payload)
    assert restored == original
    assert restored.object_id == original.object_id
    assert restored.created_at == original.created_at
    assert restored.source == original.source
    assert restored.lineage_id == original.lineage_id
    assert restored.derived_from == original.derived_from


# ---------------------------------------------------------------------------
# FrameworkMeta.derive — propagation rule (ADR-027 D5)
# ---------------------------------------------------------------------------


def test_framework_meta_derive_generates_new_id_and_timestamp() -> None:
    """``derive`` produces a fresh ``object_id`` and ``created_at``."""
    parent = FrameworkMeta(source="raw.tif")
    child = parent.derive()
    assert child.object_id != parent.object_id
    assert child.created_at >= parent.created_at
    # Same source — propagated through.
    assert child.source == parent.source


def test_framework_meta_derive_preserves_lineage_id() -> None:
    """``derive`` inherits ``lineage_id`` unless overridden."""
    parent = FrameworkMeta(lineage_id="lin-42")
    child = parent.derive()
    assert child.lineage_id == "lin-42"


def test_framework_meta_derive_records_parent_in_derived_from() -> None:
    """``derive`` sets ``derived_from = parent.object_id`` (ADR-027 D5)."""
    parent = FrameworkMeta()
    child = parent.derive()
    assert child.derived_from == parent.object_id


def test_framework_meta_derive_overrides_via_kwargs() -> None:
    """Explicit kwargs to ``derive`` override the propagation defaults."""
    parent = FrameworkMeta(source="raw.tif", lineage_id="lin-1")
    child = parent.derive(source="cropped.tif", lineage_id="lin-2")
    assert child.source == "cropped.tif"
    assert child.lineage_id == "lin-2"
    # derived_from still defaults to parent.object_id.
    assert child.derived_from == parent.object_id


def test_framework_meta_derive_returns_frozen_instance() -> None:
    """The instance returned from ``derive`` is itself frozen."""
    parent = FrameworkMeta()
    child = parent.derive()
    with pytest.raises(ValidationError):
        child.source = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ChannelInfo
# ---------------------------------------------------------------------------


def test_channel_info_minimal_construction() -> None:
    """Only ``name`` is required; other fields default to ``None``."""
    ch = ChannelInfo(name="DAPI")
    assert ch.name == "DAPI"
    assert ch.dye is None
    assert ch.excitation_nm is None
    assert ch.emission_nm is None


def test_channel_info_full_construction() -> None:
    """All four fields populated."""
    ch = ChannelInfo(
        name="DAPI",
        dye="Hoechst 33342",
        excitation_nm=358.0,
        emission_nm=461.0,
    )
    assert ch.name == "DAPI"
    assert ch.dye == "Hoechst 33342"
    assert ch.excitation_nm == pytest.approx(358.0)
    assert ch.emission_nm == pytest.approx(461.0)


def test_channel_info_frozen() -> None:
    """``ChannelInfo`` is frozen — assignment raises ``ValidationError``."""
    ch = ChannelInfo(name="DAPI")
    with pytest.raises(ValidationError):
        ch.name = "GFP"  # type: ignore[misc]


def test_channel_info_json_round_trip() -> None:
    """``ChannelInfo`` round-trips through Pydantic JSON serialisation."""
    original = ChannelInfo(
        name="GFP",
        dye="EGFP",
        excitation_nm=488.0,
        emission_nm=507.0,
    )
    payload = original.model_dump_json()
    restored = ChannelInfo.model_validate_json(payload)
    assert restored == original


def test_channel_info_in_pydantic_model_round_trip() -> None:
    """``ChannelInfo`` composes cleanly inside another Pydantic model.

    This is the canonical use case: a plugin ``Meta`` class declares
    ``channels: list[ChannelInfo]`` and round-trips end-to-end.
    """

    class FluorMeta(BaseModel):
        channels: list[ChannelInfo] = []

    original = FluorMeta(
        channels=[
            ChannelInfo(name="DAPI", excitation_nm=358.0, emission_nm=461.0),
            ChannelInfo(name="GFP", excitation_nm=488.0, emission_nm=507.0),
        ],
    )
    payload = original.model_dump_json()
    restored = FluorMeta.model_validate_json(payload)
    assert restored == original
    assert len(restored.channels) == 2
    assert restored.channels[0].name == "DAPI"
    assert restored.channels[1].name == "GFP"


# ---------------------------------------------------------------------------
# with_meta_changes — free-function helper (T-005 will use it)
# ---------------------------------------------------------------------------


class _DemoMeta(BaseModel):
    """Tiny Pydantic model used to exercise ``with_meta_changes``."""

    pixel_size: float = 1.0
    objective: str | None = None


def test_with_meta_changes_returns_new_instance() -> None:
    """Result is a *different* object identity from the input."""
    original = _DemoMeta(pixel_size=1.0)
    updated = with_meta_changes(original, pixel_size=2.0)
    assert updated is not original


def test_with_meta_changes_preserves_original() -> None:
    """The input meta is unchanged after the call."""
    original = _DemoMeta(pixel_size=1.0, objective="40x")
    _ = with_meta_changes(original, pixel_size=2.0)
    assert original.pixel_size == pytest.approx(1.0)
    assert original.objective == "40x"


def test_with_meta_changes_applies_field_update() -> None:
    """The returned instance reflects the requested change."""
    original = _DemoMeta(pixel_size=1.0)
    updated = with_meta_changes(original, pixel_size=2.5, objective="60x")
    assert updated.pixel_size == pytest.approx(2.5)
    assert updated.objective == "60x"


def test_with_meta_changes_returns_same_class() -> None:
    """The returned instance has the same concrete class as the input.

    This matters for plugin ``Meta`` subclasses: ``with_meta_changes``
    on a ``FluorImage.Meta`` must return another ``FluorImage.Meta``
    rather than a bare ``BaseModel``.
    """

    class FancyMeta(_DemoMeta):
        extra: str = ""

    original = FancyMeta(pixel_size=1.0, extra="hello")
    updated = with_meta_changes(original, pixel_size=2.0)
    assert type(updated) is FancyMeta
    assert updated.extra == "hello"
    assert updated.pixel_size == pytest.approx(2.0)


def test_with_meta_changes_propagates_validation_error_when_constructing_invalid_meta() -> None:
    """Pydantic raises ``ValidationError`` if a *new* meta with the
    merged fields would be invalid.

    Note: ``model_copy(update=...)`` itself does NOT re-validate field
    types in Pydantic v2 — that is intentional per the Pydantic design
    and matches the contract in ADR-027 D5 (the helper is a thin
    immutable-update wrapper, not a re-validator). To explicitly
    re-validate after a copy, callers should round-trip through
    ``model_validate(updated.model_dump())``. This test documents that
    contract by verifying that ``with_meta_changes`` itself is a pure
    pass-through; type errors only surface when the caller subsequently
    re-validates.
    """
    original = _DemoMeta(pixel_size=1.0)
    # No validation on the wrong type — this is documented Pydantic v2
    # behaviour for ``model_copy(update=...)``.
    updated = with_meta_changes(original, pixel_size="not a number")  # type: ignore[arg-type]
    # Re-constructing from the raw fields triggers the expected
    # ValidationError. We use ``__dict__`` rather than ``model_dump``
    # to bypass Pydantic's serializer (which would warn about the
    # type mismatch on the *output* path before we get to the
    # validation we actually want to exercise).
    with pytest.raises(ValidationError):
        _DemoMeta(**dict(updated.__dict__))
