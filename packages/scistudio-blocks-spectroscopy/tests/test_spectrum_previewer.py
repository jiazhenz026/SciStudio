"""Spectrum previewer contract tests (SC-004, SC-006).

Drives the package spectrum provider against a real
``PreviewDataAccess`` reading an on-disk parquet payload, asserting:

- exact ``Spectrum`` refs route to the spectrum previewer (SC-004);
- the envelope is a SERIES envelope carrying true (x, y) points;
- export/save controls exist for the figure and the visible data (SC-006);
- honest metadata flags are present and boolean;
- a bad input yields an error envelope rather than crashing.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
from scistudio_blocks_spectroscopy.previewers import (
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)
from scistudio_blocks_spectroscopy.previewers.providers import spectrum_provider, spectrum_resource_provider

from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewerSpec,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)

_SPECTRUM_CHAIN = ("DataObject", "Series", "Spectrum")


def _spec() -> PreviewerSpec:
    for spec in get_previewers():
        if spec.previewer_id == SPECTRUM_PREVIEWER_ID:
            return cast(PreviewerSpec, spec)
    raise AssertionError(SPECTRUM_PREVIEWER_ID)


def _request(
    path: Path,
    record_md: dict | None = None,
    storage: dict | None = None,
    extra_query: dict | None = None,
    data_access: PreviewDataAccess | None = None,
) -> PreviewRequest:
    request_query: dict = {"_storage": storage or {"backend": "filesystem", "path": str(path), "format": "parquet"}}
    if record_md is not None:
        request_query["_record_metadata"] = record_md
    if extra_query is not None:
        request_query.update(extra_query)
    return PreviewRequest(
        target=PreviewTarget(
            kind=TargetKind.DATA_REF, ref=str(path), recorded_type="Spectrum", type_chain=_SPECTRUM_CHAIN
        ),
        spec=_spec(),
        query=request_query,
        data_access=data_access or PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )


def _parquet(path: Path, columns: dict) -> Path:
    pq.write_table(pa.table(columns), path)
    return path


def test_spectrum_previewer_is_package_owned() -> None:
    """SC-004: the spectrum previewer is a PACKAGE-owned spec for ``Spectrum``."""
    spec = _spec()
    assert spec.owner_kind is OwnerKind.PACKAGE
    assert spec.owner_name == "scistudio-blocks-spectroscopy"
    assert spec.target_type == "Spectrum"
    assert spec.supports_collection is False


def test_spectrum_provider_builds_series_envelope_with_points(tmp_path: Path) -> None:
    path = _parquet(
        tmp_path / "spectrum.parquet",
        {"lambda": [400.0, 401.0, 402.0], "intensity": [0.1, 0.5, 0.3]},
    )
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "a.u."}))
    assert env.previewer_id == SPECTRUM_PREVIEWER_ID
    assert env.kind is EnvelopeKind.SERIES
    assert env.error is None
    assert env.payload["points"] == [
        {"x": 400.0, "y": 0.1},
        {"x": 401.0, "y": 0.5},
        {"x": 402.0, "y": 0.3},
    ]
    assert env.payload["total"] == 3
    assert env.payload["axes"]["x"]["unit"] == "nm"


def test_spectrum_provider_reads_complete_spectrum_not_preview_sample(tmp_path: Path) -> None:
    xs = list(range(700, 1700))
    ys = [float(i) / 10.0 for i in range(len(xs))]
    path = _parquet(tmp_path / "spectrum.parquet", {"lambda": xs, "intensity": ys})
    request = _request(
        path,
        record_md={"lambda_unit": "nm", "intensity_unit": "a.u."},
        data_access=PreviewDataAccess(series_points=10),
    )

    env = spectrum_provider(request)

    assert env.kind is EnvelopeKind.SERIES
    assert env.payload["total"] == 1000
    assert len(env.payload["points"]) == 1000
    assert env.payload["points"][0] == {"x": 700.0, "y": 0.0}
    assert env.payload["points"][-1] == {"x": 1699.0, "y": 99.9}
    assert env.metadata.sampled is False
    assert env.metadata.truncated is False
    assert env.metadata.complete is True


def test_spectrum_provider_rejects_zarr_backed_series(tmp_path: Path) -> None:
    path = tmp_path / "spectrum.zarr"
    path.mkdir()
    env = spectrum_provider(
        _request(
            path,
            record_md={"meta": {"lambda_unit": "nm", "intensity_unit": "a.u."}},
            storage={"backend": "zarr", "path": str(path), "format": "zarr"},
        )
    )
    assert env.kind is EnvelopeKind.ERROR
    assert env.error is not None
    assert "Arrow/Parquet" in env.error.message
    assert env.metadata.failed is True


def test_spectrum_provider_uses_source_header_for_axis_label(tmp_path: Path) -> None:
    source = tmp_path / "raw_spectrum.txt"
    source.write_text("# source header\nwavelength-nm intensity\n400 0.1\n401 0.5\n", encoding="utf-8")
    path = _parquet(tmp_path / "spectrum.parquet", {"lambda": [400.0, 401.0], "intensity": [0.1, 0.5]})
    env = spectrum_provider(_request(path, record_md={"meta": {"source_file": str(source)}}))
    assert env.kind is EnvelopeKind.SERIES
    assert env.payload["axes"]["x"]["label"] == "wavelength-nm"


def test_spectrum_provider_applies_axis_label_and_unit_query_overrides(tmp_path: Path) -> None:
    path = _parquet(tmp_path / "spectrum.parquet", {"lambda": [400.0, 401.0], "intensity": [0.1, 0.5]})
    env = spectrum_provider(
        _request(
            path,
            record_md={"lambda_unit": "nm", "intensity_unit": "au"},
            extra_query={
                "axis_labels": {"x": "Raman shift", "y": "Signal"},
                "axis_units": {"x": "cm^-1", "y": "counts"},
            },
        )
    )
    assert env.kind is EnvelopeKind.SERIES
    assert env.payload["axes"]["x"]["name"] == "Raman shift"
    assert env.payload["axes"]["x"]["unit"] == "cm^-1"
    assert env.payload["axes"]["x"]["label"] == "Raman shift (cm^-1)"
    assert env.payload["axes"]["y"]["label"] == "Signal (counts)"


def test_spectrum_previewer_export_controls_exist(tmp_path: Path) -> None:
    """SC-006: export/save controls for figures and visible data."""
    path = _parquet(tmp_path / "s.parquet", {"lambda": [1.0, 2.0], "intensity": [3.0, 4.0]})
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "au"}))
    resource_ids = {r.resource_id for r in env.resources}
    # Figure export (vector + raster) and visible-data export.
    assert {"export_figure_svg", "export_figure_png", "export_figure_pdf", "export_points_csv"} <= resource_ids


def test_spectrum_resource_provider_exports_csv_and_svg(tmp_path: Path) -> None:
    path = _parquet(tmp_path / "s.parquet", {"lambda": [400.0, 410.0], "intensity": [0.1, 0.5]})
    request = _request(path, record_md={"lambda_unit": "nm", "intensity_unit": "au"})

    csv_data = spectrum_resource_provider(request, "export_points_csv", {"format": "csv", "target": "points"})
    assert csv_data["mime_type"] == "text/csv"
    csv_text = base64.b64decode(str(csv_data["data_uri"]).split(",", 1)[1]).decode("utf-8")
    assert "lambda,intensity" in csv_text
    assert "400.0,0.1" in csv_text

    svg_data = spectrum_resource_provider(request, "export_figure_svg", {"format": "svg", "target": "figure"})
    assert svg_data["mime_type"] == "image/svg+xml"
    svg_text = base64.b64decode(str(svg_data["data_uri"]).split(",", 1)[1]).decode("utf-8")
    assert "<svg" in svg_text


def test_spectrum_previewer_metadata_flags_are_honest(tmp_path: Path) -> None:
    path = _parquet(tmp_path / "s.parquet", {"lambda": [1.0, 2.0], "intensity": [3.0, 4.0]})
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "au"}))
    flags = env.metadata.to_dict()
    for name in ("sampled", "truncated", "complete", "failed"):
        assert name in flags and isinstance(flags[name], bool)
    # A small fully-read spectrum is complete and not failed.
    assert env.metadata.complete is True
    assert env.metadata.failed is False


def test_spectrum_provider_error_envelope_on_missing_file() -> None:
    env = spectrum_provider(_request(Path("/does/not/exist.parquet"), record_md={}))
    assert env.kind is EnvelopeKind.ERROR
    assert env.metadata.failed is True
    assert env.metadata.complete is False
    assert env.error is not None
