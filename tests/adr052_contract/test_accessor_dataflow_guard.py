"""Guard: ergonomic accessors must not appear in the core data-flow path.

Spec: ADR-052 §3.1 ("Core internal data flow must not use the ergonomic
accessors. Loaders, savers, auto-flush, worker serialization/reconstruction,
checkpointing, the scheduler/engine, and previewers' bounded reads operate on
the canonical form via to_memory() only") and §8 (the audit), with the Excel
``.xlsx`` reader/writer (#1810, PR #1815) as the SINGLE sanctioned pandas
exception.

Independent static scan: it searches the curated core data-flow modules for an
ergonomic-accessor CALL pattern ``.to_pandas(`` / ``.to_numpy(`` and fails on any
hit outside the sanctioned ``.xlsx`` reader/writer. The type-definition modules
(array/dataframe/series/base), which legitimately DEFINE the accessors, are
deliberately not scanned. The ``.xlsx`` exception is detected structurally: a
file under ``blocks/io/loaders`` or ``blocks/io/savers`` that references
openpyxl/Excel is the sanctioned reader/writer (so a non-xlsx loader using an
accessor would still be caught).

EXPECTED TO PASS in isolation: the guard is an invariant that holds before and
after #1817 (pre-impl, the only data-flow files carrying the tokens are the xlsx
reader/writer, which is sanctioned).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "scistudio"

#: Ergonomic-accessor call pattern (a call on an object), not bare prose.
_ACCESSOR_CALL = re.compile(r"\.to_(?:pandas|numpy)\s*\(")

#: Markers identifying the sanctioned .xlsx reader/writer (spec §3.1 / §6 note).
_XLSX_MARKERS = ("openpyxl", "read_excel", "to_excel", ".xlsx", "xlsx")

#: Curated core data-flow targets (files + dirs), per ADR-052 §3.1's enumeration.
#: Type-definition modules are intentionally excluded (they DEFINE the accessors).
_DATAFLOW_TARGETS = (
    "core/types/serialization.py",        # worker serialize / reconstruct
    "workflow/serializer.py",             # workflow serializer
    "engine/checkpoint.py",               # checkpoint
    "engine/runners/worker.py",           # worker
    "engine/runners/local.py",
    "engine/runners/base.py",
    "engine/resources.py",                # engine
    "engine/materialisation.py",
    "engine/scheduler",                   # scheduler (dir)
    "core/storage/flush_context.py",      # auto-flush machinery
    "blocks/base/block.py",               # _auto_flush / persist_*
    "blocks/process/process_block.py",    # per-item auto-flush path
    "blocks/io/io_block.py",              # IO dispatch auto-flush safety net
    "blocks/io/loaders",                  # loaders (xlsx reader sanctioned within)
    "blocks/io/savers",                   # savers (xlsx writer sanctioned within)
    "previewers/data_access.py",          # previewer bounded reads
    "previewers/session.py",
)


def _gather_files() -> list[Path]:
    files: list[Path] = []
    for rel in _DATAFLOW_TARGETS:
        target = _SRC / rel
        if target.is_dir():
            files.extend(sorted(p for p in target.glob("*.py")))
        elif target.is_file():
            files.append(target)
    return files


def _is_sanctioned_xlsx(path: Path, text: str) -> bool:
    parts = path.parts
    in_io_rw = "loaders" in parts or "savers" in parts
    return in_io_rw and any(marker in text for marker in _XLSX_MARKERS)


_FILES = _gather_files()


def test_dataflow_scan_is_populated() -> None:
    """Sanity: the curated data-flow scan resolved to real files."""
    assert _SRC.is_dir(), f"source tree not found at {_SRC}"
    assert len(_FILES) >= 8, (
        f"data-flow scan resolved too few files ({len(_FILES)}); the curated "
        f"target list may be stale relative to the source layout"
    )


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(_SRC)))
def test_no_ergonomic_accessor_in_dataflow(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if _is_sanctioned_xlsx(path, text):
        pytest.skip(f"sanctioned .xlsx reader/writer exception (#1810/#1815): {path.name}")

    hits = [
        (i, line.strip())
        for i, line in enumerate(text.splitlines(), start=1)
        if _ACCESSOR_CALL.search(line) and not line.lstrip().startswith("#")
    ]
    rel = path.relative_to(_SRC)
    assert not hits, (
        f"ergonomic accessor (.to_pandas()/.to_numpy()) used in core data-flow "
        f"module {rel} (ADR-052 §3.1 forbids it; use to_memory()):\n  "
        + "\n  ".join(f"L{n}: {src}" for n, src in hits)
    )
