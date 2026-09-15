"""This project's mask type — what a pathologist marked, built on the core Array.

An ``HEMask`` is the slide it was drawn over, drained to gray, with every spot
the pathologist labeled painted in its region's color: invasive cancer, DCIS,
stroma, lymphocytes or normal tissue. A key naming the colors sits beneath the
slide. See ``data/raw/SOURCE.md`` for how the masks were made.

It is a type of its own rather than another :class:`HEImage` because the two
are not interchangeable. An H&E slide is a measurement — light through stained
tissue — and a mask is a judgment, made by a person, about what that tissue
is. A block that wants to know which spots are cancer needs the second and
cannot use the first, and saying so on the port is how it refuses the mix-up
before the run starts rather than after.
"""

from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import Array


class HEMask(Array):
    """A region mask over a slide: a ``y`` axis, an ``x`` axis, and colors.

    The class name is the registered type name, so this project now has a type
    called ``HEMask`` — look for it in the Data types tab, and in the Load
    block's core_type list.
    """

    # The same floor an HEImage sets, for the same reason: a mask that has lost
    # its spatial axes cannot be laid back over the slide it came from.
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
