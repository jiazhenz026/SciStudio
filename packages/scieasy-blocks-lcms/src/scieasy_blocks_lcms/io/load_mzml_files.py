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
            meta = _probe_header(path)
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
    """Populate ``MSRawFile.Meta`` from the path and lightweight XML header sniffing."""
    file_format = format_hint or _detect_format(path)
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


def _detect_format(path: Path) -> str:
    """Infer the raw-file format from the suffix, preserving the locked enum values."""
    if path.is_dir() and path.suffix.lower() == ".d":
        return "d"

    suffix = path.suffix.lower()
    if suffix == ".mzml":
        return "mzML"
    if suffix == ".mzxml":
        return "mzXML"
    if suffix == ".raw":
        return "raw"
    return "raw"


def _mime_for(file_format: str) -> str:
    return {
        "mzML": "application/x-mzml+xml",
        "mzXML": "application/x-mzxml+xml",
        "raw": "application/octet-stream",
        "d": "inode/directory",
    }.get(file_format, "application/octet-stream")
