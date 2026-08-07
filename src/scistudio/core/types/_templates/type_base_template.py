"""Starter template for a custom SciStudio data type.

The "New data type" action copies this file into a ``types/`` folder and opens
it for editing. Three steps to make it yours:

    1. Rename ``MyDataType`` and rewrite its docstring.
    2. Pick the base class that matches the shape of your data.
    3. Declare the metadata your type carries, if it carries any.

====================================================================
1. WHAT IS A DATA TYPE -- and why declare one
====================================================================

A data type is the *kind of thing* your blocks pass to each other. SciStudio
ships six general-purpose ones and you make your own by subclassing whichever
of them holds your data, then adding the meaning specific to your science.

Declaring your own buys three things:

    1. Ports can require it. A block declaring
       ``InputPort(accepted_types=[MySpectrum])`` refuses a plain Series, so a
       mis-wired canvas is caught before anything runs.
    2. It gets its own name, colour, and tile in the Data types tab.
    3. It can carry typed, validated metadata that travels with the data
       between processes.

====================================================================
2. WHICH BASE CLASS TO INHERIT
====================================================================

    Array          N-dimensional numeric data (images, volumes, stacks).
    Series         1D indexed data (time series, chromatograms, spectra).
    DataFrame      Columnar tables.
    Text           Plain text, Markdown, or JSON.
    Artifact       Opaque files (PDFs, reports, binary blobs).
    CompositeData  A named bundle of the above.

Subclass one of these rather than ``DataObject`` itself: they are what knows
how to store and reload your data.

====================================================================
3. WHERE TO PUT THIS FILE
====================================================================

    ~/.scistudio/types/     Your library. Available in every project.
    <project>/types/        This project only.

One file may declare as many types as you like. The class name is the
registered type name, so keep it unique and CamelCase.

Give the *file* a name no installed Python package uses -- ``spectra.py`` is
fine, ``json.py`` or ``numpy.py`` is not, and will be refused with an
explanation, because the types folder joins the Python import path.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

# Import the base you want to extend, from the table in section 2 above. The
# trailing notes just silence the linter for the types you have not used yet --
# delete a note once you start using its type.
from scistudio.core.types import (
    Array,
    Artifact,  # noqa: F401
    CompositeData,  # noqa: F401
    DataFrame,  # noqa: F401
    Series,  # noqa: F401
    Text,  # noqa: F401
)


class MyDataTypeMeta(BaseModel):
    """Typed metadata carried by every ``MyDataType`` instance.

    Optional -- delete this class and the ``Meta`` line below if your type
    needs no metadata of its own.

    Every field must survive a round trip through JSON, because instances
    travel between processes: strings, numbers, booleans, lists, dicts, and
    nested models are all fine. Give each field a default so an instance can be
    created without it.
    """

    model_config = ConfigDict(frozen=True)

    instrument: str = ""
    """Name of the instrument the data came from."""

    wavelength_nm: float | None = None
    """Excitation wavelength in nanometres, if there is one."""


class MyDataType(Array):
    """Replace this docstring with one line describing what this type holds.

    That first line is what the Data types tab shows under the type's name, so
    write it for whoever opens the palette -- including you, in six months.
    """

    # >>> EDIT THIS <<<
    # Point ``Meta`` at your model above so instances get validated metadata:
    #
    #     obj = MyDataType(axes=["wavelength"], meta=MyDataTypeMeta(instrument="Alpha"))
    #     obj.meta.instrument
    #
    # Set it back to ``None`` if this type carries no metadata of its own.
    Meta: ClassVar[type[BaseModel] | None] = MyDataTypeMeta

    # Optional appearance. Leave both unset (recommended) and SciStudio picks a
    # stable colour for you. To choose your own, uncomment and set a CSS hex
    # value -- it colours this type's palette tile and every canvas port that
    # carries it, so types that belong together can be made to look together:
    #
    #   ui_color: ClassVar[str | None] = "#4f8ef7"       # the fill
    #   ui_ring_color: ClassVar[str | None] = "#1b4f9c"  # the outline, derived
    #       from the fill when you leave it unset
    #
    # A value that is not a CSS hex colour is ignored with a warning, so a typo
    # here costs you your chosen colour and nothing else.

    # Array subclasses may require named axes. A value missing one of them is
    # rejected at construction, so a block declaring this type on a port can
    # rely on the axes being present. Delete this line if you are not
    # subclassing ``Array``, or if any axes will do.
    required_axes: ClassVar[frozenset[str]] = frozenset({"wavelength"})
