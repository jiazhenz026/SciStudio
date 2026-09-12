"""This project's own image type — a picture of a slide, built on the core Array.

Core tutorial 4 lands this file when it creates the project, because this
level's science needs an image type before its first step. It is ordinary
SciStudio type code: a module under ``types/`` declaring a subclass of a core
type, picked up by the registry the moment the file lands. This copy belongs
to this project only.

Why subclass ``Array`` rather than start from nothing: the core types are the
ones SciStudio knows how to store and reload — ``Array`` keeps its data in a
chunked Zarr store — so a subclass inherits all of that and adds only meaning.
An ``HEImage`` *is* an array; the class below says so, and everything that
accepts an Array accepts an HEImage because of it.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import Array


class HEImage(Array):
    """A picture of a slide: a ``y`` axis, an ``x`` axis, and what was measured.

    The class name is the registered type name, so this project now has a type
    called ``HEImage`` — look for it in the Data types tab, and in the Load
    block's core_type list.

    A color picture carries a third axis, ``c``, holding its red, green and
    blue channels; a single-channel one carries none. Both are HEImages: what
    every HEImage promises is the two spatial axes, because those are what makes
    a pixel a place on the slide rather than a number in a list.
    """

    # An Array subclass may demand named axes. Every HEImage must carry the two
    # spatial ones; constructing an HEImage without them raises, so a block
    # declaring HEImage on a port can rely on ``y`` and ``x`` being present.
    # Demanding them is not forbidding others — this is a floor, not a shape —
    # which is why the same class covers the color slide and the gray one.
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    # No color is declared here, and that is the point the tutorial makes: a
    # subclass that says nothing about color inherits its parent's fill and is
    # given an outline of its own, so an HEImage reads as "an Array, but a
    # particular one" on every canvas port that carries it — without its author
    # choosing anything. A type that does want its own colors declares
    # ``ui_color`` and ``ui_ring_color`` as CSS hex strings; a value that is not
    # one is ignored with a warning, so a typo costs the color and nothing else.
