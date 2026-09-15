"""A MiniApp that holds one Array in memory and answers questions about it."""

import numpy as np

_state: dict[str, object] = {}


def setup(data):
    """Called once when the MiniApp opens, with the target reconstructed."""
    array = np.asarray(getattr(data, "to_memory", lambda: data)())
    _state["array"] = array


def summary():
    """Shape, dtype and range of the array."""
    a = _state["array"]
    return {
        "shape": list(a.shape),
        "dtype": str(a.dtype),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
    }


def fraction_above(threshold: float):
    """The fraction of elements above `threshold`, recomputed per slider move."""
    a = _state["array"]
    finite = np.isfinite(a)
    total = int(finite.sum())
    above = int((finite & (a > threshold)).sum())
    return {"above": above, "total": total, "fraction": (above / total) if total else 0.0}
