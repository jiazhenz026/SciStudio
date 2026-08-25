"""This project's own image type — a 2-D micrograph, built on the core Array.

Core tutorial 2 writes this file over the template that the New data type
dialog created for you. It is ordinary SciStudio type code: a module under
``types/`` declaring a subclass of a core type, picked up by the registry the
moment the file lands. This copy belongs to this project only; "Move to My
Library" at the end of the tutorial is what makes it available everywhere.

Why subclass ``Array`` rather than start from nothing: the core types are the
ones SciStudio knows how to store and reload — ``Array`` keeps its data in a
chunked Zarr store — so a subclass inherits all of that and adds only meaning.
An ``Image`` *is* an array; the class below says so, and everything that
accepts an Array (the core previewer you are about to meet included) accepts
an Image because of it.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import Array


class Image(Array):
    """A 2-D microscope image: a ``y`` axis, an ``x`` axis, one value per pixel.

    The class name is the registered type name, so this project now has a type
    called ``Image`` — look for it in the Data types tab, and in the Load
    block's core_type list.
    """

    # An Array subclass may demand named axes. Every Image must carry the two
    # spatial ones; constructing an Image without them raises, so a block
    # declaring Image on a port can rely on ``y`` and ``x`` being present.
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    # No color is declared here, and that is the point the tutorial makes: a
    # subclass that says nothing about color inherits its parent's fill and is
    # given an outline of its own, so an Image reads as "an Array, but a
    # particular one" on every canvas port that carries it — without its author
    # choosing anything. A type that does want its own colors declares
    # ``ui_color`` and ``ui_ring_color`` as CSS hex strings; a value that is not
    # one is ignored with a warning, so a typo costs the color and nothing else.
