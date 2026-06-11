"""SciStudio imaging plugin package metadata and public exports."""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_imaging.interactive.fiji_block import FijiBlock
from scistudio_blocks_imaging.interactive.napari_block import NapariBlock
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.math.image_calculator import ImageCalculator
from scistudio_blocks_imaging.math.scalar_ops import AddScalar, DivideScalar, MultiplyScalar, SubtractScalar
from scistudio_blocks_imaging.measurement.colocalization import Colocalization
from scistudio_blocks_imaging.measurement.pairwise_distance import PairwiseDistance
from scistudio_blocks_imaging.measurement.region_props import RegionProps
from scistudio_blocks_imaging.morphology.edge_detect import EdgeDetect
from scistudio_blocks_imaging.morphology.fft_filter import FFTFilter
from scistudio_blocks_imaging.morphology.morphology_op import MorphologyOp
from scistudio_blocks_imaging.morphology.ridge_filter import RidgeFilter
from scistudio_blocks_imaging.morphology.sharpen import Sharpen
from scistudio_blocks_imaging.preprocess.axis_ops import AxisMerge, AxisSplit
from scistudio_blocks_imaging.preprocess.background_subtract import BackgroundSubtract
from scistudio_blocks_imaging.preprocess.convert_dtype import ConvertDType
from scistudio_blocks_imaging.preprocess.denoise import Denoise
from scistudio_blocks_imaging.preprocess.flat_field_correct import FlatFieldCorrect
from scistudio_blocks_imaging.preprocess.geometry import Crop, Flip, Pad, Resize, Rotate
from scistudio_blocks_imaging.preprocess.normalize import Normalize
from scistudio_blocks_imaging.previewers import get_previewers
from scistudio_blocks_imaging.projection.projection import AxisProjection, SelectSlice
from scistudio_blocks_imaging.registration.apply_transform import ApplyTransform
from scistudio_blocks_imaging.registration.compute_registration import ComputeRegistration
from scistudio_blocks_imaging.registration.register_series import RegisterSeries
from scistudio_blocks_imaging.segmentation.blob_detect import BlobDetect
from scistudio_blocks_imaging.segmentation.cellpose_segment import CellposeSegment
from scistudio_blocks_imaging.segmentation.cleanup import (
    ExpandLabels,
    FillHoles,
    RemoveBorderObjects,
    RemoveSmallObjects,
    ShrinkLabels,
)
from scistudio_blocks_imaging.segmentation.connected_components import ConnectedComponents
from scistudio_blocks_imaging.segmentation.threshold import Threshold
from scistudio_blocks_imaging.segmentation.watershed import Watershed
from scistudio_blocks_imaging.types import Image, Label, Mask, Transform
from scistudio_blocks_imaging.visualization.render import (
    RenderHistogram,
    RenderMontage,
    RenderMovie,
    RenderOverlay,
    RenderPseudoColor,
)

__version__ = "0.1.0"

_IMAGING_TYPES: tuple[type, ...] = (Image, Mask, Label, Transform)
_IMAGING_BLOCKS: tuple[type, ...] = (
    LoadImage,
    SaveImage,
    Denoise,
    BackgroundSubtract,
    Normalize,
    FlatFieldCorrect,
    Rotate,
    Flip,
    Crop,
    Pad,
    Resize,
    ConvertDType,
    AxisSplit,
    AxisMerge,
    MorphologyOp,
    EdgeDetect,
    RidgeFilter,
    Sharpen,
    FFTFilter,
    ComputeRegistration,
    ApplyTransform,
    RegisterSeries,
    AxisProjection,
    SelectSlice,
    AddScalar,
    SubtractScalar,
    MultiplyScalar,
    DivideScalar,
    ImageCalculator,
    RenderPseudoColor,
    RenderOverlay,
    RenderMontage,
    RenderMovie,
    RenderHistogram,
    FijiBlock,
    NapariBlock,
    RegionProps,
    PairwiseDistance,
    Colocalization,
    Threshold,
    Watershed,
    CellposeSegment,
    BlobDetect,
    ConnectedComponents,
    RemoveSmallObjects,
    RemoveBorderObjects,
    FillHoles,
    ExpandLabels,
    ShrinkLabels,
)


def get_package_info() -> PackageInfo:
    """Return package metadata for the ``scistudio.blocks`` registry."""
    return PackageInfo(
        name="scistudio-blocks-imaging",
        description="Microscopy imaging blocks for SciStudio Phase 11 workflows.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_types() -> list[type]:
    """Return the imaging plugin's exported type classes."""
    return list(_IMAGING_TYPES)


def get_blocks() -> list[type]:
    """Return the imaging plugin's exported concrete block classes."""
    return list(_IMAGING_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and block classes for ``scistudio.blocks``."""
    return get_package_info(), get_blocks()


__all__ = [
    "AddScalar",
    "ApplyTransform",
    "AxisMerge",
    "AxisProjection",
    "AxisSplit",
    "BackgroundSubtract",
    "BlobDetect",
    "CellposeSegment",
    "Colocalization",
    "ComputeRegistration",
    "ConnectedComponents",
    "ConvertDType",
    "Crop",
    "Denoise",
    "DivideScalar",
    "EdgeDetect",
    "ExpandLabels",
    "FFTFilter",
    "FijiBlock",
    "FillHoles",
    "FlatFieldCorrect",
    "Flip",
    "Image",
    "ImageCalculator",
    "Label",
    "LoadImage",
    "Mask",
    "MorphologyOp",
    "MultiplyScalar",
    "NapariBlock",
    "Normalize",
    "Pad",
    "PairwiseDistance",
    "RegionProps",
    "RegisterSeries",
    "RemoveBorderObjects",
    "RemoveSmallObjects",
    "RenderHistogram",
    "RenderMontage",
    "RenderMovie",
    "RenderOverlay",
    "RenderPseudoColor",
    "Resize",
    "RidgeFilter",
    "Rotate",
    "SaveImage",
    "SelectSlice",
    "Sharpen",
    "ShrinkLabels",
    "SubtractScalar",
    "Threshold",
    "Transform",
    "Watershed",
    "__version__",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_previewers",
    "get_types",
]
