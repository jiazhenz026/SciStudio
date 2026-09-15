"""A custom data type — a `CompositeData` subclass example.

An AnnData-style single-cell dataset: a named bundle of three tables. Where
the [Image example](../image/) subclasses ``Array`` because its data *is* one
array, this type subclasses ``CompositeData`` because its data is *several*
data objects that belong together — the expression matrix, the per-cell
annotations, and the per-gene annotations are only meaningful as a set, and
ports should be able to demand the whole set at once.

A type is a Python class under your project's ``types/``; the registry picks
it up the moment the file lands. The class name is the registered type name,
so this project now has a type called ``AnnData``.

Copy this file into ``types/`` in your project and edit it. A type is complete
only when data of that type can be read — pair it with a ``SimpleLoader`` (see
the [IO block example](../../blocks/io-load-tiff/)) so the Load block can
bring it into a workflow.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import CompositeData, DataFrame


class AnnData(CompositeData):
    """A single-cell experiment: expression matrix ``X`` plus per-cell ``obs`` and per-gene ``var`` annotations.

    ``expected_slots`` fixes the bundle's layout. Every AnnData must carry
    exactly these three named slots, each a ``DataFrame``; ``set()`` rejects
    a value of the wrong type for its slot, so a block declaring AnnData on a
    port can rely on all three being present and being tables.
    """

    expected_slots: ClassVar[dict[str, type]] = {
        "X": DataFrame,  # expression counts: one row per gene, one column per cell
        "obs": DataFrame,  # per-cell metadata (batch, condition, …): one row per cell
        "var": DataFrame,  # per-gene metadata (gene symbol, genome): one row per gene
    }
