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

    def prepare(
        self,
        inputs: dict[str, Any],
        exchange_dir: Path,
        *,
        registry: Any | None = None,
    ) -> None:
        """Serialise *inputs* into *exchange_dir*.

        ADR-028 §D8 / #1080: :class:`DataObject` inputs (including items
        inside a :class:`Collection`) are materialised to real files via
        :func:`scieasy.engine.materialisation.materialise_to_file` —
        which routes through :meth:`BlockRegistry.find_saver` and
        prefers a :func:`scieasy.utils.fs.mount_pathlike` pass-through
        when ``storage_ref.path`` already matches the target extension.
        Scalar (``str``/``int``/``float``/``bool``), ``bytes``, and
        otherwise-unknown inputs keep the legacy JSON / raw-bytes
        serialisation paths.

        The manifest format per port is now:

        - DataObject:
          ``{"type": <ClassName>, "path": <abspath>, "extension": ".csv",
          "format": "csv"}``.
        - Collection:
          ``{"type": "collection", "item_type": <ClassName | "mixed">,
          "items": [{"type": ..., "path": ..., "extension": ...,
          "format": ...}, ...]}``.
        - Scalar: ``{"type": "scalar", "value": <value>}``.
        - Bytes: ``{"type": "file", "path": <abspath>}`` (extension
          ``".bin"``).
        - Fallback JSON: ``{"type": "json", "path": <abspath>,
          "extension": ".json", "format": "json"}``.

        The optional *registry* kwarg lets callers in hot paths
        (FileExchangeBridge is normally instantiated once per AppBlock
        execution) amortise the registry scan; when omitted,
        :func:`materialise_to_file` builds and scans a fresh one.
        """
        # Imports are scoped to keep the bridge module's import-time
        # footprint small (consistent with the rest of this file).
        from scieasy.core.types.base import DataObject
        from scieasy.core.types.collection import Collection

        exchange_dir.mkdir(parents=True, exist_ok=True)
        input_dir = exchange_dir / "inputs"
        input_dir.mkdir(exist_ok=True)

        manifest: dict[str, Any] = {}
        for key, value in inputs.items():
            # ADR-020-Add2: iterate Collection items one at a time. We
            # materialise each item independently so the external app
            # receives one file per element under ``inputs/<key>/``.
            if isinstance(value, Collection):
                collection_dir = input_dir / key
                collection_dir.mkdir(exist_ok=True)
                item_entries: list[dict[str, Any]] = []
                item_types: set[str] = set()
                for i, item in enumerate(value):
                    item_entries.append(
                        _materialise_data_object(
                            item,
                            collection_dir,
                            filename_stem=f"item_{i:04d}",
                            registry=registry,
                        )
                    )
                    item_types.add(type(item).__name__)
                manifest[key] = {
                    "type": "collection",
                    "item_type": next(iter(item_types)) if len(item_types) == 1 else "mixed",
                    "items": item_entries,
                }
                continue

            # ADR-028 §D8 / #1080: type-dispatched materialisation
            # for DataObject inputs. Replaces the legacy
            # ``json.dumps(value.to_memory(), default=str)`` path,
            # which produced a useless ``str(ndarray)`` repr for
            # numpy-backed objects.
            if isinstance(value, DataObject):
                manifest[key] = _materialise_data_object(
                    value,
                    input_dir,
                    filename_stem=key,
                    registry=registry,
                )
                continue

            if isinstance(value, (str, int, float, bool)):
                manifest[key] = {"type": "scalar", "value": value}
            elif isinstance(value, bytes):
                file_path = input_dir / f"{key}.bin"
                file_path.write_bytes(value)
                manifest[key] = {
                    "type": "file",
                    "path": str(file_path),
                    "extension": ".bin",
                    "format": "binary",
                }
            else:
                # Last-resort fallback: anything else (e.g. a plain
                # dict not tied to a DataObject) is JSON-serialised
                # using ``default=str``. This preserves backward
                # compatibility for AppBlock subclasses that pre-stage
                # ad-hoc dict inputs without registering a DataObject
                # type.
                file_path = input_dir / f"{key}.json"
                file_path.write_text(json.dumps(value, default=str), encoding="utf-8")
                manifest[key] = {
                    "type": "json",
                    "path": str(file_path),
                    "extension": ".json",
                    "format": "json",
                }

        # silence: ``materialise_to_file`` deliberately raises ``LookupError``
        # when no saver covers a type — bubble that to the caller so the
        # AppBlock author sees a clear "no saver registered for X" error
        # instead of a half-written manifest.

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


_CORE_TYPE_DEFAULT_EXTENSION: dict[str, str] = {
    # ADR-028 §D8 / #1080: per-core-type default extension when
    # ``materialise_to_file`` is called without an explicit extension.
    # The canonical generic saver (``SaveData``) advertises a flat union
    # of extensions across all core types via its ``supported_extensions``
    # ClassVar, so the materialiser's "first-declared extension wins"
    # default would pick ``.npy`` for everything (which the DataFrame
    # branch then rejects). This per-type map gives the bridge a stable,
    # type-appropriate default. Plugin types not listed here fall back
    # to the materialiser's saver-declared default — which is correct
    # for plugin savers that declare a type-specific extension set.
    "DataFrame": ".csv",
    "Series": ".csv",
    "Array": ".npy",
    "Text": ".txt",
    "Artifact": ".bin",
    "CompositeData": ".zarr",
}


def _default_extension_for_obj(obj: Any) -> str | None:
    """Return the bridge's preferred default extension for *obj*.

    Walks ``type(obj).__mro__`` looking for a matching name in
    :data:`_CORE_TYPE_DEFAULT_EXTENSION`. Returns ``None`` when no
    core-type ancestor is registered — the materialiser then falls
    back to the saver-declared default.
    """
    for base in type(obj).__mro__:
        if base.__name__ in _CORE_TYPE_DEFAULT_EXTENSION:
            return _CORE_TYPE_DEFAULT_EXTENSION[base.__name__]
    return None


def _materialise_data_object(
    obj: Any,
    dest_dir: Path,
    *,
    filename_stem: str,
    registry: Any | None,
) -> dict[str, Any]:
    """Materialise *obj* (a :class:`DataObject`) and return a manifest entry.

    Routes through :func:`scieasy.engine.materialisation.materialise_to_file`,
    which selects a saver via :meth:`BlockRegistry.find_saver` (#1077),
    prefers a :func:`scieasy.utils.fs.mount_pathlike` pass-through when
    ``obj.storage_ref.path`` already matches the chosen extension, and
    falls back to the saver round-trip otherwise.

    The returned manifest entry is:

    ``{"type": <DataObject subclass name>, "path": <abspath>,
    "extension": ".csv", "format": "csv"}``

    where ``format`` comes from the resolved saver's
    :attr:`supported_extensions` mapping (the same format identifier
    surfaced by :meth:`IOBlock._detect_format`). When no saver declares
    a format for the chosen extension, ``format`` is ``None``.
    """
    from scieasy.engine.materialisation import materialise_to_file

    extension = _default_extension_for_obj(obj)
    out_path = materialise_to_file(
        obj,
        dest_dir,
        extension=extension,
        filename_stem=filename_stem,
        registry=registry,
    )
    resolved_extension = out_path.suffix
    fmt = _resolve_format_for(type(obj), resolved_extension, registry=registry)
    return {
        "type": type(obj).__name__,
        "path": str(out_path),
        "extension": resolved_extension,
        "format": fmt,
    }


def _resolve_format_for(
    cls: type,
    extension: str,
    *,
    registry: Any | None,
) -> str | None:
    """Return the format identifier the resolved saver uses for *extension*.

    Mirrors :meth:`IOBlock._detect_format` lookup semantics: case-
    insensitive trailing-suffix match against the saver's
    :attr:`supported_extensions` mapping. Returns ``None`` when the
    materialisation helper picked an extension via the pass-through
    branch and no saver declares it (an edge case, since the
    pass-through path is only taken when the same saver is available).
    """
    from scieasy.blocks.registry import BlockRegistry

    reg = registry if registry is not None else BlockRegistry()
    if registry is None:
        reg.scan()
    saver_cls = reg.find_saver(cls, extension)
    if saver_cls is None:
        return None
    exts: dict[str, str] = getattr(saver_cls, "supported_extensions", {}) or {}
    normalised = {k.lower(): v for k, v in exts.items()}
    return normalised.get(extension.lower())


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
