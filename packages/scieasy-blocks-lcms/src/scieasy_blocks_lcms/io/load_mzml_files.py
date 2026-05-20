"""LoadMzMLFiles — batch loader for mzML LC-MS acquisition files (T-LCMS-003).

Skeleton @ c08a885. Per ``docs/specs/phase11-lcms-block-spec.md`` §9
T-LCMS-003.

Records paths only — does NOT parse scan data. Reads minimal header
bytes from each ``.mzML`` / ``.mzXML`` to populate
:attr:`MSRawFile.Meta` (format, polarity, instrument,
acquisition_date, sample_id). The actual data stays in the file and is
processed externally by ElMAVEN.

See spec §8 Q-10 for the plural-only-no-singular-variant rationale.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.types import MSRawFile

_MZML_TIMESTAMP_RE = re.compile(r'startTimeStamp="([^"]+)"')
_MZML_POLARITY_POSITIVE = re.compile(r"MS:1000130")
_MZML_POLARITY_NEGATIVE = re.compile(r"MS:1000129")
_MZML_INSTRUMENT_RE = re.compile(r'<instrumentConfiguration[^>]*name="([^"]+)"')


class LoadMzMLFiles(_LCMSBlockMixin, IOBlock):
    """Batch loader that records paths to raw LC-MS acquisition files.

    See spec §9 T-LCMS-003 for the full specification, including the
    16 acceptance-criteria checkboxes covered by
    ``tests/test_io/test_load_ms_raw_files.py``.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "lcms.load_mzml_files"
    name: ClassVar[str] = "Load mzML Files"
    subcategory: ClassVar[str] = "io"
    description: ClassVar[str] = (
        "Batch loader for raw LC-MS acquisition files (mzML/mzXML/raw/d). "
        "Records paths and minimal header metadata; does not parse scan data."
    )

    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="scieasy-blocks-lcms.ms_raw.mzml.load",
            direction="load",
            data_type=MSRawFile,
            format_id="mzml",
            extensions=(".mzml",),
            label="mzML raw file",
            block_type="LoadMzMLFiles",
            handler="load",
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("format", "polarity", "instrument", "acquisition_date", "sample_id"),
                notes="Reads lightweight mzML header metadata only; scan data remains external.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-lcms.ms_raw.mzxml.load",
            direction="load",
            data_type=MSRawFile,
            format_id="mzxml",
            extensions=(".mzxml",),
            label="mzXML raw file",
            block_type="LoadMzMLFiles",
            handler="load",
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("format", "polarity", "instrument", "acquisition_date", "sample_id"),
                notes="Reads lightweight mzXML-compatible header metadata only; scan data remains external.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-lcms.ms_raw.raw.load",
            direction="load",
            data_type=MSRawFile,
            format_id="raw",
            extensions=(".raw",),
            label="Vendor RAW file",
            block_type="LoadMzMLFiles",
            handler="load",
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("format", "sample_id"),
                notes="Records path-derived metadata only; vendor RAW scan data remains external.",
            ),
        ),
        FormatCapability(
            id="scieasy-blocks-lcms.ms_raw.d.load",
            direction="load",
            data_type=MSRawFile,
            format_id="d",
            extensions=(".d",),
            label="Vendor .d directory",
            block_type="LoadMzMLFiles",
            handler="load",
            metadata_fidelity=MetadataFidelity(
                level="typed_meta",
                typed_meta_reads=("format", "sample_id"),
                notes="Records path-derived metadata only; vendor .d scan data remains external.",
            ),
        ),
    )

    # ADR-028 §D8: declare every extension this loader accepts. The mapping
    # values are the locked format identifiers persisted on
    # :attr:`MSRawFile.Meta.format` and consumed by :func:`_mime_for` — do
    # not change them without coordinating with downstream consumers.
    # Issue #1076.
    supported_extensions: ClassVar[dict[str, str]] = {
        ".mzml": "mzML",
        ".mzxml": "mzXML",
        ".raw": "raw",
        ".d": "d",
    }

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="raw_files",
            accepted_types=[MSRawFile],
            description="Collection of loaded raw file handles",
        ),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": ["string", "array"],
                "items": {"type": "string"},
                "title": "Raw file path(s)",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
        },
        "required": ["path"],
    }

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Load file path(s) and return ``Collection[MSRawFile]``.

        ADR-031 D4: ``output_dir`` accepted for signature compatibility.
        MSRawFile is an Artifact subclass — path-only transport, exempt
        from storage writes.

        Accepts ``config["path"]`` as a single string or a list of strings
        (matching the :class:`LoadImage` multi-file pattern).

        Each path is probed for lightweight header metadata via
        :func:`_probe_header`.

        Returns:
            ``Collection[MSRawFile]`` (possibly empty).

        Raises:
            FileNotFoundError: If any specified path does not exist.
            ValueError: If ``path`` is neither a string nor a list of strings.
        """
        raw_path = config.get("path")

        if isinstance(raw_path, list):
            paths = [Path(p) for p in raw_path if isinstance(p, str) and p]
        elif isinstance(raw_path, str) and raw_path:
            paths = [Path(raw_path)]
        else:
            raise ValueError("LoadMzMLFiles: config['path'] must be a non-empty string or list of strings")

        items: list[MSRawFile] = []
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"LoadMzMLFiles: path does not exist: {path}")
            # ADR-028 §D8 / #1076: use base-class extension lookup instead of
            # a private module-level helper. ``self._detect_format`` returns
            # ``None`` for paths whose suffix is not in
            # :attr:`supported_extensions`; we fall back to "raw" to preserve
            # the legacy "unknown vendor extension defaults to raw" behavior.
            file_format = self._detect_format(path) or "raw"
            meta = _probe_header(path, format_hint=file_format)
            items.append(
                MSRawFile(
                    file_path=path,
                    mime_type=_mime_for(meta.format),
                    description=path.name,
                    meta=meta,
                )
            )
        return Collection(items=cast(list[DataObject], items), item_type=MSRawFile)

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Not supported — :class:`LoadMzMLFiles` is input-only."""
        raise NotImplementedError("T-LCMS-003 LoadMzMLFiles is direction='input'; save() is unreachable.")


def _probe_header(path: Path, *, format_hint: str | None = None) -> MSRawFile.Meta:
    """Populate ``MSRawFile.Meta`` from the path and lightweight XML header sniffing.

    *format_hint* is required in practice (callers in this module pass the
    result of :meth:`IOBlock._detect_format` plus the legacy ``"raw"``
    fallback). The ``or "raw"`` default below preserves the prior behavior
    when callers omit the hint.

    ADR-028 §D8 / #1076: the previous module-level ``_detect_format`` was
    removed; the equivalent lookup now lives on
    :attr:`LoadMzMLFiles.supported_extensions` and the base-class
    :meth:`IOBlock._detect_format` helper.
    """
    file_format = format_hint or "raw"
    polarity: str | None = None
    instrument: str | None = None
    acquisition_date: datetime | None = None
    sample_id = path.stem

    if file_format in {"mzML", "mzXML"} and path.is_file():
        head = path.read_bytes()[:8192].decode("utf-8", errors="ignore")
        if _MZML_POLARITY_POSITIVE.search(head):
            polarity = "+"
        elif _MZML_POLARITY_NEGATIVE.search(head):
            polarity = "-"

        ts_match = _MZML_TIMESTAMP_RE.search(head)
        if ts_match:
            raw_value = ts_match.group(1)
            try:
                acquisition_date = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            except ValueError:
                acquisition_date = None

        instrument_match = _MZML_INSTRUMENT_RE.search(head)
        if instrument_match:
            instrument = instrument_match.group(1)

    return MSRawFile.Meta(
        format=file_format,
        polarity=polarity,
        instrument=instrument,
        acquisition_date=acquisition_date,
        sample_id=sample_id,
    )


def _mime_for(file_format: str) -> str:
    return {
        "mzML": "application/x-mzml+xml",
        "mzXML": "application/x-mzxml+xml",
        "raw": "application/octet-stream",
        "d": "inode/directory",
    }.get(file_format, "application/octet-stream")
