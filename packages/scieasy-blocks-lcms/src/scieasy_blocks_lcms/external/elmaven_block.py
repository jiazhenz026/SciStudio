"""ElMAVENBlock -- AppBlock wrapper for ElMAVEN (T-LCMS-007 / part 1).

Rewritten to follow the standard AppBlock pattern (Fiji reference).
See issue #555 for context: the original hand-rolled state transitions,
exchange dir setup, bridge.launch(), and FileWatcher caused rerun
deadlocks because they bypassed the standard lifecycle.

The block now delegates to module-level helpers that mirror the
imaging package's shared infrastructure:
  - ``_resolve_exchange_dir()``   -- exchange directory resolution
  - ``_resolve_command()``        -- command resolution with config override
  - ``_prepare_elmaven_exchange()`` -- stage raw files + write manifest
  - ``_run_external_app()``       -- launch, watch, state transitions
  - ``_collect_elmaven_outputs()`` -- classify + load exported files

ElMAVEN-specific logic preserved:
  - Output classification via ``_classify_export()`` (column-header heuristic)
  - Two typed output ports: peak_table (PeakTable) and mid_table (MIDTable)
  - Raw file paths staged as symlinks and passed as positional CLI args
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, cast

from scieasy.blocks.app.app_block import AppBlock, _PopenProcessAdapter
from scieasy.blocks.app.bridge import FileExchangeBridge
from scieasy.blocks.app.watcher import FileWatcher, ProcessExitedWithoutOutputError
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.state import BlockState, ExecutionMode
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy_blocks_lcms._base import _LCMSBlockMixin
from scieasy_blocks_lcms.io.load_mid_table import LoadMIDTable
from scieasy_blocks_lcms.io.load_peak_table import LoadPeakTable
from scieasy_blocks_lcms.types import MIDTable, MSRawFile, PeakTable

logger = logging.getLogger(__name__)

try:
    from pandas.errors import EmptyDataError as _PandasEmptyDataErrorImported
except ModuleNotFoundError:

    class _PandasEmptyDataErrorFallbackError(Exception):
        """Fallback when pandas is not installed."""

    _PandasEmptyDataErrorImported = _PandasEmptyDataErrorFallbackError

EmptyDataError = _PandasEmptyDataErrorImported


# ---------------------------------------------------------------------------
# Shared helpers (mirror imaging package's interactive/__init__.py)
# ---------------------------------------------------------------------------


def _resolve_exchange_dir(config: BlockConfig, *, prefix: str) -> Path:
    """Resolve the file-exchange directory, creating it if needed."""
    explicit_dir = config.get("exchange_dir")
    if explicit_dir:
        exchange_dir = Path(str(explicit_dir))
    else:
        project_dir = config.get("project_dir")
        block_id = config.get("block_id")
        if project_dir and block_id:
            exchange_dir = Path(str(project_dir)) / "data" / "exchange" / str(block_id)
        else:
            exchange_dir = Path(tempfile.mkdtemp(prefix=prefix))
    exchange_dir.mkdir(parents=True, exist_ok=True)
    (exchange_dir / "inputs").mkdir(exist_ok=True)
    (exchange_dir / "outputs").mkdir(exist_ok=True)
    return exchange_dir


def _resolve_command(
    config: BlockConfig,
    *,
    app_command: str,
    override_key: str | None = None,
) -> str | list[str]:
    """Resolve the application command from config or class default."""
    raw_command = config.get("app_command")
    if raw_command is not None:
        if isinstance(raw_command, list):
            return [str(part) for part in raw_command]
        if isinstance(raw_command, str):
            return raw_command
        raise ValueError(f"App command must be str or list[str], got {type(raw_command).__name__}")

    executable = str(config.get(override_key) or app_command) if override_key is not None else app_command
    return [executable]


def _prepare_elmaven_exchange(
    raw_paths: list[str],
    exchange_dir: Path,
    *,
    tool_name: str,
    config: BlockConfig,
) -> None:
    """Stage raw file symlinks in the exchange dir and write the manifest.

    Raw files are staged as symlinks in the exchange directory for reference.
    The files are also passed as positional CLI arguments so ElMAVEN loads
    them automatically on launch.
    """
    input_dir = exchange_dir / "inputs"
    for rp in raw_paths:
        src = Path(rp)
        if src.exists():
            link = input_dir / src.name
            if not link.exists():
                with suppress(OSError):
                    link.symlink_to(src)

    manifest = {
        "tool": tool_name,
        "input_files": raw_paths,
        "output_dir": str(exchange_dir / "outputs"),
        "config": dict(config.params),
    }
    (exchange_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def _run_external_app(
    block: AppBlock,
    *,
    command: str | list[str],
    exchange_dir: Path,
    patterns: list[str],
    config: BlockConfig,
    launch_args: list[str] | None = None,
) -> list[Path]:
    """Launch an external application and wait for output files.

    Mirrors the imaging package's ``_run_external_app()`` exactly:
    state transitions, bridge launch, FileWatcher, cleanup.
    """
    bridge = FileExchangeBridge()
    stability_period = float(config.get("stability_period", 2.0))
    done_marker = config.get("done_marker")

    if block.state == BlockState.RUNNING:
        block.transition(BlockState.PAUSED)

    output_dir = exchange_dir / "outputs"
    logger.info(
        "Waiting for external application output. Save files to: %s",
        output_dir,
    )

    proc = bridge.launch(command, exchange_dir, argv_override=launch_args)
    watcher = FileWatcher(
        directory=output_dir,
        patterns=patterns,
        timeout=None,
        process_handle=_PopenProcessAdapter(proc),
        stability_period=stability_period,
        done_marker=str(done_marker) if done_marker is not None else None,
    )
    watcher.start()
    try:
        output_files = watcher.wait_for_output()
    except ProcessExitedWithoutOutputError:
        if block.state == BlockState.PAUSED:
            block.transition(BlockState.CANCELLED)
        return []
    except Exception:
        if block.state == BlockState.PAUSED:
            block.transition(BlockState.ERROR)
        raise
    finally:
        watcher.stop()
        with suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)

    if block.state == BlockState.PAUSED:
        block.transition(BlockState.RUNNING)
    if block.state == BlockState.RUNNING:
        block.transition(BlockState.DONE)
    return output_files


def _collect_elmaven_outputs(output_files: list[Path]) -> dict[str, Collection]:
    """Classify and load exported files into typed output collections.

    .. deprecated:: 2026-04 (issue #680)
       Replaced by ``AppBlock._bin_outputs_by_extension``. The function is
       retained as a deprecated import for backwards compatibility with
       existing test imports; ``ElMAVENBlock.run()`` no longer calls it.
    """
    peak_tables: list[PeakTable] = []
    mid_tables: list[MIDTable] = []
    for file_path in output_files:
        if _classify_export(file_path) == "mid_table":
            loaded = LoadMIDTable().load(BlockConfig(params={"path": str(file_path)}))
            if isinstance(loaded, Collection):
                mid_tables.extend(cast(list[MIDTable], list(loaded)))
            else:
                mid_tables.append(cast(MIDTable, loaded))
        else:
            loaded = LoadPeakTable().load(BlockConfig(params={"path": str(file_path), "source": "auto"}))
            if isinstance(loaded, Collection):
                peak_tables.extend(cast(list[PeakTable], list(loaded)))
            else:
                peak_tables.append(cast(PeakTable, loaded))

    return {
        "peak_table": Collection(items=cast(list[DataObject], peak_tables), item_type=PeakTable),
        "mid_table": Collection(items=cast(list[DataObject], mid_tables), item_type=MIDTable),
    }


def _classify_export(path: Path) -> str:
    """Return ``'mid_table'`` if *path* looks like a MID table, else ``'peak_table'``.

    Heuristic: MID tables have a column named ``C13`` or ``H2`` in the
    header row; peak tables typically have ``medMz`` / ``mz`` instead.

    .. deprecated:: 2026-04 (issue #680)
       Routing is now driven by user-declared port extensions on the
       AppBlock; this column-header heuristic is no longer used by
       ``ElMAVENBlock.run()``. Retained for backwards compatibility with
       existing test imports.
    """
    import pandas as pd

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            columns = pd.read_csv(path, nrows=0).columns
        elif suffix == ".tsv":
            columns = pd.read_csv(path, sep="\t", nrows=0).columns
        elif suffix in {".xlsx", ".xls"}:
            columns = pd.read_excel(path, nrows=0).columns
        else:
            return "peak_table"
    except (EmptyDataError, ValueError):
        return "peak_table"

    names = {str(column) for column in columns}
    if {"C13", "H2"} & names:
        return "mid_table"
    return "peak_table"


# ---------------------------------------------------------------------------
# Block definition
# ---------------------------------------------------------------------------


class ElMAVENBlock(_LCMSBlockMixin, AppBlock):
    """Launch ElMAVEN for interactive peak picking on a batch of raw files.

    Follows the standard AppBlock pattern (same as FijiBlock): delegates
    exchange dir setup, command resolution, app launch, file watching, and
    state transitions to shared helpers. ElMAVEN-specific logic is limited
    to input staging (symlinks) and output classification (peak_table vs
    mid_table).
    """

    name: ClassVar[str] = "ElMAVEN"
    type_name: ClassVar[str] = "lcms.elmaven"
    subcategory: ClassVar[str] = "external"
    description: ClassVar[str] = (
        "Open a batch of MSRawFiles in ElMAVEN for interactive peak picking. "
        "Collects exported peak tables (and optional MID tables) from the "
        "exchange directory."
    )

    app_command: ClassVar[str] = "elmaven"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*.csv", "*.tsv", "*.xlsx"]

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(
            name="raw_files",
            accepted_types=[MSRawFile],
            required=True,
            description="Raw acquisition files to open in ElMAVEN",
        ),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(
            name="peak_table",
            accepted_types=[PeakTable],
            description="Exported peak table from ElMAVEN",
        ),
        OutputPort(
            name="mid_table",
            accepted_types=[MIDTable],
            required=False,
            description="Exported MID table from ElMAVEN (optional)",
        ),
    ]

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "elmaven_path": {
                "type": ["string", "null"],
                "default": None,
                "title": "Executable Path",
                "ui_priority": 0,
                "ui_widget": "file_browser",
            },
        },
    }

    def run(
        self,
        inputs: dict[str, Collection],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Stage raw files and launch ElMAVEN for interactive peak picking.

        Follows the standard AppBlock pattern:
        1. Extract input data
        2. Resolve exchange directory
        3. Prepare exchange (stage files + manifest)
        4. Resolve command
        5. Launch app via shared helper (handles state, watcher, cleanup)
        6. Collect and classify outputs
        """
        # 1. Extract raw file paths from input.
        raw_items = list(inputs.get("raw_files", Collection(items=[], item_type=MSRawFile)))
        raw_paths = [str(Path(item.file_path).resolve()) for item in raw_items if item.file_path is not None]

        # 2. Resolve exchange directory.
        exchange_dir = _resolve_exchange_dir(config, prefix="scieasy_elmaven_")

        # 3. Stage raw files and write manifest.
        _prepare_elmaven_exchange(raw_paths, exchange_dir, tool_name=self.type_name, config=config)

        # 4. Resolve command.
        command = _resolve_command(config, app_command=self.app_command, override_key="elmaven_path")

        # 5. Launch and wait (shared helper manages state transitions).
        # Pass raw file paths as positional args so ElMAVEN loads them on launch.
        # Issue #680: broaden watcher patterns to cover each declared extension.
        patterns = list(self.output_patterns)
        configured_ports = config.get("output_ports") or []
        if isinstance(configured_ports, list):
            for entry in configured_ports:
                if isinstance(entry, dict) and entry.get("extension"):
                    ext = str(entry["extension"]).strip().lstrip(".").lower()
                    if ext and f"*.{ext}" not in patterns:
                        patterns.append(f"*.{ext}")
        output_files = _run_external_app(
            self,
            command=command,
            exchange_dir=exchange_dir,
            patterns=patterns,
            config=config,
            launch_args=raw_paths,
        )

        # 6. Route output files into user-declared ports by extension
        # (issue #680). The legacy column-header heuristic
        # (``_collect_elmaven_outputs`` / ``_classify_export``) has been
        # replaced by the generic binner — users declare peak_table vs
        # mid_table ports with distinct extensions in the port editor.
        if config.get("output_ports"):
            return self._bin_outputs_by_extension(output_files, config)
        # Backwards-compatible fallback: wrap every exported file as an
        # Artifact under ``peak_table`` until the user opens the port
        # editor and declares extensions.
        from scieasy.blocks.app.bridge import _guess_mime
        from scieasy.core.types.artifact import Artifact

        artifacts = [Artifact(file_path=p, mime_type=_guess_mime(p), description=p.name) for p in output_files]
        if not artifacts:
            return {}
        return {"peak_table": Collection(artifacts, item_type=Artifact)}
