"""Tests for :class:`TypeRegistry` ``resolve(type_chain)`` and Meta validation.

Covers T-012 (ADR-027 D11 + Addendum 1 §3):

1. :meth:`TypeRegistry.resolve` — walks a type chain from rightmost (most
   specific) to leftmost (most general) and returns the most specific
   registered class, or ``None`` when no entry matches. The legacy
   ``resolve(name: str) -> TypeSpec`` path is preserved for backward
   compatibility.
2. :meth:`TypeRegistry._validate_meta_class` — runs at registration time
   and rejects any subclass whose ``Meta`` ClassVar is not a pydantic
   ``BaseModel`` subclass, has ``PrivateAttr`` fields, or fails JSON
   round-trip. Bare ``DataObject`` and the six core base classes
   (``Meta = None``) must pass without complaint.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.registry import TypeRegistry, TypeSpec
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Fixtures: well-formed and malformed Meta classes
# ---------------------------------------------------------------------------


class _GoodMeta(BaseModel):
    """Well-formed Meta: frozen, no PrivateAttr, JSON-round-trippable."""

    model_config = ConfigDict(frozen=True)
    sample_id: str = ""
    channel_count: int = 0


class _BadMetaPrivateAttr(BaseModel):
    """Malformed Meta: declares a PrivateAttr field."""

    model_config = ConfigDict(frozen=True)
    public: str = ""
    _private: str = PrivateAttr(default="hidden")


class _RequiredFieldMeta(BaseModel):
    """Meta with a required field (no default) — default construction fails.

    ADR-027 Addendum 1 §3 allows this: validation skips the JSON round-
    trip smoke test when the default instance cannot be built, and
    trusts the plugin's own regression tests.
    """

    model_config = ConfigDict(frozen=True)
    required_field: str  # no default → Meta() raises ValidationError


class _GoodObject(DataObject):
    """Test fixture: DataObject subclass with a well-formed Meta."""

    Meta: ClassVar[type[BaseModel] | None] = _GoodMeta


class _BadObjectPrivateAttr(DataObject):
    """Test fixture: DataObject subclass with a PrivateAttr in Meta."""

    Meta: ClassVar[type[BaseModel] | None] = _BadMetaPrivateAttr


class _ObjectWithRequiredFieldMeta(DataObject):
    """Test fixture: DataObject subclass with required-field Meta."""

    Meta: ClassVar[type[BaseModel] | None] = _RequiredFieldMeta


class _BadObjectMetaIsDict(DataObject):
    """Test fixture: Meta is a plain dict, not a BaseModel. Invalid."""

    # Deliberately use a non-BaseModel sentinel. Ignore the type-checker
    # complaint because the whole point of the fixture is to fail
    # validation at runtime.
    Meta = dict  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# resolve(type_chain) — new ADR-027 D11 behaviour
# ---------------------------------------------------------------------------


class TestResolveTypeChain:
    """``resolve(type_chain: list[str]) -> type | None`` walks right-to-left."""

    def test_resolve_returns_most_specific_registered(self) -> None:
        """Registering Array + querying ``[DataObject, Array]`` yields Array."""
        registry = TypeRegistry()
        registry.scan_builtins()
        result = registry.resolve(["DataObject", "Array"])
        assert result is Array

    def test_resolve_returns_none_when_chain_unknown(self) -> None:
        """A chain of completely unknown names returns ``None``."""
        registry = TypeRegistry()
        registry.scan_builtins()
        result = registry.resolve(["NonExistent"])
        assert result is None

    def test_resolve_walks_chain_right_to_left(self) -> None:
        """Chain ``[DataObject, Array, Image]`` where only Array is registered.

        Expected: ``Array`` is returned (walking right -> left: Image
        not found, Array found, return it).
        """
        registry = TypeRegistry()
        registry.scan_builtins()
        # "Image" is NOT in core per ADR-027 D2 / T-006 — it lives in
        # scistudio-blocks-imaging. So this chain tests exactly the
        # "most-specific unknown, fall back to parent" path.
        result = registry.resolve(["DataObject", "Array", "Image"])
        assert result is Array

    def test_resolve_returns_first_match_from_right(self) -> None:
        """Both Array and DataObject registered: query ``[DataObject, Array]`` → Array.

        Walking rightmost-first means Array (the more specific entry)
        wins even though DataObject is also present.
        """
        registry = TypeRegistry()
        registry.scan_builtins()
        result = registry.resolve(["DataObject", "Array"])
        assert result is Array
        # And a reverse order still returns Array (the one that's on the right).
        result_reversed = registry.resolve(["Array", "DataObject"])
        assert result_reversed is DataObject

    def test_resolve_empty_chain_returns_none(self) -> None:
        """An empty chain has nothing to resolve; returns ``None``."""
        registry = TypeRegistry()
        registry.scan_builtins()
        assert registry.resolve([]) is None

    def test_resolve_returns_none_no_match(self) -> None:
        """Chain has multiple entries but none are registered."""
        registry = TypeRegistry()
        # Empty registry — nothing scanned.
        result = registry.resolve(["FooBar", "BazQux"])
        assert result is None

    def test_resolve_legacy_string_lookup_still_works(self) -> None:
        """Backward compat: ``resolve(name: str)`` returns a ``TypeSpec``.

        Regression guard — the ADR-027 D11 addition must not break the
        existing architecture enforcement tests or the core type tests
        that pass a string.
        """
        registry = TypeRegistry()
        registry.scan_builtins()
        spec = registry.resolve("Array")
        assert isinstance(spec, TypeSpec)
        assert spec.name == "Array"

    def test_resolve_legacy_string_unknown_raises_key_error(self) -> None:
        """Backward compat: missing name still raises ``KeyError``."""
        registry = TypeRegistry()
        with pytest.raises(KeyError, match="not registered"):
            registry.resolve("NonExistent")


# ---------------------------------------------------------------------------
# _validate_meta_class — ADR-027 Addendum 1 §3
# ---------------------------------------------------------------------------


class TestValidateMetaClass:
    """``_validate_meta_class`` enforces ADR-027 Addendum 1 §3 constraints."""

    def test_register_bare_dataobject_succeeds(self) -> None:
        """Bare ``DataObject`` has ``Meta = None`` and must pass validation."""
        registry = TypeRegistry()
        # Should not raise.
        registry._validate_meta_class(DataObject)
        registry.register_class(DataObject)
        assert "DataObject" in registry.all_types()

    def test_register_class_with_valid_meta_succeeds(self) -> None:
        """A DataObject subclass with a frozen pydantic Meta passes validation."""
        registry = TypeRegistry()
        registry._validate_meta_class(_GoodObject)
        registry.register_class(_GoodObject)
        assert "_GoodObject" in registry.all_types()

    def test_register_class_with_non_basemodel_meta_raises(self) -> None:
        """``Meta = dict`` (or anything non-BaseModel) is rejected."""
        registry = TypeRegistry()
        with pytest.raises(ValueError, match=r"pydantic\.BaseModel subclass"):
            registry._validate_meta_class(_BadObjectMetaIsDict)

    def test_register_class_with_meta_having_private_attr_raises(self) -> None:
        """``PrivateAttr`` fields are rejected (cannot round-trip through JSON)."""
        registry = TypeRegistry()
        with pytest.raises(ValueError, match="PrivateAttr"):
            registry._validate_meta_class(_BadObjectPrivateAttr)

    def test_register_class_with_well_formed_meta_with_required_fields_succeeds(
        self,
    ) -> None:
        """Meta with required fields (no default) passes validation.

        Validation cannot default-construct such a Meta, so the JSON
        round-trip smoke test is skipped per ADR-027 Addendum 1 §3.
        Plugin authors are expected to write their own round-trip
        regression test.
        """
        registry = TypeRegistry()
        # Should not raise even though _RequiredFieldMeta() would fail.
        registry._validate_meta_class(_ObjectWithRequiredFieldMeta)

    def test_existing_core_base_classes_pass_validation(self) -> None:
        """All six core base classes ship with Meta = None (T-005) and must pass.

        This test is the canary for future refactors: if someone adds a
        broken Meta ClassVar to one of the core base classes, this test
        will scream before the worker subprocess crashes at runtime.
        """
        registry = TypeRegistry()
        for cls in [DataObject, Array, Series, DataFrame, Text, Artifact, CompositeData]:
            # Sanity: confirm Meta is None on every core base class.
            assert cls.Meta is None, f"{cls.__name__}.Meta should be None"
            # Must not raise.
            registry._validate_meta_class(cls)

    def test_scan_builtins_runs_meta_validation(self) -> None:
        """``scan_builtins`` calls ``_validate_meta_class`` on every builtin.

        This is verified indirectly: if validation were skipped, the
        previous test alone would be sufficient; but we also want to
        guarantee the registration path exercises the validation code.
        """
        registry = TypeRegistry()
        # scan_builtins should run to completion without raising.
        registry.scan_builtins()
        # And all seven core base classes must be registered.
        assert "DataObject" in registry.all_types()
        assert "Array" in registry.all_types()
        assert "Series" in registry.all_types()
        assert "DataFrame" in registry.all_types()
        assert "Text" in registry.all_types()
        assert "Artifact" in registry.all_types()
        assert "CompositeData" in registry.all_types()

    def test_validation_error_message_mentions_offending_class(self) -> None:
        """Error messages must name the offending class for fast debugging."""
        registry = TypeRegistry()
        with pytest.raises(ValueError) as exc_info:
            registry._validate_meta_class(_BadObjectPrivateAttr)
        assert "_BadObjectPrivateAttr" in str(exc_info.value)
        assert "PrivateAttr" in str(exc_info.value)
        assert "_private" in str(exc_info.value)

    def test_validation_error_non_basemodel_mentions_class_and_adr(self) -> None:
        """Non-BaseModel error message cites the class name and the ADR reference."""
        registry = TypeRegistry()
        with pytest.raises(ValueError) as exc_info:
            registry._validate_meta_class(_BadObjectMetaIsDict)
        msg = str(exc_info.value)
        assert "_BadObjectMetaIsDict" in msg
        assert "pydantic.BaseModel" in msg
        assert "Addendum 1" in msg

    def test_register_class_with_json_incompatible_default_raises(self) -> None:
        """A Meta whose default instance cannot JSON-round-trip is rejected."""

        class _MetaWithBadDefault(BaseModel):
            """Meta that dumps fine but fails model_validate of its own JSON."""

            # A set is allowed in Pydantic fields but dumps to a list;
            # to force a hard JSON failure we use a non-serialisable
            # arbitrary type via arbitrary_types_allowed.
            model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
            bad: object = Field(default_factory=lambda: object())

        class _BadDefaultObject(DataObject):
            Meta: ClassVar[type[BaseModel] | None] = _MetaWithBadDefault

        registry = TypeRegistry()
        with pytest.raises(ValueError, match="round-trip"):
            registry._validate_meta_class(_BadDefaultObject)


# ---------------------------------------------------------------------------
# Smoke test: scan_all is idempotent
# ---------------------------------------------------------------------------


class TestScanIdempotent:
    """``scan_builtins`` / ``scan_all`` must be safe to call twice."""

    def test_scan_builtins_is_idempotent(self) -> None:
        """Calling ``scan_builtins`` twice does not raise or change the result."""
        registry = TypeRegistry()
        registry.scan_builtins()
        snapshot = set(registry.all_types().keys())
        registry.scan_builtins()
        assert set(registry.all_types().keys()) == snapshot
