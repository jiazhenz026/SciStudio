"""Denoise — gaussian / median (T-IMG-004 impl, narrow scope).

Sprint C imaging preprocess subset A. See
``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-004.

Pilot scope: ``gaussian`` and ``median`` are implemented via
scikit-image. ``bilateral``/``nlmeans``/``wavelet`` remain in the enum
schema for forward compatibility but raise ``NotImplementedError`` —
they are tracked as out-of-scope on issue #356 and will be filled in by
a follow-on subset.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy.utils.constraints import has_axes
from scieasy_blocks_imaging.types import Image

_PILOT_METHODS = frozenset({"gaussian", "median"})
_DEFERRED_METHODS = frozenset({"bilateral", "nlmeans", "wavelet"})
_ALL_METHODS = _PILOT_METHODS | _DEFERRED_METHODS


class Denoise(ProcessBlock):
    """Denoise images using one of several 2D algorithms.

    Operates on 2D ``(y, x)`` slices. For N-D inputs, the implementation
    uses :func:`scieasy.utils.axis_iter.iterate_over_axes` to broadcast
    across the extra ``(t, z, c, lambda)`` axes.
    """

    type_name: ClassVar[str] = "imaging.denoise"
    name: ClassVar[str] = "Denoise"
    description: ClassVar[str] = "Remove noise via gaussian/median (pilot)."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "denoise"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="image",
            accepted_types=[Image],
            required=True,
            constraint=has_axes("y", "x"),
            constraint_description="image must carry (y, x)",
        ),
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
                "default": "gaussian",
            },
            "sigma": {"type": "number", "default": 1.0, "minimum": 0.0},
            "radius": {"type": "integer", "default": 3, "minimum": 1},
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Image:
        """Denoise a single image, broadcasting over extra axes.

        Args:
            item: Input :class:`Image` carrying ``(y, x)`` (and possibly
                extra axes from ``(t, z, c, lambda)``).
            config: BlockConfig with ``method`` and method-specific params.
            state: Unused (kept for ADR-027 D7 signature).

        Returns:
            A new :class:`Image` of identical axes / shape with denoised
            pixel values.

        Raises:
            ValueError: If ``method`` is unknown, ``sigma < 0``, or
                ``radius < 1``.
            NotImplementedError: If ``method`` is one of the deferred
                pilot methods (bilateral/nlmeans/wavelet).
        """
        method = config.get("method", "gaussian")
        sigma = float(config.get("sigma", 1.0))
        radius = int(config.get("radius", 3))
        if sigma < 0:
            raise ValueError(f"Denoise: sigma must be >= 0, got {sigma}")
        if radius < 1:
            raise ValueError(f"Denoise: radius must be >= 1, got {radius}")
        if method not in _ALL_METHODS:
            raise ValueError(f"Denoise: unknown method {method!r}; expected one of {sorted(_ALL_METHODS)}")
        if method in _DEFERRED_METHODS:
            # TODO: #356 — implement bilateral/nlmeans/wavelet denoising methods (deferred from T-IMG-004 pilot).
            raise NotImplementedError(
                f"Denoise: method {method!r} is deferred from the T-IMG-004 pilot (see issue #356)."
            )
        fn = _build_denoise_fn(method, sigma=sigma, radius=radius)
        return cast(Image, iterate_over_axes(item, frozenset({"y", "x"}), fn))


def _build_denoise_fn(method: str, *, sigma: float, radius: int) -> Any:
    """Return a per-slice numpy callable for ``method``."""
    from skimage.filters import gaussian, median
    from skimage.morphology import disk

    if method == "gaussian":

        def _gauss(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return np.asarray(gaussian(slice_2d, sigma=sigma, preserve_range=True))

        return _gauss
    if method == "median":
        footprint = disk(radius)

        def _med(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            return np.asarray(median(slice_2d, footprint=footprint))

        return _med
    raise ValueError(f"Denoise: unknown method {method!r}")  # pragma: no cover
