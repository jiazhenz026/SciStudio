"""ExternalAppBridge protocol and default file-exchange implementation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalAppBridge(Protocol):
    """Structural protocol for bridging external GUI applications."""

    def prepare(self, inputs: dict[str, Any], exchange_dir: Path) -> None: ...
    def launch(self, command: str, exchange_dir: Path) -> Any: ...
    def watch(self, exchange_dir: Path, patterns: list[str]) -> list[Path]: ...
    def collect(self, output_files: list[Path]) -> dict[str, Any]: ...


class FileExchangeBridge:
    """Default bridge that serialises inputs to JSON/files and launches a subprocess.

    .. note::

        Engine-level subprocess management (ADR-017 spawn_block_process factory)
        and ProcessHandle integration (ADR-019) are handled by LocalRunner.
    """

    def prepare(self, inputs: dict[str, Any], exchange_dir: Path) -> None:
        """Serialise *inputs* into *exchange_dir*."""
        exchange_dir.mkdir(parents=True, exist_ok=True)
        input_dir = exchange_dir / "inputs"
        input_dir.mkdir(exist_ok=True)

        manifest: dict[str, Any] = {}
        for key, value in inputs.items():
            # ADR-031 D2: ViewProxy eliminated. DataObject.to_memory()
            # is called directly when data materialisation is needed.
            from scieasy.core.types.base import DataObject

            if isinstance(value, DataObject) and not hasattr(value, "__iter__"):
                value = value.to_memory() if value.storage_ref is not None else value

            # ADR-020-Add2: iterate Collection items one at a time.
            from scieasy.core.types.collection import Collection

            if isinstance(value, Collection):
                collection_dir = input_dir / key
                collection_dir.mkdir(exist_ok=True)
                item_paths = []
                for i, item in enumerate(value):
                    # ADR-031: use to_memory() directly instead of .view().to_memory()
                    data = item.to_memory() if item.storage_ref is not None else item.user
                    item_path = collection_dir / f"item_{i:04d}.json"
                    item_path.write_text(json.dumps(data, default=str), encoding="utf-8")
                    item_paths.append(str(item_path))
                manifest[key] = {"type": "collection", "items": item_paths}
                continue

            if isinstance(value, (str, int, float, bool)):
                manifest[key] = {"type": "scalar", "value": value}
            elif isinstance(value, bytes):
                file_path = input_dir / f"{key}.bin"
                file_path.write_bytes(value)
                manifest[key] = {"type": "file", "path": str(file_path)}
            else:
                file_path = input_dir / f"{key}.json"
                file_path.write_text(json.dumps(value, default=str), encoding="utf-8")
                manifest[key] = {"type": "json", "path": str(file_path)}

        manifest_path = exchange_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def launch(
        self,
        command: str | list[str],
        exchange_dir: Path,
        argv_override: list[str] | None = None,
    ) -> subprocess.Popen[bytes]:
        """Launch the external application with *command*.

        The command is validated through :func:`validate_app_command` to prevent
        shell injection attacks (see issue #70).  ``shell=False`` is set
        explicitly as a defence-in-depth measure.

        Parameters
        ----------
        command:
            Executable and any fixed arguments (validated for injection safety).
        exchange_dir:
            The file-exchange working directory, used as ``cwd`` for the process.
        argv_override:
            When provided, these strings are appended to the validated command
            instead of the default ``str(exchange_dir)`` suffix.  Use this to
            pass specific file paths (e.g. staged TIFF files) to applications
            that open files by path rather than by directory (see issue #420).
        """
        from scieasy.blocks.app.command_validator import validate_app_command

        parts = validate_app_command(command)
        trailing = argv_override if argv_override is not None else [str(exchange_dir)]
        cmd = [*parts, *trailing]
        # macOS .app bundles must be launched via `open` (#483).
        # Use ``-W`` so ``open`` blocks until the launched .app exits — the
        # returned ``Popen`` then tracks the .app's lifetime instead of the
        # short-lived ``open`` launcher (#677). ``-n`` forces a fresh
        # instance so the watcher is keyed to the new process and we do not
        # accidentally wait on an unrelated existing window.
        if sys.platform == "darwin" and cmd[0].endswith(".app"):
            cmd = ["open", "-W", "-n", "-a", cmd[0], "--args", *cmd[1:]]
        return subprocess.Popen(
            cmd,
            cwd=str(exchange_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    def watch(self, exchange_dir: Path, patterns: list[str]) -> list[Path]:
        """Watch *exchange_dir* for output files matching *patterns*."""
        from scieasy.blocks.app.watcher import FileWatcher

        output_dir = exchange_dir / "outputs"
        output_dir.mkdir(exist_ok=True)
        watcher = FileWatcher(directory=output_dir, patterns=patterns, timeout=300)
        watcher.start()
        try:
            return watcher.wait_for_output()
        finally:
            watcher.stop()

    def collect(self, output_files: list[Path]) -> dict[str, Any]:
        """Collect results from *output_files* into a typed output mapping."""
        from scieasy.core.types.artifact import Artifact

        results: dict[str, Any] = {}
        for fp in output_files:
            artifact = Artifact(file_path=fp, mime_type=_guess_mime(fp), description=fp.name)
            results[fp.stem] = artifact
        return results


def _guess_mime(path: Path) -> str:
    """Guess MIME type from file extension."""
    mapping = {
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".json": "application/json",
        ".txt": "text/plain",
        ".png": "image/png",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".pdf": "application/pdf",
    }
    return mapping.get(path.suffix.lower(), "application/octet-stream")
