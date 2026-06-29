"""A custom file loader — an IOBlock example.

``LoadNpy`` reads a NumPy ``.npy`` file from disk into an ``Array`` so the rest
of a workflow can process it. Loaders and savers subclass the small
``SimpleLoader`` / ``SimpleSaver`` helpers: you declare a couple of class
attributes and write one method.

Copy this file into ``blocks/`` in your project and edit it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.io import SimpleLoader
from scistudio.core.types import Array, DataObject


class LoadNpy(SimpleLoader):
    """Load a NumPy ``.npy`` file as an ``Array``."""

    name: ClassVar[str] = "Load .npy"
    description: ClassVar[str] = "Read a NumPy .npy file into an Array."

    # What this loader produces, and which file extensions it claims.
    output_type: ClassVar[type[DataObject]] = Array
    extensions: ClassVar[tuple[str, ...]] = (".npy",)
    format_id: ClassVar[str] = "numpy_npy"

    def load_file(self, path: Path, config: dict[str, Any]) -> Array:
        arr = np.load(path)
        # Name the axes. For a plain N-D array we use generic names; if you know
        # the data is, say, a 2-D image, use ["y", "x"] instead.
        axes = [f"axis_{i}" for i in range(arr.ndim)]
        return Array(axes=axes, data=arr)
