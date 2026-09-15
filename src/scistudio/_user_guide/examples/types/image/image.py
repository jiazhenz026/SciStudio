# mypy: ignore-errors
#
# Mirrors pyproject's `[tool.mypy] exclude = ['/_user_guide/']`, which
# package-wide runs honor but explicit-file runs do not (the gate's narrowed
# check and the pre-commit hook pass files by name, #2115): this file ships as
# project *data* a reader copies into their project and edits, not a module the
# package imports.
#
"""A custom data type — an `Array` subclass example.

This project's own image type: a 2-D micrograph, built on the core ``Array``.
A type is a Python class under your project's ``types/``; the registry picks it
up the moment the file lands. The class name is the registered type name, so
this project now has a type called ``Image`` — look for it in the Data types
tab, and in the Load block's core_type list.

Why subclass ``Array`` rather than start from nothing: the core types are the
ones SciStudio knows how to store and reload — ``Array`` keeps its data in a
chunked Zarr store — so a subclass inherits all of that and adds only meaning.
An ``Image`` *is* an array; the class below says so, and everything that
accepts an Array (the core Array preview panel included) accepts an Image
because of it.

Copy this file into ``types/`` in your project and edit it.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import Array


class Image(Array):
    """A 2-D microscope image: a ``y`` axis, an ``x`` axis, one value per pixel."""

    # An Array subclass may demand named axes. Every Image must carry the two
    # spatial ones; constructing an Image without them raises, so a block
    # declaring Image on a port can rely on ``y`` and ``x`` being present.
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    # No color is declared here, and that is the point: a subclass that says
    # nothing about color inherits its parent's fill and is given an outline
    # of its own, so an Image reads as "an Array, but a particular one" on
    # every canvas port that carries it — without its author choosing
    # anything. A type that does want its own colors declares ``ui_color``
    # and ``ui_ring_color`` as CSS hex strings; a value that is not one is
    # ignored with a warning, so a typo costs the color and nothing else.
