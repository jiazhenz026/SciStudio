"""Regression tests for T-007: other base classes audit per ADR-027 D2 + D5.

This module verifies two invariants on the five non-Array core base
classes (``Series``, ``DataFrame``, ``CompositeData``, ``Text``,
``Artifact``):

1. **ADR-027 D2** — no domain subtypes exist in the core modules. Any
   class like ``Spectrum``, ``PeakTable``, ``AnnData`` that was removed
   as part of T-007 must stay removed.

2. **ADR-027 D5 / T-005 three-slot integration** — each base class
   accepts the standard ``framework=``, ``meta=``, ``user=``,
   ``storage_ref=`` kwargs via ``**kwargs`` pass-through, and (since
   each base class has its own constructor args) overrides
   :meth:`DataObject.with_meta` to propagate those extra args through
   the immutable-update path.

T-006 landed the analogous contract for ``Array``; T-007 brings the
remaining five base classes in line.
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from scistudio.core.meta import FrameworkMeta
from scistudio.core.types import artifact as artifact_module
from scistudio.core.types import composite as composite_module
from scistudio.core.types import dataframe as dataframe_module
from scistudio.core.types import series as series_module
from scistudio.core.types import text as text_module
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Test fixtures: tiny typed Meta models + matching subclasses for each
# base class. T-005's ``DataObject.with_meta`` requires a non-None Meta
# on the instance, so we exercise it via small local subclasses that
# declare their own Pydantic Meta model (the same pattern T-005 used in
# ``test_stratified_metadata.py`` and T-006 used in ``test_array_axes.py``).
# ---------------------------------------------------------------------------


class _SeriesMeta(BaseModel):
    """Typed Meta for the Series three-slot integration test."""

    field: int = 0
    label: str = ""


class _TypedSeries(Series):
    """Series subclass declaring a typed Meta for with_meta() tests."""

    Meta = _SeriesMeta


class _DataFrameMeta(BaseModel):
    """Typed Meta for the DataFrame three-slot integration test."""

    field: int = 0
    label: str = ""


class _TypedDataFrame(DataFrame):
    """DataFrame subclass declaring a typed Meta for with_meta() tests."""

    Meta = _DataFrameMeta


class _CompositeMeta(BaseModel):
    """Typed Meta for the CompositeData three-slot integration test."""

    field: int = 0
    label: str = ""


class _TypedComposite(CompositeData):
    """CompositeData subclass declaring a typed Meta for with_meta() tests."""

    Meta = _CompositeMeta


class _TextMeta(BaseModel):
    """Typed Meta for the Text three-slot integration test."""

    field: int = 0
    label: str = ""


class _TypedText(Text):
    """Text subclass declaring a typed Meta for with_meta() tests."""

    Meta = _TextMeta


class _ArtifactMeta(BaseModel):
    """Typed Meta for the Artifact three-slot integration test."""

    field: int = 0
    label: str = ""


class _TypedArtifact(Artifact):
    """Artifact subclass declaring a typed Meta for with_meta() tests."""

    Meta = _ArtifactMeta


def _concrete_dataobject_classes(module) -> list[str]:
    """Return the names of concrete DataObject subclasses defined in *module*.

    Filters out classes imported from other modules (by comparing
    ``cls.__module__``) so that, e.g., ``DataObject`` re-imported from
    ``base.py`` is not counted against ``series.py``'s quota.
    """
    names: list[str] = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, DataObject):
            continue
        if obj.__module__ != module.__name__:
            continue
        names.append(name)
    return names


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


class TestSeriesIntegration:
    """Series audit + three-slot integration."""

    def test_series_construction_with_three_slot_kwargs(self) -> None:
        """Series accepts framework / meta / user kwargs via **kwargs."""
        s = Series(
            index_name="t",
            value_name="intensity",
            length=100,
            framework=FrameworkMeta(source="test"),
            user={"notes": "unit test"},
        )
        assert s.index_name == "t"
        assert s.value_name == "intensity"
        assert s.length == 100
        assert s.framework.source == "test"
        assert s.user == {"notes": "unit test"}
        assert s.meta is None  # base Series has no Meta ClassVar

    def test_series_with_meta_propagates_extra_kwargs(self) -> None:
        """with_meta() preserves Series-specific constructor args."""
        s = _TypedSeries(
            index_name="t",
            value_name="intensity",
            length=100,
            meta=_SeriesMeta(field=1, label="a"),
            user={"x": 1},
        )
        new = s.with_meta(field=42)

        # Meta fields were updated
        assert isinstance(new.meta, _SeriesMeta)
        assert new.meta.field == 42
        assert new.meta.label == "a"  # unchanged

        # Series-specific constructor args were propagated
        assert new.index_name == "t"
        assert new.value_name == "intensity"
        assert new.length == 100

        # Standard slots were propagated
        assert new.user == {"x": 1}
        assert new.framework.derived_from == s.framework.object_id

    def test_series_with_meta_raises_when_meta_is_none(self) -> None:
        """Base Series has no Meta; with_meta() must refuse."""
        s = Series(index_name="t")
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            s.with_meta(field=1)

    def test_series_no_domain_subclasses_in_module(self) -> None:
        """ADR-027 D2: series.py contains only Series (no Spectrum)."""
        classes = _concrete_dataobject_classes(series_module)
        assert classes == ["Series"], (
            f"Expected series.py to contain only 'Series'; found {classes}. "
            f"Domain subtypes must live in plugin packages per ADR-027 D2."
        )
        # Also explicitly assert the deleted names are gone.
        for deleted in ("Spectrum", "RamanSpectrum", "MassSpectrum"):
            assert not hasattr(series_module, deleted), (
                f"series.py must not define '{deleted}' — it belongs in scistudio-blocks-spectral."
            )


# ---------------------------------------------------------------------------
# DataFrame
# ---------------------------------------------------------------------------


class TestDataFrameIntegration:
    """DataFrame audit + three-slot integration."""

    def test_dataframe_construction_with_three_slot_kwargs(self) -> None:
        df = DataFrame(
            columns=["mz", "intensity"],
            row_count=10,
            schema={"mz": "float64"},
            framework=FrameworkMeta(source="test"),
            user={"notes": "unit test"},
        )
        assert df.columns == ["mz", "intensity"]
        assert df.row_count == 10
        assert df.schema == {"mz": "float64"}
        assert df.framework.source == "test"
        assert df.user == {"notes": "unit test"}
        assert df.meta is None

    def test_dataframe_with_meta_propagates_extra_kwargs(self) -> None:
        df = _TypedDataFrame(
            columns=["a", "b"],
            row_count=5,
            schema={"a": "int"},
            meta=_DataFrameMeta(field=1, label="x"),
            user={"k": "v"},
        )
        new = df.with_meta(field=99)

        assert isinstance(new.meta, _DataFrameMeta)
        assert new.meta.field == 99
        assert new.meta.label == "x"

        assert new.columns == ["a", "b"]
        assert new.row_count == 5
        assert new.schema == {"a": "int"}

        assert new.user == {"k": "v"}
        assert new.framework.derived_from == df.framework.object_id

    def test_dataframe_with_meta_preserves_columns_as_independent_copy(self) -> None:
        """Mutating the new DataFrame's columns list does not affect the original."""
        df = _TypedDataFrame(columns=["a", "b"], meta=_DataFrameMeta())
        new = df.with_meta(field=1)
        assert new.columns is not df.columns
        new.columns.append("c")
        assert df.columns == ["a", "b"]

    def test_dataframe_with_meta_raises_when_meta_is_none(self) -> None:
        df = DataFrame(columns=["a"])
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            df.with_meta(field=1)

    def test_dataframe_no_domain_subclasses_in_module(self) -> None:
        """ADR-027 D2: dataframe.py contains only DataFrame."""
        classes = _concrete_dataobject_classes(dataframe_module)
        assert classes == ["DataFrame"], f"Expected dataframe.py to contain only 'DataFrame'; found {classes}."
        for deleted in ("PeakTable", "MetabPeakTable"):
            assert not hasattr(dataframe_module, deleted), (
                f"dataframe.py must not define '{deleted}' — it belongs in scistudio-blocks-spectral."
            )


# ---------------------------------------------------------------------------
# CompositeData
# ---------------------------------------------------------------------------


class TestCompositeIntegration:
    """CompositeData audit + three-slot integration."""

    def test_composite_construction_with_three_slot_kwargs(self) -> None:
        child = DataObject(user={"child": True})
        comp = CompositeData(
            slots={"a": child},
            framework=FrameworkMeta(source="test"),
            user={"notes": "unit test"},
        )
        assert comp.get("a") is child
        assert comp.framework.source == "test"
        assert comp.user == {"notes": "unit test"}
        assert comp.meta is None

    def test_composite_with_meta_propagates_slots(self) -> None:
        """with_meta() preserves the populated slot children."""
        child_a = DataObject()
        child_b = DataObject()
        comp = _TypedComposite(
            slots={"a": child_a, "b": child_b},
            meta=_CompositeMeta(field=1, label="c"),
            user={"k": "v"},
        )
        new = comp.with_meta(field=7)

        assert isinstance(new.meta, _CompositeMeta)
        assert new.meta.field == 7
        assert new.meta.label == "c"

        # Slots were propagated (shared by reference, per composite.py docstring)
        assert new.get("a") is child_a
        assert new.get("b") is child_b
        assert sorted(new.slot_names) == ["a", "b"]

        assert new.user == {"k": "v"}
        assert new.framework.derived_from == comp.framework.object_id

    def test_composite_with_meta_preserves_slots_mapping_independently(self) -> None:
        """Mutating new composite's slot registry does not affect the original."""
        child = DataObject()
        comp = _TypedComposite(slots={"a": child}, meta=_CompositeMeta())
        new = comp.with_meta(field=1)

        # The slot mappings are distinct dict objects (though their
        # values share DataObject identity — see composite.py docstring).
        new.set("b", DataObject())
        assert "b" in new.slot_names
        assert "b" not in comp.slot_names

    def test_composite_with_meta_raises_when_meta_is_none(self) -> None:
        comp = CompositeData()
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            comp.with_meta(field=1)

    def test_composite_no_domain_subclasses_in_module(self) -> None:
        """ADR-027 D2: composite.py contains only CompositeData."""
        classes = _concrete_dataobject_classes(composite_module)
        assert classes == ["CompositeData"], f"Expected composite.py to contain only 'CompositeData'; found {classes}."
        for deleted in ("AnnData", "SpatialData"):
            assert not hasattr(composite_module, deleted), (
                f"composite.py must not define '{deleted}' — it belongs in a plugin package."
            )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


class TestTextIntegration:
    """Text audit + three-slot integration."""

    def test_text_construction_with_three_slot_kwargs(self) -> None:
        t = Text(
            content="hello",
            format="markdown",
            encoding="utf-8",
            framework=FrameworkMeta(source="test"),
            user={"notes": "unit test"},
        )
        assert t.content == "hello"
        assert t.format == "markdown"
        assert t.encoding == "utf-8"
        assert t.framework.source == "test"
        assert t.user == {"notes": "unit test"}
        assert t.meta is None

    def test_text_with_meta_propagates_extra_kwargs(self) -> None:
        t = _TypedText(
            content="body",
            format="markdown",
            encoding="utf-16",
            meta=_TextMeta(field=1, label="t"),
            user={"k": "v"},
        )
        new = t.with_meta(field=42)

        assert isinstance(new.meta, _TextMeta)
        assert new.meta.field == 42
        assert new.meta.label == "t"

        assert new.content == "body"
        assert new.format == "markdown"
        assert new.encoding == "utf-16"

        assert new.user == {"k": "v"}
        assert new.framework.derived_from == t.framework.object_id

    def test_text_with_meta_raises_when_meta_is_none(self) -> None:
        t = Text(content="x")
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            t.with_meta(field=1)

    def test_text_no_domain_subclasses_in_module(self) -> None:
        """ADR-027 D2: text.py contains only Text."""
        classes = _concrete_dataobject_classes(text_module)
        assert classes == ["Text"], f"Expected text.py to contain only 'Text'; found {classes}."


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


class TestArtifactIntegration:
    """Artifact audit + three-slot integration."""

    def test_artifact_construction_with_three_slot_kwargs(self) -> None:
        a = Artifact(
            mime_type="application/pdf",
            description="report",
            framework=FrameworkMeta(source="test"),
            user={"notes": "unit test"},
        )
        assert a.mime_type == "application/pdf"
        assert a.description == "report"
        assert a.framework.source == "test"
        assert a.user == {"notes": "unit test"}
        assert a.meta is None

    def test_artifact_with_meta_propagates_extra_kwargs(self) -> None:
        a = _TypedArtifact(
            mime_type="application/pdf",
            description="report",
            meta=_ArtifactMeta(field=1, label="a"),
            user={"k": "v"},
        )
        new = a.with_meta(field=99)

        assert isinstance(new.meta, _ArtifactMeta)
        assert new.meta.field == 99
        assert new.meta.label == "a"

        assert new.mime_type == "application/pdf"
        assert new.description == "report"

        assert new.user == {"k": "v"}
        assert new.framework.derived_from == a.framework.object_id

    def test_artifact_with_meta_raises_when_meta_is_none(self) -> None:
        a = Artifact(mime_type="application/pdf")
        with pytest.raises(ValueError, match="requires a typed `meta` slot"):
            a.with_meta(field=1)

    def test_artifact_no_domain_subclasses_in_module(self) -> None:
        """ADR-027 D2: artifact.py contains only Artifact."""
        classes = _concrete_dataobject_classes(artifact_module)
        assert classes == ["Artifact"], f"Expected artifact.py to contain only 'Artifact'; found {classes}."


# ---------------------------------------------------------------------------
# __all__ sanity check
# ---------------------------------------------------------------------------


class TestCoreTypesAllExports:
    """The ``scistudio.core.types`` public surface must contain only base types."""

    def test_all_contains_only_base_types(self) -> None:
        """__all__ must not re-export any deleted domain subtypes."""
        from scistudio.core.types import __all__ as core_types_all

        forbidden = {
            "Spectrum",
            "RamanSpectrum",
            "MassSpectrum",
            "PeakTable",
            "MetabPeakTable",
            "AnnData",
            "SpatialData",
            "Image",
            "FluorImage",
            "MSImage",
            "SRSImage",
        }
        overlap = forbidden & set(core_types_all)
        assert overlap == set(), (
            f"scistudio.core.types.__all__ must not re-export deleted domain subtypes; found: {sorted(overlap)}"
        )

    def test_all_contains_the_seven_base_types(self) -> None:
        """__all__ must contain exactly the seven core base types."""
        from scistudio.core.types import __all__ as core_types_all

        required = {
            "DataObject",
            "Array",
            "Series",
            "DataFrame",
            "Text",
            "Artifact",
            "CompositeData",
        }
        missing = required - set(core_types_all)
        assert missing == set(), (
            f"scistudio.core.types.__all__ must export all seven core base types; missing: {sorted(missing)}"
        )
