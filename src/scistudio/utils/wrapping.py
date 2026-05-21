"""wrap_as_dataobject() -- auto-detect DataObject type from raw data."""

from __future__ import annotations

from typing import Any


def wrap_as_dataobject(data: Any) -> Any:
    """Auto-detect the appropriate DataObject subtype for *data* and wrap it.

    Handles numpy arrays -> Array, pandas DataFrames -> DataFrame,
    strings -> Text, etc.
    """
    # TODO: implement type auto-detection and wrap raw values into the matching DataObject subclass.
    raise NotImplementedError
