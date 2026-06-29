"""ExternalAppBridge protocol and default file-exchange implementation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from scistudio.stability import provisional

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry


def _external_app_launch_env() -> dict[str, str] | None:
    """Return a process environment for launching an external app, or ``None``.

    External-app blocks (e.g. :class:`NapariBlock`) launch user-installed GUI
    commands by name. Console scripts installed through the in-app Python
    terminal land in the shared user dependency site's script directory, which
    is not on the backend's inherited ``PATH``. Prepend that directory so
    commands like ``napari`` resolve at launch time (#1772).

    Returns ``None`` when the script directory does not exist so the subprocess
    inherits the parent environment unchanged (``env=None`` to ``Popen``).
    """
    try:
        from scistudio.desktop.paths import user_python_script_dir
    except Exception:  # pragma: no cover - desktop paths always importable here
        return None
    script_dir = user_python_script_dir()
    if not script_dir.is_dir():
        return None
    env = dict(os.environ)
    parts = [str(script_dir)]
    for part in env.get("PATH", "").split(os.pathsep):
        if part and part not in parts:
            parts.append(part)
    env["PATH"] = os.pathsep.join(parts)
    return env


@provisional(since="0.3.1")
@runtime_checkable
class ExternalAppBridge(Protocol):
    """The contract an :class:`AppBlock` uses to talk to an external program.

    A bridge is the four-step adapter between a block and a desktop application:
    write the inputs somewhere the app can read them, launch the app, watch for
    the files it produces, and load those files back as results. Provide your
    own implementation to support an app that needs a different on-disk layout
    or launch convention; the default is :class:`FileExchangeBridge`.

    Because this is a runtime-checkable protocol, any object with matching
    ``prepare`` / ``launch`` / ``watch`` / ``collect`` methods satisfies it
    without subclassing.
    """

    def prepare(self, inputs: dict[str, Any], exchange_dir: Path) -> None:
        """Write *inputs* into *exchange_dir* so the external app can read them."""
        ...

    def launch(self, command: str, exchange_dir: Path) -> Any:
        """Start the external application and return a handle to its process."""
        ...

    def watch(self, exchange_dir: Path, patterns: list[str]) -> list[Path]:
        """Wait for output files matching *patterns* and return their paths."""
        ...

    def collect(self, output_files: list[Path]) -> dict[str, Any]:
        """Load *output_files* into a mapping of result name to value."""
        ...


@provisional(since="0.3.1")
class FileExchangeBridge:
    """Default :class:`ExternalAppBridge`: swap data with an app through files.

    This is the bridge :class:`AppBlock` uses unless you supply your own. It
    serialises each input to a file (or to JSON for scalars and unknown values)
    under an exchange directory, launches the executable with that directory as
    its working directory, watches an ``outputs`` subfolder for files the app
    writes, and turns each output file into an
    :class:`~scistudio.core.types.artifact.Artifact`.

    Example:
        A block rarely builds this directly — :class:`AppBlock` constructs and
        drives the bridge. Manual use looks like::

            bridge = FileExchangeBridge()
            bridge.prepare({"image": my_array}, exchange_dir)
            proc = bridge.launch("/Applications/Fiji.app", exchange_dir)
    """

    # Engine-level subprocess management and process-handle integration live in
    # LocalRunner, not here (see ADR-017 / ADR-019).

    @provisional(since="0.3.1")
    def prepare(
        self,
        inputs: dict[str, Any],
        exchange_dir: Path,
        *,
        input_ports: list[dict[str, Any]] | None = None,
        registry: Any | None = None,
    ) -> None:
        """Write each input into *exchange_dir* and record a manifest.

        Typed data objects (and the items inside a
        :class:`~scistudio.core.types.collection.Collection`) are saved to real
        files via
        :func:`scistudio.blocks.io.materialisation.materialise_to_file`,
        reusing the object's existing on-disk file when its extension already
        matches the target. Scalars (``str`` / ``int`` / ``float`` / ``bool``),
        ``bytes``, and otherwise-unknown values fall back to JSON or raw-bytes
        files. A ``manifest.json`` describing every input is written alongside
        them so the external app can find each file.

        The manifest entry per input is one of:

        - data object:
          ``{"type": <ClassName>, "path": <abspath>, "extension": ".csv",
          "format": "csv"}``
        - collection:
          ``{"type": "collection", "item_type": <ClassName | "mixed">,
          "items": [<entry>, ...]}``
        - scalar: ``{"type": "scalar", "value": <value>}``
        - bytes: ``{"type": "file", "path": <abspath>}`` (extension ``".bin"``)
        - other: ``{"type": "json", "path": <abspath>, "extension": ".json",
          "format": "json"}``

        Args:
            inputs: Input values keyed by input-port name.
            exchange_dir: Directory to write inputs and the manifest into; an
                ``inputs`` subfolder is created inside it.
            input_ports: Optional per-port settings (such as a preferred file
                ``extension``) from the port editor.
            registry: Optional pre-scanned block registry to reuse; when omitted
                a fresh one is built and scanned for this call.

        Raises:
            TypeError: If an input value is a bare ``list``/``tuple`` containing
                :class:`~scistudio.core.types.base.DataObject` items. Wrap a batch
                of data objects in a
                :class:`~scistudio.core.types.collection.Collection` instead so
                each item is materialised to its own file (#1874).
        """
        from scistudio.core.types.base import DataObject
        from scistudio.core.types.collection import Collection

        exchange_dir.mkdir(parents=True, exist_ok=True)
        input_dir = exchange_dir / "inputs"
        input_dir.mkdir(exist_ok=True)

        port_config = _port_config_by_name(input_ports)
        manifest: dict[str, Any] = {}
        for key, value in inputs.items():
            selected = port_config.get(key, {})
            extension = _normalise_config_extension(selected.get("extension"))
            capability_id = _normalise_capability_id(selected.get("capability_id"))
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
                            extension=extension,
                            capability_id=capability_id,
                            registry=registry,
                        )
                    )
                    item_types.add(type(item).__name__)
                if len(item_types) == 1:
                    item_type_name = next(iter(item_types))
                elif len(item_types) == 0:
                    declared = getattr(value, "item_type", None)
                    item_type_name = declared.__name__ if declared is not None else "mixed"
                else:
                    item_type_name = "mixed"
                manifest[key] = {
                    "type": "collection",
                    "item_type": item_type_name,
                    "items": item_entries,
                }
                continue

            if isinstance(value, DataObject):
                manifest[key] = _materialise_data_object(
                    value,
                    input_dir,
                    filename_stem=key,
                    extension=extension,
                    capability_id=capability_id,
                    registry=registry,
                )
                continue

            if isinstance(value, (str, int, float, bool)):
                manifest[key] = {"type": "scalar", "value": value}
            elif isinstance(value, (list, tuple)) and any(isinstance(item, DataObject) for item in value):
                # #1874: a bare list/tuple of DataObjects is not a recognised
                # input shape. Materialising it would require a homogeneous
                # item type the bare sequence does not carry, and falling through
                # to the JSON branch below would silently serialise each item as a
                # useless ``repr`` string and stage no files. Fail loudly and
                # point the caller at ``Collection``, which is the typed batch
                # carrier the collection branch above materialises item-by-item.
                raise TypeError(
                    f"Input {key!r} is a bare {type(value).__name__} containing "
                    "DataObject items. Wrap a batch of data objects in a "
                    "Collection so each item is staged to its own file under "
                    "inputs/<port>/; a raw sequence has no homogeneous item-type "
                    "guarantee and cannot be materialised."
                )
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
                file_path = input_dir / f"{key}.json"
                file_path.write_text(json.dumps(value, default=str), encoding="utf-8")
                manifest[key] = {
                    "type": "json",
                    "path": str(file_path),
                    "extension": ".json",
                    "format": "json",
                }

        manifest_path = exchange_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @provisional(since="0.3.1")
    def launch(
        self,
        command: str | list[str],
        exchange_dir: Path,
        argv_override: list[str] | None = None,
    ) -> subprocess.Popen[bytes]:
        """Start the external application and return its process handle.

        The command is checked by :func:`validate_app_command` to reject shell
        metacharacters before launch, and ``shell=False`` is used as a second
        line of defence. On macOS, a ``.app`` bundle is opened with ``open -W``
        so the returned process tracks the application's lifetime rather than
        the short-lived launcher.

        Args:
            command: Executable and any fixed arguments, as a single string or a
                pre-split argument list.
            exchange_dir: File-exchange directory used as the process working
                directory and, by default, passed to the app as its argument.
            argv_override: When given, these strings are passed to the app
                instead of the exchange-directory path — use it for apps that
                open specific files by path (for example staged TIFF files)
                rather than a whole directory.

        Returns:
            The launched process as a :class:`subprocess.Popen`.

        Raises:
            ValueError: If the command fails the injection-safety check.
        """
        from scistudio.blocks.app.command_validator import validate_app_command

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
            env=_external_app_launch_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    @provisional(since="0.3.1")
    def watch(self, exchange_dir: Path, patterns: list[str]) -> list[Path]:
        """Wait for output files in *exchange_dir* and return their paths.

        Watches an ``outputs`` subfolder of *exchange_dir* until files matching
        *patterns* appear and stop changing.

        Args:
            exchange_dir: The exchange directory whose ``outputs`` subfolder is
                watched.
            patterns: Glob patterns the output files must match.

        Returns:
            Paths of the detected output files.

        Raises:
            TimeoutError: If no matching files appear within the watch timeout.
        """
        from scistudio.blocks.app.watcher import FileWatcher

        output_dir = exchange_dir / "outputs"
        output_dir.mkdir(exist_ok=True)
        watcher = FileWatcher(directory=output_dir, patterns=patterns, timeout=300)
        watcher.start()
        try:
            return watcher.wait_for_output()
        finally:
            watcher.stop()

    @provisional(since="0.3.1")
    def collect(self, output_files: list[Path]) -> dict[str, Any]:
        """Wrap each output file as an Artifact, keyed by its file stem.

        Args:
            output_files: Paths of files the external app produced.

        Returns:
            A mapping from each file's stem (its name without extension) to an
            :class:`~scistudio.core.types.artifact.Artifact` for that file.
        """
        from scistudio.core.types.artifact import Artifact

        results: dict[str, Any] = {}
        for fp in output_files:
            # mime_type is non-load-bearing (it only feeds a provenance
            # sidecar; dispatch keys off extension, not MIME), so leave it
            # unset to match the typed path (ADR-052 §7.2).
            artifact = Artifact(file_path=fp, mime_type=None, description=fp.name)
            results[fp.stem] = artifact
        return results


_CORE_TYPE_DEFAULT_EXTENSION: dict[str, str] = {
    "DataFrame": ".csv",
    "Series": ".csv",
    "Array": ".npy",
    "Text": ".txt",
    "Artifact": ".bin",
    "CompositeData": ".zarr",
}


def _default_extension_for_obj(obj: Any) -> str | None:
    """Return the bridge's preferred default extension for *obj*."""
    return _CORE_TYPE_DEFAULT_EXTENSION.get(type(obj).__name__)


def _normalise_config_extension(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if text.startswith(".") else f".{text}"


def _normalise_capability_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _port_config_by_name(port_configs: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(port_configs, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in port_configs:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if name:
            result[name] = entry
    return result


def _materialise_data_object(
    obj: Any,
    dest_dir: Path,
    *,
    filename_stem: str,
    extension: str | None = None,
    capability_id: str | None = None,
    registry: Any | None,
) -> dict[str, Any]:
    """Materialise *obj* and return a manifest entry."""
    extension = (
        extension
        if extension is not None
        else (None if capability_id else _bridge_default_extension_for(obj, registry=registry))
    )
    out_path = _bridge_materialise_to_file(
        obj,
        dest_dir,
        extension=extension,
        filename_stem=filename_stem,
        capability_id=capability_id,
        registry=registry,
    )
    resolved_extension = out_path.suffix
    capability = _resolve_saver_capability_for(
        type(obj),
        resolved_extension,
        capability_id=capability_id,
        registry=registry,
    )
    entry = {
        "type": type(obj).__name__,
        "path": str(out_path),
        "extension": resolved_extension,
        "format": capability.format_id if capability is not None else None,
    }
    if capability is not None:
        entry["capability_id"] = capability.id
    return entry


def _resolve_saver_capability_for(
    cls: type,
    extension: str,
    *,
    capability_id: str | None = None,
    registry: Any | None,
) -> Any | None:
    """Return the saver capability used for *extension*."""
    from scistudio.blocks.registry import BlockRegistry

    reg = registry if registry is not None else BlockRegistry()
    if registry is None:
        reg.scan()
    try:
        return reg.find_saver_capability(cls, extension, capability_id=capability_id)
    except LookupError:
        return None


def _get_registry(registry: Any | None) -> BlockRegistry:
    """Return *registry* or build/scan a fresh :class:`BlockRegistry`."""
    from scistudio.blocks.registry import BlockRegistry

    if registry is not None:
        return cast(BlockRegistry, registry)
    reg = BlockRegistry()
    reg.scan()
    return reg


def _bridge_default_extension_for(obj: Any, *, registry: Any | None) -> str | None:
    """Return the bridge's chosen extension for *obj*.

    Core types use a deterministic mapping. Plugin types fall back to the
    first extension declared by the first matching saver.
    """
    preferred = _default_extension_for_obj(obj)
    if preferred is not None:
        return preferred

    reg = _get_registry(registry)
    try:
        capability = reg.find_saver_capability(type(obj))
    except LookupError:
        return None
    return capability.extensions[0]


def _resolve_core_type_param(obj_or_type: Any) -> str | None:
    """Return the SaveData ``core_type`` enum value for a core DataObject."""
    core_type_names = {"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"}
    cls = obj_or_type if isinstance(obj_or_type, type) else type(obj_or_type)
    for base in cls.__mro__:
        if base.__name__ in core_type_names:
            return base.__name__
    return None


def _try_mount_existing_path(obj: Any, dest: Path, extension: str) -> bool:
    """Link existing on-disk storage into *dest* when extensions already match."""
    ref = getattr(obj, "storage_ref", None)
    if ref is None:
        return False
    src_path_raw = getattr(ref, "path", None)
    if not src_path_raw:
        return False

    src_path = Path(str(src_path_raw))
    if not src_path.exists():
        return False

    target_ext = extension.lower()
    if src_path.suffix.lower() != target_ext:
        return False

    from scistudio.utils.fs import mount_pathlike

    try:
        mount_pathlike(src_path, dest)
    except (OSError, FileExistsError):
        return False
    return True


def _bridge_materialise_to_file(
    obj: Any,
    dest_dir: Path,
    *,
    extension: str | None,
    filename_stem: str,
    capability_id: str | None = None,
    registry: Any | None,
) -> Path:
    """Materialise *obj* through the canonical engine helper."""

    from scistudio.blocks.io.materialisation import materialise_to_file

    return materialise_to_file(
        obj,
        dest_dir,
        extension=extension,
        filename_stem=filename_stem,
        capability_id=capability_id,
        registry=_get_registry(registry),
    )
