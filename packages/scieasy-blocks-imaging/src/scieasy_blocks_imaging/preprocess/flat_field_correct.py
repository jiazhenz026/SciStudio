"""FlatFieldCorrect — multi-input flat-field / shading correction (T-IMG-007).

Sprint C imaging preprocess subset A. See
``docs/specs/phase11-imaging-block-spec.md`` §9 T-IMG-007.

Tier 2 block (overrides ``run()``) because it consumes three input
ports: ``image``, ``flat_field``, and optional ``dark_frame``.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.core.types.collection import Collection
from scieasy.utils.axis_iter import iterate_over_axes
from scieasy_blocks_imaging.types import Image

_ALLOWED_METHODS = frozenset({"basic", "BaSiC"})


class FlatFieldCorrect(ProcessBlock):
    """Multi-input flat-field correction.

    Formula: ``out = (image - dark) / (flat - dark) * mean(flat - dark)``,
    where ``dark`` defaults to zeros if not provided. Methods:

    - ``basic``: literal formula above.
    - ``BaSiC``: BaSiC algorithm via the optional ``basicpy`` package.
    """

    type_name: ClassVar[str] = "imaging.flatfield_correct"
    name: ClassVar[str] = "Flat Field Correct"
    description: ClassVar[str] = "Correct uneven illumination using a flat-field reference."
    subcategory: ClassVar[str] = "preprocess"
    algorithm: ClassVar[str] = "flatfield_correct"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
        InputPort(name="flat_field", accepted_types=[Image], required=True),
        InputPort(name="dark_frame", accepted_types=[Image], required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="image", accepted_types=[Image]),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": sorted(_ALLOWED_METHODS),
                "default": "basic",
            },
        },
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Apply flat-field correction (Tier 2 — multi-input).

        Iterates the primary ``image`` Collection and pairs it with the
        first item of ``flat_field`` (and optional ``dark_frame``). All
        items in the image Collection are corrected against the same
        reference flat (and dark), which matches the conventional
        microscopy workflow where a single reference pair is acquired
        per session.

        Raises:
            ValueError: On unknown method, missing flat_field, or
                ``(y, x)`` shape mismatch between image and references.
            ImportError: If ``method=BaSiC`` is requested but ``basicpy``
                is not installed.
        """
        method = config.get("method", "basic")
        if method not in _ALLOWED_METHODS:
            raise ValueError(f"FlatFieldCorrect: unknown method {method!r}; expected one of {sorted(_ALLOWED_METHODS)}")

        if "image" not in inputs or "flat_field" not in inputs:
            raise ValueError("FlatFieldCorrect: requires both 'image' and 'flat_field' inputs")

        image_input = inputs["image"]
        flat_input = inputs["flat_field"]
        dark_input = inputs.get("dark_frame")

        flat_ref = _first_image(flat_input, "flat_field")
        dark_ref: Image | None = _first_image(dark_input, "dark_frame") if dark_input is not None else None

        if method == "BaSiC":
            try:
                import basicpy  # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "FlatFieldCorrect: method='BaSiC' requires the 'basicpy' "
                    "package. Install it with: pip install basicpy"
                ) from exc
            # TODO: T-IMG-007 — implement the BaSiC flat-field correction method (currently only the literal 'basic' formula is wired).
            raise NotImplementedError(
                "FlatFieldCorrect: method='BaSiC' is deferred from the T-IMG-007 "
                "pilot; use method='basic' for the literal formula."
            )

        # method == "basic"
        flat_arr = np.asarray(flat_ref.to_memory()).astype(np.float64)
        dark_arr: np.ndarray | None = (
            np.asarray(dark_ref.to_memory()).astype(np.float64) if dark_ref is not None else None
        )

        corrected_items: list[Image] = []
        if isinstance(image_input, Collection):
            for item in image_input:
                if not isinstance(item, Image):
                    raise ValueError(f"FlatFieldCorrect: expected Image items, got {type(item).__name__}")
                corrected_items.append(self._apply_basic(item, flat_arr, dark_arr))
            out_collection = Collection(items=cast(Any, corrected_items), item_type=Image)
        else:
            # Non-Collection fallback: single Image passed directly.
            if not isinstance(image_input, Image):
                raise ValueError(f"FlatFieldCorrect: expected Image input, got {type(image_input).__name__}")
            corrected = self._apply_basic(image_input, flat_arr, dark_arr)
            out_collection = Collection(items=cast(Any, [corrected]), item_type=Image)

        output_name = self.output_ports[0].name
        return {output_name: out_collection}

    def _apply_basic(
        self,
        image: Image,
        flat_arr: np.ndarray,
        dark_arr: np.ndarray | None,
    ) -> Image:
        """Apply the basic flat-field formula to a single image.

        Validates that ``image``, ``flat_arr``, and ``dark_arr`` (when
        provided) agree on the ``(y, x)`` shape, then iterates over the
        extra axes of ``image`` via :func:`iterate_over_axes`.
        """
        if "y" not in image.axes or "x" not in image.axes:
            raise ValueError(f"FlatFieldCorrect: image must have (y, x) axes; got {image.axes}")

        if image.shape is None:
            raise ValueError("FlatFieldCorrect: image.shape is required (metadata-only image not supported)")
        y_size = image.shape[image.axes.index("y")]
        x_size = image.shape[image.axes.index("x")]

        flat_2d = _to_2d_yx(flat_arr, "flat_field")
        if flat_2d.shape != (y_size, x_size):
            raise ValueError(
                f"FlatFieldCorrect: flat_field (y, x) shape {flat_2d.shape} "
                f"does not match image (y, x) shape {(y_size, x_size)}"
            )

        dark_2d: np.ndarray
        if dark_arr is None:
            dark_2d = np.zeros_like(flat_2d)
        else:
            dark_2d = _to_2d_yx(dark_arr, "dark_frame")
            if dark_2d.shape != (y_size, x_size):
                raise ValueError(
                    f"FlatFieldCorrect: dark_frame (y, x) shape {dark_2d.shape} "
                    f"does not match image (y, x) shape {(y_size, x_size)}"
                )

        denom = flat_2d - dark_2d
        # Guard against zero-division: where denom==0, leave numerator as-is
        # by substituting 1.0 for the denominator (result: image - dark).
        safe_denom = np.where(denom == 0, 1.0, denom)
        scale = float(np.mean(denom))

        def _correct(slice_2d: np.ndarray, _coord: dict[str, int]) -> np.ndarray:
            out = (slice_2d.astype(np.float64) - dark_2d) / safe_denom * scale
            return np.asarray(out)

        return cast(Image, iterate_over_axes(image, frozenset({"y", "x"}), _correct))


def _first_image(col_or_item: Any, port_name: str) -> Image:
    """Extract the first :class:`Image` from a Collection or pass-through."""
    if isinstance(col_or_item, Collection):
        try:
            first = col_or_item[0]
        except (IndexError, StopIteration) as exc:
            raise ValueError(f"FlatFieldCorrect: input {port_name!r} collection is empty") from exc
        if not isinstance(first, Image):
            raise ValueError(f"FlatFieldCorrect: {port_name!r} must contain Image items; got {type(first).__name__}")
        return first
    if isinstance(col_or_item, Image):
        return col_or_item
    raise ValueError(
        f"FlatFieldCorrect: {port_name!r} must be an Image or Collection[Image]; got {type(col_or_item).__name__}"
    )


def _to_2d_yx(arr: np.ndarray, name: str) -> np.ndarray:
    """Squeeze a reference array down to 2D ``(y, x)``.

    Accepts a 2D array directly, or an N-D array whose non-last-two
    dimensions are all size-1 (conventional single-frame reference).
    """
    if arr.ndim == 2:
        return arr
    squeezed = np.squeeze(arr)
    if squeezed.ndim != 2:
        raise ValueError(f"FlatFieldCorrect: {name!r} must be 2D after squeezing; got shape {arr.shape}")
    return squeezed
