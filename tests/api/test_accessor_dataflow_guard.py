"""ADR-052 §8 guard: the ergonomic accessors stay out of the core data flow.

ADR-052 §3.1 adds ``to_pandas()`` / ``to_numpy()`` for *author* convenience
only. The core data-flow path — loaders, savers, auto-flush, worker
serialization/reconstruction, checkpointing, the scheduler/engine, and the
previewer bounded reads — must operate on the canonical form via ``to_memory()``
(Arrow / ndarray), never through the ergonomic accessors. The single sanctioned
pandas-using exception is the Excel (``.xlsx``) reader/writer (#1810, PR #1815),
which must use pandas/openpyxl at the format boundary because ``pyarrow`` cannot
read or write Excel.

This is a static scan over the listed data-flow source modules. It asserts the
accessor-call tokens ``.to_pandas(`` / ``.to_numpy(`` appear only in explicitly
allow-listed locations (with a recorded reason). Any *new* occurrence — e.g. a
loader calling ``frame.to_pandas()`` on a ``DataObject`` to move data — trips the
guard. The guard is intentionally green on today's tree (the two existing
occurrences are pyarrow methods, not ``DataObject`` accessors) so a regression is
unambiguous.
"""

from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "scistudio"

# Core data-flow modules ADR-052 §8 names. Paths are relative to ``_SRC``.
_DATA_FLOW_TARGETS: tuple[str, ...] = (
    "blocks/io/loaders",
    "blocks/io/savers",
    "blocks/base/block.py",  # _auto_flush / pack / map_items / parallel_map
    "core/types/serialization.py",  # worker serialization / reconstruction
    "engine/runners/worker.py",
    "engine/runners/local.py",
    "engine/checkpoint.py",
    "engine/scheduler",
    "previewers/data_access.py",  # bounded reads
)

# Locations allowed to contain an accessor-name token, with the reason. Keys are
# POSIX paths relative to ``_SRC``.
#
# Both current occurrences are pyarrow methods, NOT the DataObject ergonomic
# accessors, so neither is a data-flow violation:
_ALLOWLIST: dict[str, str] = {
    # ADR-052 §3.1 single sanctioned pandas exception: the .xlsx writer uses
    # pyarrow.Table.to_pandas() at the format boundary (#1810, PR #1815).
    "blocks/io/savers/_helpers.py": "sanctioned .xlsx reader/writer pandas boundary (ADR-052 §3.1; #1810/#1815)",
    # Benign pyarrow ChunkedArray.to_numpy() (Arrow column -> ndarray leaf read);
    # not the DataObject ergonomic accessor and not a data-flow conversion.
    "blocks/io/loaders/load_data.py": "pyarrow column.to_numpy() leaf read (not the DataObject accessor)",
}

_ACCESSOR_TOKEN = re.compile(r"\.to_pandas\(|\.to_numpy\(")


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for target in _DATA_FLOW_TARGETS:
        path = _SRC / target
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            files.append(path)
        # Missing optional paths are silently skipped; the layout-coverage test
        # below asserts the load-bearing ones exist.
    return files


def test_data_flow_target_layout_is_present() -> None:
    """At least the core data-flow anchors must exist (so the scan is meaningful)."""
    required = (
        "blocks/io/loaders",
        "blocks/io/savers",
        "blocks/base/block.py",
        "core/types/serialization.py",
        "previewers/data_access.py",
    )
    missing = [t for t in required if not (_SRC / t).exists()]
    assert not missing, f"expected core data-flow modules are missing (scan would be hollow): {missing}"


def test_ergonomic_accessors_absent_from_core_data_flow() -> None:
    """No un-allow-listed ``.to_pandas(`` / ``.to_numpy(`` in the data-flow path."""
    violations: list[str] = []
    for file in _iter_py_files():
        rel = file.relative_to(_SRC).as_posix()
        if rel in _ALLOWLIST:
            continue
        text = file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _ACCESSOR_TOKEN.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, (
        "ergonomic accessor (to_pandas/to_numpy) used in the core data-flow path "
        "(ADR-052 §8 — use to_memory() instead; the only sanctioned pandas exception "
        "is the .xlsx reader/writer):\n  " + "\n  ".join(violations)
    )


def test_xlsx_exception_is_the_only_sanctioned_pandas_boundary() -> None:
    """Record that the .xlsx writer is the single sanctioned pandas-using exception.

    Pins the allowlist's intent: exactly one entry is the sanctioned pandas
    boundary (the .xlsx reader/writer); the other is a benign pyarrow leaf read.
    If a future change adds another sanctioned exception, it must be an explicit,
    reviewed allowlist edit — not a silent data-flow leak.
    """
    sanctioned = [path for path, reason in _ALLOWLIST.items() if "xlsx" in reason.lower()]
    assert sanctioned == ["blocks/io/savers/_helpers.py"], (
        "the single sanctioned pandas data-flow exception must be the .xlsx "
        f"reader/writer (ADR-052 §3.1); got {sanctioned}"
    )
