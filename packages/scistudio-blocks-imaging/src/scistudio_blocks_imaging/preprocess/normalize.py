"""Normalize — minmax / zscore / percentile (T-IMG-006 impl, narrow scope).

Sprint C imaging preprocess subset A. See
``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-006.

Pilot scope: ``minmax``, ``zscore``, and ``percentile`` are implemented
with numpy. ``histogram_match`` requires a reference image and is kept
in the enum schema for forward compatibility but raises
``NotImplementedError`` — it needs a second input port (tracked in the
spec as out-of-scope for subset A).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, cast

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio_blocks_imaging.types import Image

_PILOT_METHODS = frozenset({"minmax", "zscore", "percentile"})
_DEFERRED_METHODS = frozenset({"histogram_match"})
_ALL_METHODS = _PILOT_METHODS | _DEFERRED_METHODS

_SliceFn = Callable[[np.ndarray, dict[str, int]], np.ndarray]


class Normalize(ProcessBlock):
    """Intensity normalization with several methods."""

    type_name: ClassVar[str] = "imaging.normalize"
    name: ClassVar[str] = "Normalize"
    description: ClassVar[str] = "Rescale image intensities (minmax / zscore / percentile / histogram_match)."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "normalize"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": sorted(_ALL_METHODS),
                "default": "minmax",
            },
            "low_pct": {"type": "number", "default": 1.0},
            "high_pct": {"type": "number", "default": 99.0},
            "per_slice": {"type": "boolean", "default": True},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Normalize image intensities.

        Args:
            item: Input :class:`Image`.
            config: BlockConfig with ``method`` and optional params.
            state: Unused (ADR-027 D7).

        Returns:
            A new :class:`Image` with normalized intensities, same
            axes/shape.

        Raises:
            ValueError: If ``method`` is unknown or percentile bounds
                are invalid.
            NotImplementedError: If ``method`` is ``histogram_match``
                (deferred — requires a reference-image input port).
        """
        method = config.get("method", "minmax")
        low_pct = float(config.get("low_pct", 1.0))
        high_pct = float(config.get("high_pct", 99.0))
        per_slice = bool(config.get("per_slice", True))
        if method not in _ALL_METHODS:
            raise ValueError(f"Normalize: unknown method {method!r}; expected one of {sorted(_ALL_METHODS)}")
        if method in _DEFERRED_METHODS:
            # TODO: T-IMG-006 — implement histogram_match normalization (needs adding a reference-image input port to the block).
            raise NotImplementedError(
                f"Normalize: method {method!r} is deferred from the T-IMG-006 "
                "pilot (requires reference-image input port)."
            )
        if not (0.0 <= low_pct < high_pct <= 100.0):
            raise ValueError(
                f"Normalize: need 0 <= low_pct < high_pct <= 100, got low_pct={low_pct}, high_pct={high_pct}"
            )

        if per_slice:
            fn = _build_normalize_fn(method, low_pct=low_pct, high_pct=high_pct)
            return cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), fn))

        # Whole-image normalization: operate on the full N-D array at once.
        data = np.asarray(item.to_memory())
        normalized = _normalize_full(data, method, low_pct=low_pct, high_pct=high_pct)

        def _identity(_slice: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return _slice  # pragma: no cover

        # Reuse the iterate_over_axes result-building pathway by calling
        # it with a no-op on every axis (empty operates_on would reject);
        # instead, construct the result the same way iterate_over_axes
        # does internally via a one-shot over all axes.
        fn_all = _make_whole_fn(normalized, item.axes)
        return cast(Image, iterate_over_axes(item, frozenset(item.axes), fn_all))


def _make_whole_fn(full: np.ndarray, axes: list[str]) -> _SliceFn:
    """Return a slice fn that returns ``full`` once (fast-path for no extra axes).

    When ``operates_on == set(source.axes)``, :func:`iterate_over_axes`
    invokes the function once with the entire array and an empty coord
    dict. We ignore the input and return the pre-computed normalized
    array so the result pathway rebuilds a new :class:`Image` with
    propagated metadata.
    """

    def _fn(_slice: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
        return full

    _ = axes  # only used by callers for documentation
    return _fn


def _build_normalize_fn(method: str, *, low_pct: float, high_pct: float) -> _SliceFn:
    """Return a per-slice numpy callable for ``method``."""
    if method == "minmax":

        def _mm(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return _minmax(slice_2d)

        return _mm
    if method == "zscore":

        def _zs(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return _zscore(slice_2d)

        return _zs
    if method == "percentile":

        def _pc(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return _percentile(slice_2d, low_pct, high_pct)

        return _pc
    raise ValueError(f"Normalize: unknown method {method!r}")  # pragma: no cover


def _normalize_full(data: np.ndarray, method: str, *, low_pct: float, high_pct: float) -> np.ndarray:
    if method == "minmax":
        return _minmax(data)
    if method == "zscore":
        return _zscore(data)
    if method == "percentile":
        return _percentile(data, low_pct, high_pct)
    raise ValueError(f"Normalize: unknown method {method!r}")  # pragma: no cover


def _minmax(arr: np.ndarray) -> np.ndarray:
    a = arr.astype(np.float64)
    lo = float(a.min())
    hi = float(a.max())
    if hi == lo:
        return np.zeros_like(a)
    return (a - lo) / (hi - lo)


def _zscore(arr: np.ndarray) -> np.ndarray:
    a = arr.astype(np.float64)
    mu = float(a.mean())
    sigma = float(a.std())
    if sigma == 0.0:
        return np.zeros_like(a)
    return (a - mu) / sigma


def _percentile(arr: np.ndarray, low_pct: float, high_pct: float) -> np.ndarray:
    a = arr.astype(np.float64)
    lo = float(np.percentile(a, low_pct))
    hi = float(np.percentile(a, high_pct))
    if hi == lo:
        return np.zeros_like(a)
    clipped = np.clip(a, lo, hi)
    return (clipped - lo) / (hi - lo)
